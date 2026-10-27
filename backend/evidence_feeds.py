"""Strict primary-source parsers. Context is never a substitute for fare history."""
import calendar
import csv
import hashlib
import io
import math
import re
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

ATF_URL='https://iocl.com/atf-domestic-airlines'
AAI_URL='https://www.aai.aero/en/business-opportunities/aai-traffic-news'
PARSER_VERSION=1
MONTHS={name.lower():i for i,name in enumerate(calendar.month_name) if name}
AIRPORT_LABELS={
    'DEL':'DELHI (DIAL)','BOM':'MUMBAI (MIAL)','BLR':'BENGALURU (BIAL)',
    'HYD':'HYDERABAD (GHIAL)','COK':'KOCHI','MAA':'CHENNAI','CCU':'KOLKATA',
    'GOI':'GOA (DABOLIM)','GOX':'GOA (MOPA)','JAI':'JAIPUR','AMD':'AHMEDABAD',
    'PNQ':'PUNE','ATQ':'AMRITSAR','LKO':'LUCKNOW','GAU':'GUWAHATI',
    'TRV':'THIRUVANANTHAPURAM','IXC':'CHANDIGARH'}


def source_metadata(raw,url,transport='http'):
    data=raw.encode('utf-8') if isinstance(raw,str) else raw
    return dict(source_url=url,source_sha256=hashlib.sha256(data).hexdigest(),
                parser_version=PARSER_VERSION,transport=transport)


def source_document_metadata(raw, url, observations, date_field='date', transport='http', download_url=None):
    """Hash one received document and report only rows actually parsed from it."""
    dates = [date.fromisoformat(row[date_field]).isoformat() for row in observations]
    if not dates:
        raise ValueError('Source document has no parsed observation dates')
    receipt_time = {'fetched_at' if transport == 'http' else 'recorded_at': datetime.now(timezone.utc).isoformat()}
    return dict(**source_metadata(raw, url, transport), download_url=download_url or url,
                **receipt_time, hash_scope='source_document',
                first_observation_date=min(dates), last_observation_date=max(dates),
                observation_count=len(observations), coverage='parsed_document_rows')


def merge_source_documents(previous, fresh_documents, **updates):
    """Keep bounded receipt history without claiming a hash covers a merged series.

    Legacy receipts with no recorded parsed bounds remain explicitly unknown.
    Re-fetching identical content updates its receipt; revisions remain distinct.
    """
    previous = previous if isinstance(previous, dict) else {}
    documents = []
    for document in previous.get('source_documents', []) if isinstance(previous.get('source_documents'), list) else []:
        if isinstance(document, dict) and document.get('source_url') and document.get('source_sha256'):
            documents.append(dict(document))
    # Preserve the former top-level receipt too, but never infer its date bounds
    # from the merged observations (which may contain several older documents).
    if previous.get('source_url') and previous.get('source_sha256'):
        legacy = {key: previous[key] for key in ('source_url', 'source_sha256', 'download_url',
            'parser_version', 'transport', 'fetched_at', 'recorded_at', 'hash_scope', 'first_observation_date',
            'last_observation_date', 'observation_count', 'coverage') if key in previous}
        identity = lambda item: (item.get('source_url'), item.get('download_url'), item.get('source_sha256'))
        if not any(identity(document) == identity(legacy) for document in documents):
            documents.append(legacy)
    fresh_documents = [dict(document) for document in fresh_documents if isinstance(document, dict)
                       and document.get('source_url') and document.get('source_sha256')]
    merged = {}
    for document in documents + fresh_documents:
        key = (document.get('source_url'), document.get('download_url'), document.get('source_sha256'))
        document = {**merged.pop(key, {}), **document}
        if not all(document.get(field) is not None for field in
                   ('first_observation_date', 'last_observation_date', 'observation_count')):
            document['coverage'] = 'unknown_legacy_document_coverage'
        else:
            document.setdefault('coverage', 'recorded_document_rows')
        if document.get('hash_scope') == 'latest_source_document_not_merged_observations':
            document['hash_scope'] = 'source_document'
        document.setdefault('hash_scope', 'legacy_document_scope_unverified' if document['coverage'] == 'unknown_legacy_document_coverage' else 'source_document')
        merged[key] = document
    discarded = max(0, len(merged) - 64)
    prior_discarded = previous.get('source_documents_discarded', 0)
    prior_discarded = prior_discarded if isinstance(prior_discarded, int) and not isinstance(prior_discarded, bool) and prior_discarded > 0 else 0
    unknown = any(document.get('coverage') == 'unknown_legacy_document_coverage' for document in merged.values())
    result = {**previous, **updates, 'source_documents': list(merged.values())[-64:],
              'source_documents_limit': 64, 'source_documents_discarded': prior_discarded + discarded,
              'legacy_document_coverage_unknown': bool(previous.get('legacy_document_coverage_unknown') or unknown)}
    if fresh_documents:
        received = fresh_documents[-1]
        latest = merged[(received.get('source_url'), received.get('download_url'), received.get('source_sha256'))]
        for key in ('source_url', 'source_sha256', 'download_url', 'parser_version', 'transport', 'fetched_at', 'recorded_at',
                    'first_observation_date', 'last_observation_date', 'observation_count', 'coverage'):
            if key in latest:
                result[key] = latest[key]
            elif key in ('download_url', 'first_observation_date', 'last_observation_date', 'observation_count'):
                result.pop(key, None)
        result['hash_scope'] = 'latest_source_document_not_merged_observations'
        # A reviewed excerpt receipt must not inherit a previous HTTP fetch time.
        if 'fetched_at' not in latest:
            result.pop('fetched_at', None)
        if 'recorded_at' not in latest:
            result.pop('recorded_at', None)
    return result


def fred_points(raw,code,today=None):
    today=today or date.today()
    points={}
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            day=date.fromisoformat(row.get('observation_date') or row.get('DATE') or '')
            value=float(row.get(code,''))
        except (ValueError,TypeError):
            continue
        if day>today or not math.isfinite(value) or value<=0:
            continue
        if day in points and points[day]!=value:
            raise ValueError('Conflicting same-day source observations')
        points[day]=value
    if not points:
        raise ValueError('No valid dated observations; blocked or changed source')
    return [dict(date=d.isoformat(),value=v) for d,v in sorted(points.items())]


def atf_rows(text,today=None):
    """Accept only full dated rows and all four INR/kilolitre city values."""
    today=today or date.today()
    rows={}
    pattern=r'([A-Za-z]+\s+\d{1,2},\s*\d{4})\s*\|\s*([\d,.]+)\s*\|\s*([\d,.]+)\s*\|\s*([\d,.]+)\s*\|\s*([\d,.]+)'
    for match in re.finditer(pattern,text):
        day=datetime.strptime(match[1],'%B %d, %Y').date()
        if day>today:
            continue
        for city,number in zip(('Delhi','Kolkata','Mumbai','Chennai'),match.groups()[1:]):
            if not re.fullmatch(r'(?:\d+|\d{1,2}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+)\.\d{2}',number):
                raise ValueError('Unrecognized ATF number grouping')
            value=float(number.replace(',',''))
            if not math.isfinite(value) or value<=0:
                raise ValueError('Invalid ATF value')
            key=(day.isoformat(),city)
            if key in rows and rows[key]['value']!=value:
                raise ValueError('Conflicting ATF city/date rows')
            rows[key]=dict(date=day.isoformat(),city=city,value=value,units='INR/kilolitre',source_url=ATF_URL)
    if not rows:
        raise ValueError('No dated ATF table; challenge/error/layout unsupported')
    return sorted(rows.values(),key=lambda x:(x['date'],x['city']))


def atf_html(raw):
    soup=BeautifulSoup(raw,'html.parser')
    tables=[]
    for table in soup.find_all('table'):
        text=table.get_text(' ',strip=True)
        if not all(city in text for city in ('Delhi','Kolkata','Mumbai','Chennai')):
            continue
        for tr in table.find_all('tr'):
            tables.append(' | '.join(cell.get_text(' ',strip=True) for cell in tr.find_all(['td','th'])))
    if not re.search(r'Rupees\s*/\s*Kl|INR\s*/\s*(?:kl|kilolitre)',soup.get_text(' ',strip=True),re.I):
        raise ValueError('ATF table currency/units are not established')
    return atf_rows('\n'.join(tables))


def aai_links(raw):
    links=[]
    for a in BeautifulSoup(raw,'html.parser').find_all('a',href=True):
        url=urljoin(AAI_URL,a['href'])
        parsed=urlparse(url)
        if parsed.scheme=='https' and parsed.hostname=='www.aai.aero' and re.search(r'Annex_?3(?:_\d+)?\.pdf$',parsed.path,re.I):
            if url not in links:
                links.append(url)
    if not links:
        raise ValueError('No published AAI passenger report links')
    return links


def aai_text(text,url,today=None):
    """Extract domestic monthly columns, excluding international/cumulative totals."""
    today=today or date.today()
    clean=re.sub(r'[^\x20-\x7e\n]',' ',text)
    start=re.search(r'Domestic\s+Passengers',clean,re.I)
    if not start:
        raise ValueError('Domestic passenger section missing')
    section=clean[start.end():]
    stop=re.search(r'Total\s+Passengers|ANNEXURE-III\s+C',section,re.I)
    if stop:
        section=section[:stop.start()]
    header=re.search(r'\b('+'|'.join(calendar.month_name[1:])+r')[ \t]+\1[^\n]*',section,re.I)
    if not header:
        raise ValueError('AAI month/current/prior column headers changed')
    # Older published layouts place S.NO or a period label before the year row.
    year_rows='\n'.join(section[header.end():].splitlines()[:4])
    years=re.search(r'(?<!\d)(20\d{2})[ \t]+(20\d{2})(?![\d-])',year_rows)
    if not years:
        raise ValueError('AAI monthly year columns missing')
    month=MONTHS[header[1].lower()];year=int(years[1]);prior=int(years[2])
    if prior!=year-1:
        raise ValueError('AAI comparison is not the same month last year')
    end=date(year,month,calendar.monthrange(year,month)[1])
    if end>today:
        raise ValueError('Future or incomplete AAI reporting month')
    result=[]
    for code,label in AIRPORT_LABELS.items():
        # Bilingual names precede these exact English names. Numeric columns follow.
        label_pattern=re.escape(label)
        if code=='DEL':
            label_pattern=r'DELHI(?:\s+\(DIAL\))?'
        elif code=='GOI':
            label_pattern=r'GOA(?:\s+\(DABOLIM\))?'
        pattern=r'\b'+label_pattern+r'\s+(\d+)\s+(\d+)\s+(-?\d+(?:\.\d+)?%|-)\s+(\d+)\s+(\d+)'
        matches=list(re.finditer(pattern,section))
        if len(matches)!=1:
            raise ValueError('AAI airport row missing or duplicated: '+code)
        m=matches[0];current,previous=int(m[1]),int(m[2])
        if m[3]!='-' and (previous==0 or abs((current/previous-1)*100-float(m[3][:-1]))>.11):
            raise ValueError('AAI monthly numbers disagree with printed percentage')
        result.append(dict(period_end=end.isoformat(),period_month=end.strftime('%Y-%m'),
            airport=code,airport_label=label,domestic_current=current,domestic_previous=previous,
            previous_period_month=f'{prior}-{month:02d}',source_url=url))
    return result


def aai_pdf(raw,url):
    if not raw.startswith(b'%PDF-') or len(raw)>5_000_000:
        raise ValueError('AAI response is not a bounded PDF')
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(raw))
    if len(reader.pages)>20:
        raise ValueError('Unexpected AAI PDF page count')
    return aai_text('\n'.join(p.extract_text(extraction_mode='layout') for p in reader.pages),url)


async def fetch_bytes(session,url,limit=5_000_000):
    async with session.get(url) as response:
        response.raise_for_status()
        chunks=[];size=0
        async for chunk in response.content.iter_chunked(65536):
            size+=len(chunk)
            if size>limit:
                raise ValueError('Source response exceeded size limit')
            chunks.append(chunk)
        return b''.join(chunks)
