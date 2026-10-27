"""Explicit after-search exclusions. Never infer that a user owns a card."""
import re


def parse_feedback(text):
    from financial_text import financial_instructions
    parsed=financial_instructions(text)
    if not any(parsed[key] for key in ('blacklisted_banks','excluded_card_names','only_upi','block_emi','block_bnpl')):
        raise ValueError('Could not enforce that restriction. Use “I don’t have HDFC”, “exclude Flipkart Axis”, “no EMI”, or “only UPI”. Change dates/cabin in flight search, or use Explore to compare alternatives.')
    return {key:parsed[key] for key in ('blacklisted_banks','excluded_card_names','only_upi','block_emi','block_bnpl')}


def merge_feedback(financial,feedback):
    rules=dict(financial)
    for key in ('blacklisted_banks','excluded_card_names'):
        rules[key]=list(dict.fromkeys([*rules.get(key,[]),*feedback[key]]))
    if feedback['only_upi']:
        rules['allowed_card_types']=['UPI']
    if feedback['block_emi']: rules['allow_emi']=False
    if feedback['block_bnpl']: rules['allow_bnpl']=False
    return rules


def available_result(row,rules,offers):
    meta=row.get('savings_breakdown',{})
    if meta.get('integrity',{}).get('status')=='flagged':
        return False
    if meta.get('verification')!='checkout':
        return True
    selected=meta.get('selected_payment',{})
    if set(selected.get('banks',[])).intersection(rules.get('blacklisted_banks',[])):
        return False
    if rules.get('allowed_card_types') and selected.get('method') not in rules['allowed_card_types']:
        return False
    label=re.sub(r'[^A-Z0-9]','',str(selected.get('label') or '').upper())
    for product in rules.get('excluded_card_names',[]):
        if re.sub(r'[^A-Z0-9]','',product.upper()) in label:
            return False
    code=row.get('best_coupon_code')
    if code:
        from financial_filter import FinancialFilter
        offer=next((c for c in offers if c['code']==code and c['platform']==row['platform']),None)
        if not offer or FinancialFilter().assess(offer,{**rules,'selected_payment':selected,
                'booking_total':row.get('base_price')}).status!='eligible':
            return False
    return True
