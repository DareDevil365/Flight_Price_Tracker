"""Published carrier-wide domestic capacity, never route fares or seat inventory."""
import calendar
import math
import re
from datetime import date
from bs4 import BeautifulSoup
from evidence_feeds import fetch_bytes, source_metadata, ATF_URL, atf_html, source_document_metadata, merge_source_documents

CAPACITY_URL = 'https://www.goindigo.in/information/investor-relations/operational-statistics/domestic.html'
CURRENT_ATF_URL = 'https://iocl.com/prices-of-petroleum-products'
NUMBER = r'(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?'
MONTH_MAP = {name[:3].upper(): i for i, name in enumerate(calendar.month_name) if name}
TITLE = r'Monthly Operational Statistics for FY (20\d{2})-(\d{2}) on scheduled domestic services'


def source_number(value):
    if not re.fullmatch(NUMBER, value):
        raise ValueError('Invalid published number grouping')
    result = float(value.replace(',', ''))
    if not math.isfinite(result) or result < 0:
        raise ValueError('Invalid published number')
    return result


def capacity_text(text, today=None, rejected=None):
    """Read the observed 17-column table; preserve blanks and fiscal-year scope."""
    today = today or date.today()
    output = {}
    titles = list(re.finditer(TITLE, text, re.I))
    for index, title in enumerate(titles):
        start_year = int(title[1])
        if int(title[2]) != (start_year + 1) % 100:
            raise ValueError('Fiscal year is inconsistent')
        section = text[title.end():titles[index + 1].start() if index + 1 < len(titles) else len(text)]
        header = re.sub(r'\s+', ' ', section).upper()
        if not re.search(r'PASSENGERS CARRIED.*?PASSENGER KMS\.?\s*PERFORMED.*?AVAILABLE SEAT KILOMETRE.*?PAX\.\s*LOAD FACTOR', header):
            raise ValueError('Carrier monthly column order changed')
        if 'IN THOUSAND' not in header or 'IN %' not in header:
            raise ValueError('Carrier units are missing')
        for line in section.splitlines():
            cells = [cell.strip() for cell in line.split('|')]
            month = MONTH_MAP.get(cells[0][:3].upper()) if cells else None
            if not month or cells[0].upper() not in ('APR','MAY','JUN','JUNE','JUL','JULY','AUG','SEP','OCT','NOV','DEC','JAN','FEB','MAR'):
                continue
            if len(cells) != 17:
                if rejected is not None:
                    rejected.append(dict(fiscal_year=start_year,month=cells[0],reason='Incomplete source row; no value inferred'))
                continue
            # Empty source rows represent unavailable months, never zero traffic.
            if all(not value for value in cells[1:]):
                continue
            numbers = [source_number(value) for value in cells[1:]]
            year = start_year if month >= 4 else start_year + 1
            end = date(year, month, calendar.monthrange(year, month)[1])
            if end > today:
                continue
            passengers, rpk, ask, plf = numbers[3:7]
            if not passengers.is_integer() or passengers <= 0 or rpk <= 0 or ask <= 0 or not 0 <= plf <= 100:
                raise ValueError('Carrier passengers, capacity or load factor invalid')
            if abs(rpk / ask * 100 - plf) > .11:
                raise ValueError('Carrier load factor disagrees with published RPK/ASK')
            row = dict(airline='IndiGo',period_month=end.strftime('%Y-%m'),period_end=end.isoformat(),
                       passengers=int(passengers),passenger_km_thousands=rpk,seat_km_thousands=ask,
                       load_factor_pct=plf,source_url=CAPACITY_URL)
            key = row['period_month']
            if key in output and output[key] != row:
                raise ValueError('Conflicting carrier monthly rows')
            output[key] = row
    if not output:
        raise ValueError('No dated domestic carrier table passed validation')
    return [output[key] for key in sorted(output)]


def capacity_html(raw, rejected=None):
    soup = BeautifulSoup(raw, 'html.parser')
    parts = []
    for table in soup.find_all('table'):
        header = table.get_text(' ', strip=True)
        if not re.search('PAX.*?LOAD FACTOR', header, re.I):
            continue
        title = table.find_previous(string=re.compile(TITLE, re.I))
        if title is None:
            continue
        rows = '\n'.join(' | '.join(cell.get_text(' ',strip=True) for cell in tr.find_all(['td','th'])) for tr in table.find_all('tr'))
        parts.append(str(title) + '\n' + header + '\n' + rows)
    return capacity_text('\n'.join(parts), rejected=rejected)


def current_atf_html(raw, today=None):
    """Use only the dated domestic INR/KL block, not LPG/footer/international dates."""
    soup = BeautifulSoup(raw, 'html.parser')
    heading = soup.find(string=re.compile(r'ATF Prices in Metros.*?Rupees\s*/\s*Kl.*?Domestic Airlines', re.I))
    if heading is None:
        raise ValueError('Domestic INR/KL ATF section missing')
    table = heading.find_next('table')
    if table is None:
        raise ValueError('Domestic ATF table missing')
    scope = []
    for element in heading.parent.next_elements:
        if element is table:
            break
        if getattr(element,'name',None) in ('h1','h2'):
            raise ValueError('ATF table left its domestic section')
        if isinstance(element,str):
            scope.append(element.strip())
    dates = re.findall(r'Last updated on\s+([A-Za-z]+\s+\d{1,2},\s*20\d{2})', ' '.join(scope), re.I)
    if len(dates) != 1:
        raise ValueError('Domestic ATF observation date ambiguous')
    from datetime import datetime
    day = datetime.strptime(dates[0],'%B %d, %Y').date()
    if day > (today or date.today()):
        raise ValueError('Future ATF observation date')
    rows = {}
    for tr in table.find_all('tr'):
        cells = [cell.get_text(' ',strip=True) for cell in tr.find_all(['th','td'])]
        if len(cells) != 2 or cells[0] not in ('Delhi','Kolkata','Mumbai','Chennai'):
            continue
        if cells[0] in rows:
            raise ValueError('Duplicated ATF city row')
        value = source_number(cells[1])
        if value <= 0:
            raise ValueError('Invalid ATF price')
        rows[cells[0]] = dict(date=day.isoformat(),city=cells[0],value=value,units='INR/kilolitre',source_url=CURRENT_ATF_URL)
    if set(rows) != {'Delhi','Kolkata','Mumbai','Chennai'}:
        raise ValueError('Incomplete domestic ATF city table')
    return [rows[city] for city in sorted(rows)]


async def refresh_capacity(context, session, status):
    try:
        raw = (await fetch_bytes(session,CAPACITY_URL,2_000_000)).decode('utf-8')
        rejected=[]
        rows = capacity_html(raw,rejected=rejected)
        await context._save('airline_capacity',dict(**source_metadata(raw,CAPACITY_URL),observations=rows,
            rejected_rows=rejected,units='Percent (passenger-km / available seat-km)',as_of=rows[-1]['period_end'],
            scope='IndiGo-wide scheduled domestic operations, not all Indian airlines, directed route demand, available seats or fare training'))
        status['airline_capacity'] = f'{len(rows)} published carrier-month rows; source reporting months retained'
    except Exception as exc:
        status['airline_capacity'] = f'Unavailable: {type(exc).__name__}. Cached carrier-wide observations retain their actual reporting months.'


async def refresh_atf(context, session, status):
    cache = await context.snapshot()
    entry = cache.get('indian_atf',{})
    previous = entry.get('data',{}) if isinstance(entry,dict) else {}
    if not isinstance(previous,dict):
        previous={}
    old = {}
    if previous.get('parser_version') == 1:
        for row in previous.get('observations',[]) if isinstance(previous.get('observations'),list) else []:
            try:
                if isinstance(row,dict) and row.get('city') in ('Delhi','Kolkata','Mumbai','Chennai') and date.fromisoformat(row['date']) <= date.today() and row.get('units') == 'INR/kilolitre' and isinstance(row.get('value'),(int,float)) and not isinstance(row['value'],bool) and math.isfinite(row['value']) and row['value'] > 0 and isinstance(row.get('source_url'),str) and row['source_url'].startswith('https://'):
                    old[(row['date'],row['city'])] = row
            except (TypeError,ValueError,KeyError):
                continue
    failures, sources, fresh = [], [], {}
    for url, reader in ((ATF_URL,atf_html),(CURRENT_ATF_URL,current_atf_html)):
        try:
            body = await fetch_bytes(session,url,1_000_000)
            raw = body.decode('utf-8-sig')
            rows = reader(raw)
            proposed={(row['date'],row['city']):row for row in rows}
            if any(key in fresh and fresh[key]['value']!=row['value'] for key,row in proposed.items()):
                raise ValueError('Conflicting published ATF tables')
            fresh.update(proposed)
            old.update(proposed)
            sources.append(source_document_metadata(body,url,rows))
        except Exception as exc:
            failures.append(dict(source_url=url,error=type(exc).__name__))
    if sources:
        rows = [old[key] for key in sorted(old)]
        await context._save('indian_atf',merge_source_documents(previous,sources,parser_version=1,
            failed_sources=failures,units='INR/kilolitre',observations=rows,
            as_of=rows[-1]['date'],scope='Dated metro ATF posted prices, not current airline contracted costs or fare forecasts'))
        status['indian_atf'] = f'{len(rows)} dated city observations; {len(failures)} sources unavailable; actual table dates retained'
    else:
        status['indian_atf'] = 'Unavailable: both published tables failed validation/access. Cached ATF retains actual dates; no challenge bypass.'
