"""Deterministic three-valued offer conditions. Unknown is never eligibility proof."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime

METHODS = {'CREDIT':r'\bcredit\s+cards?\b', 'DEBIT':r'\bdebit\s+cards?\b',
           'UPI':r'\bupi\b', 'NET_BANKING':r'\bnet[ -]?banking\b', 'WALLET':r'\bwallets?\b'}


@dataclass
class Decision:
    status: str
    reasons: list = field(default_factory=list)


def evaluate_tree(node, facts):
    """Supported structured AND/OR/NOT predicates; unsupported facts stay unknown."""
    op=node.get('op')
    if op in ('all','any'):
        children=[evaluate_tree(child,facts) for child in node.get('conditions',[])]
        if not children:
            return Decision('unknown',['Empty condition group'])
        statuses=[c.status for c in children]
        status=('ineligible' if 'ineligible' in statuses else 'unknown' if 'unknown' in statuses else 'eligible') if op=='all' else (
            'eligible' if 'eligible' in statuses else 'unknown' if 'unknown' in statuses else 'ineligible')
        return Decision(status,[reason for c in children for reason in c.reasons])
    if op=='not':
        child=evaluate_tree(node.get('condition',{}),facts)
        return Decision({'eligible':'ineligible','ineligible':'eligible','unknown':'unknown'}[child.status],child.reasons)
    value=facts.get(node.get('field'))
    reason=node.get('evidence') or node.get('field') or 'Unsupported condition'
    if value is None:
        return Decision('unknown',[reason+' is unconfirmed'])
    try:
        if op=='in':
            passed=bool(set(value if isinstance(value,list) else [value]) & set(node['values']))
        elif op=='gte':
            passed=value>=node['value']
        elif op=='eq':
            passed=value==node['value']
        else:
            return Decision('unknown',[reason+' is unsupported'])
    except (KeyError,TypeError):
        return Decision('unknown',[reason+' could not be evaluated'])
    return Decision('eligible' if passed else 'ineligible',[reason])


def clauses(text):
    # Periods inside Rs. and decimals must not split required payment terms.
    text=re.sub(r'\bRs\.', 'INR',text,flags=re.I)
    return [s.strip() for s in re.split(r'[\n;|]|\.(?:\s|$)',text) if s.strip()]


def payment_constraints(text):
    required,excluded,banks_required,banks_excluded=set(),set(),set(),set()
    excluded_groups=[]
    required_groups=[]
    ambiguous=False
    from offer_parser import BANKS
    for clause in clauses(text):
        negative=bool(re.search(r'\b(?:not (?:valid|applicable|eligible)|exclud(?:e[ds]?|ing)|except|ineligible)\b',clause,re.I))
        methods={m for m,p in METHODS.items() if re.search(p,clause,re.I)}
        banks={b for b in BANKS if re.search(r'\b'+re.escape(b)+r'\b',clause,re.I)}
        if negative:
            # "Not valid on Bank X credit cards" excludes that combination,
            # rather than every credit card and every Bank X payment.
            from offer_parser import card_product
            product=card_product(clause)
            excluded_groups.append(dict(methods=sorted(methods),banks=sorted(banks),product=product))
            if not banks and not product:
                excluded.update(methods)
            if not methods and not product:
                banks_excluded.update(banks)
        else:
            required.update(methods)
            banks_required.update(banks)
            if methods and banks:
                required_groups.append(dict(methods=sorted(methods),banks=sorted(banks)))
                ambiguous |= len(methods)>1 and len(banks)>1
    return dict(methods=sorted(required),excluded_methods=sorted(excluded),
                banks=sorted(banks_required),excluded_banks=sorted(banks_excluded),
                excluded_groups=excluded_groups,required_groups=required_groups,ambiguous=ambiguous)


def parse_date(value):
    if not value:
        return None
    value=re.sub(r'(\d)(?:st|nd|rd|th)\b',r'\1',str(value),flags=re.I).replace(',','')
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d %b %Y','%d %B %Y','%b %d %Y','%B %d %Y'):
        try:
            return datetime.strptime(value.strip(),fmt).date()
        except ValueError:
            continue
    return None


def booking_validity(text):
    """Only explicit booking/offer windows; never confuse travel dates with expiry."""
    token=r'\b(?:20\d{2}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]20\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+20\d{2})\b'
    start,end,unknown=None,None,False
    for match in re.finditer(r'\b(offer validity|offer period|booking period|valid from|valid until|valid till|expires?(?: on)?|ends? on)\s*[:\-]?\s*([^\n.;]{0,180})',text,re.I):
        label,body=match[1].lower(),match[2]
        dates=[parse_date(t) for t in re.findall(token,body)]
        dates=[d for d in dates if d]
        if len(dates)>=2:
            start,end=dates[0],dates[1]
        elif dates:
            if re.search(r'\b(?:to|till|until|through)\b',body,re.I):
                end=dates[-1]
                unknown=True  # Do not invent the missing start year.
            elif label=='valid from':
                start=dates[0]
            else:
                end=dates[0]
        else:
            unknown=True
    return start,end,unknown


def evaluate_offer(coupon, rules):
    from offer_parser import payment_terms, card_product
    text=payment_terms(coupon.get('description') or '')
    exclusive=lambda scope:bool(re.search(r'\b(?:only\s+(?:on\s+|for\s+)?'+scope+r'(?:\s+flights?)?|'+scope+r'(?:\s+flights?)?\s+only)\b',text,re.I))
    if exclusive('domestic') and exclusive('international'):
        return Decision('unknown',['Conflicting domestic-only and international-only restrictions; check current merchant terms'])
    positive='; '.join(c for c in clauses(text) if not re.search(
        r'\b(?:not (?:valid|applicable|eligible)|exclud(?:e[ds]?|ing)|except|ineligible)\b',c,re.I))
    constraints=payment_constraints(text)
    selected=rules.get('selected_payment')
    facts={'passenger_count':rules.get('passenger_count',1),
           'method':selected.get('method') if selected else None,
           'banks':selected.get('banks') or None if selected else None,
           'spend':rules.get('booking_total'),
           'fare_subtotal':rules.get('fare_subtotal'),
           **rules.get('eligibility_facts',{})}
    nodes=[]
    if constraints['ambiguous']:
        nodes.append(dict(op='eq',field='payment_combinations_confirmed',value=True,evidence='Ambiguous bank/payment combinations'))
    groups=[]
    for group in constraints['required_groups']:
        groups.append(dict(op='all',conditions=[dict(op='in',field='method',values=group['methods']),
            dict(op='in',field='banks',values=group['banks'])]))
    if groups:
        nodes.append(dict(op='any',conditions=groups))
    for index,group in enumerate(constraints['excluded_groups']):
        conditions=[]
        if group['methods']:
            conditions.append(dict(op='in',field='method',values=group['methods']))
        if group['banks']:
            conditions.append(dict(op='in',field='banks',values=group['banks']))
        if group['product']:
            label=selected.get('label','') if selected else ''
            normalized=re.sub(r'[^a-z0-9]','',label.lower())
            key='excluded_product_'+str(index)
            facts[key]=all(re.sub(r'[^a-z0-9]','',t.lower()) in normalized for t in group['product'][1]) if label else None
            conditions.append(dict(op='eq',field=key,value=True))
        if conditions:
            nodes.append(dict(op='not',condition=dict(op='all',conditions=conditions)))
    if re.search(r'\b(?:travel period|travel dates?|valid for travel|operated by|selected routes?|select routes?)\b',positive,re.I):
        nodes.append(dict(op='eq',field='travel_conditions_confirmed',value=True,evidence='Travel/airline restrictions'))
    today=parse_date(rules.get('booking_date')) or date.today()
    published_start,published_end,unknown_window=booking_validity(text)
    if published_start and today<published_start:
        return Decision('ineligible',['Published offer has not started'])
    if published_end and today>published_end:
        return Decision('ineligible',['Published offer has expired'])
    if unknown_window:
        nodes.append(dict(op='eq',field='booking_window_confirmed',value=True,evidence='Unparsed booking validity'))
    for key,label,compare in [('valid_until','Offer expiry',lambda d:today<=d),('valid_from','Offer start',lambda d:today>=d)]:
        if coupon.get(key):
            value=parse_date(coupon[key])
            if not value:
                return Decision('unknown',[label+' could not be parsed'])
            if not compare(value):
                return Decision('ineligible',['Offer has expired' if key=='valid_until' else 'Offer has not started'])
    weekdays=re.search(r'\b(?:every|only on|valid on)\s+((?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)(?:s)?(?:\s*(?:,|and|or|&)\s*)?)+)',positive,re.I)
    if weekdays:
        days=re.findall(r'Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday',weekdays[1],re.I)
        if today.strftime('%A').lower() not in [d.lower() for d in days]:
            return Decision('ineligible',['Offer booking weekdays: '+', '.join(days)])
    if re.search(r'\b(?:students?|senior citizens?|defen[cs]e|armed forces|doctors?|nurses?|healthcare|army|government personnel)\b',positive,re.I):
        nodes.append(dict(op='eq',field='special_traveller_eligible',value=True,evidence='Special traveller eligibility'))
    if re.search(r'\b(?:chance to win|one lucky|lucky draw|lottery)\b',positive,re.I):
        return Decision('ineligible',['A chance-based reward is not an immediate payable discount'])
    if re.search(r'\bexisting users?\b',positive,re.I) and not re.search(r'\bnew (?:and existing )?users?\b|\ball users?\b',positive,re.I):
        nodes.append(dict(op='eq',field='account_eligible',value=True,evidence='Existing account eligibility'))
    if re.search(r'\b(?:new users?|new customers?|first bookings?|first transactions?|signup|invitation.only|selected customers?|received communication)\b',positive,re.I):
        nodes.append(dict(op='eq',field='account_eligible',value=True,evidence='Account eligibility'))
    if re.search(r'\b(?:once per|once a|one (?:time|transaction) per|usage limit|redemption limit)\b',positive,re.I):
        nodes.append(dict(op='eq',field='redemption_available',value=True,evidence='Offer usage limit'))
    # A published flight+insurance combo is conditional on the additional
    # product, even when it does not require a particular payment method. Mere
    # mentions of optional insurance must not restrict an ordinary flight code.
    addon=r'(?:insurance|seats?|meals?|baggage|add[ -]?ons?)'
    required_addon=re.search(
        r'\bflight(?:s| booking)?\s*(?:and|\+)\s*(?:[A-Za-z]+\s+)?'+addon+r'\s+combo\b'
        r'|\b(?:requires?|only with|only on purchase of)\s+(?:[A-Za-z]+\s+){0,2}'+addon+r'\b',
        positive,re.I)
    if required_addon:
        nodes.append(dict(op='eq',field='required_addon_confirmed',value=True,evidence='Required add-on/combo eligibility'))
    people=re.search(r'(?:on|for)\s+(\d+)\s*(or more\s*)?(?:pax|passengers?|adults?)',positive,re.I)
    if people:
        nodes.append(dict(op='gte' if people[2] else 'eq',field='passenger_count',value=int(people[1]),
            evidence='Minimum passengers' if people[2] else 'Required passenger count'))
    if re.search(r'(?:off|discount).{0,15}\b(?:child|infant)\b',positive,re.I):
        return Decision('ineligible',['Child/infant offers are unsupported by adult-only search'])
    # Infer payment requirements only from positive clauses. Old database fields
    # were inferred from all words; do not reintroduce those false requirements.
    methods=constraints['methods']
    if not methods and not text and coupon.get('card_type') not in (None,'ANY'):
        methods=[coupon['card_type']]
    if not methods and 'UPI' in coupon.get('code','').upper():
        methods=['UPI']
    if methods:
        nodes.append(dict(op='in',field='method',values=methods,evidence='Required payment method'))
    if constraints['excluded_methods']:
        nodes.append(dict(op='not',condition=dict(op='in',field='method',values=constraints['excluded_methods'],evidence='Excluded payment method')))
    banks=constraints['banks']
    if not text:
        banks=(coupon.get('bank_restriction') or '').split('|')
    banks=[b for b in banks if b]
    blocked=set(rules.get('blacklisted_banks',[]))
    if banks and not set(banks)-blocked:
        return Decision('ineligible',['User cannot use any bank supported by this offer'])
    if banks:
        nodes.append(dict(op='in',field='banks',values=banks,evidence='Required payment bank'))
    if constraints['excluded_banks']:
        nodes.append(dict(op='not',condition=dict(op='in',field='banks',values=constraints['excluded_banks'],evidence='Excluded payment bank')))
    allowed=rules.get('allowed_card_types',[])
    if allowed and methods and not set(methods)&set(allowed):
        return Decision('ineligible',['User excluded the required payment method'])
    special=card_product(positive)
    for excluded in rules.get('excluded_card_names',[]):
        if special and card_product(excluded)==special:
            return Decision('ineligible',['User excluded this card product'])
    if special:
        label=selected.get('label','') if selected else ''
        normalized=re.sub(r'[^a-z0-9]','',label.lower())
        facts['card_product_matches']=True if all(re.sub(r'[^a-z0-9]','',t.lower()) in normalized for t in special[1]) else None
        nodes.append(dict(op='eq',field='card_product_matches',value=True,evidence='Required card product'))
    networks=re.findall(r'\b(visa|mastercard|rupay|amex)\b',positive,re.I)
    if networks:
        label=selected.get('label','') if selected else ''
        facts['network_matches']=True if any(re.search(r'\b'+n+r'\b',label,re.I) for n in networks) else None
        nodes.append(dict(op='eq',field='network_matches',value=True,evidence='Required card network'))
    for pattern,flag,label in [(r'\b(?:emi|easyemi|equated monthly|installments?)\b','allow_emi','EMI'),
                                (r'\b(?:bnpl|buy now pay later|pay later|simpl|lazypay)\b','allow_bnpl','BNPL')]:
        if re.search(pattern,positive,re.I) and not rules.get(flag,False):
            return Decision('ineligible',[label+' blocked by user'])
    if 'WALLET' in methods and not rules.get('allow_wallet_offers',True):
        return Decision('ineligible',['Wallet payment blocked by user'])
    if coupon.get('app_only') and not rules.get('allow_app_only',False):
        return Decision('ineligible',['App-only offer is unavailable in this web checkout'])
    minimum=coupon.get('min_booking_value')
    if minimum:
        field='fare_subtotal' if re.search(r'minimum.{0,40}base fare|base fare.{0,40}minimum',positive,re.I) else 'spend'
        nodes.append(dict(op='gte',field=field,value=minimum,evidence='Minimum eligible spend'))
    if coupon.get('eligibility_unconfirmed'):
        nodes.append(dict(op='eq',field='original_coupon_eligible',value=True,evidence='Original coupon eligibility'))
    if coupon.get('condition_tree'):
        nodes.append(coupon['condition_tree'])
    return evaluate_tree(dict(op='all',conditions=nodes),facts) if nodes else Decision('eligible',['No additional restriction was identified; provider acceptance is still required'])
