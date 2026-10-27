"""Small explicit financial grammar; never turn a negation into card ownership."""
import re
from offer_parser import BANKS, card_product


def financial_instructions(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError('Enter a short payment restriction.')
    text = text.upper().replace('’', "'")
    result = dict(blacklisted_banks=[], whitelisted_banks=[], excluded_card_names=[],
                  owned_card_names=[], only_upi=False, block_emi=False, block_bnpl=False)
    action = None
    for clause in re.split(r'[,;.!\n]|\b(?:BUT|AND|OR|ALSO)\b', text):
        clause = clause.strip()
        if not clause:
            continue
        denied = bool(re.search(r"\b(?:DON'?T HAVE|DO NOT HAVE|HAVE NO|DO NOT OWN|DON'?T OWN|NO|WITHOUT|EXCLUDE|SKIP|IGNORE|BLOCK|CANNOT USE|CAN'T USE)\b", clause))
        owned = bool(re.search(r'\b(?:HAVE|HOLD|OWN|USE)\b', clause)) and not denied
        if denied:
            action = 'exclude'
        elif owned:
            action = 'own'
        banks = [bank for bank in BANKS if re.search(r'\b'+re.escape(bank)+r'\b', clause)]
        product = card_product(clause)
        upi = bool(re.search(r'\b(?:ONLY UPI|UPI ONLY)\b', clause))
        emi = bool(re.search(r'\bEMI\b', clause))
        bnpl = bool(re.search(r'\bBNPL\b|\bPAY LATER\b', clause))
        if upi:
            if denied:
                raise ValueError('Conflicting UPI restriction. Use “only UPI”.')
            result['only_upi'] = True
        if emi or bnpl:
            if action != 'exclude':
                raise ValueError('Use “no EMI” or “no BNPL” to exclude these payments.')
            result['block_emi'] |= emi
            result['block_bnpl'] |= bnpl
        if banks or product:
            if action is None:
                raise ValueError('Say whether you own or exclude each named bank/card.')
            if product:
                result['excluded_card_names' if action == 'exclude' else 'owned_card_names'].append(product[0])
                banks = [bank for bank in banks if bank not in product[0]]
            result['blacklisted_banks' if action == 'exclude' else 'whitelisted_banks'].extend(banks)
        if not (banks or product or upi or emi or bnpl):
            raise ValueError('Unrecognized instruction. Use the search form for dates, times and flight requirements.')
        # Recognizing one bank must not silently accept unrelated flight rules.
        remainder = clause
        for bank in BANKS:
            remainder = re.sub(r'\b'+re.escape(bank)+r'\b', ' ', remainder)
        if product:
            for token in product[1]:
                remainder = re.sub(r'\b'+re.escape(token)+r'\b', ' ', remainder)
            remainder = re.sub(r'\b(?:SIMPLY SAVE|SIMPLY CLICK|TRAVEL ONE|BANK OF BARODA)\b', ' ', remainder)
        remainder = re.sub(r"\b(?:I|DO|NOT|DON'T|DONT|CAN'T|CANNOT|HAVE|HOLD|OWN|USE|NO|WITHOUT|EXCLUDE|SKIP|IGNORE|BLOCK|PLEASE|A|AN|ANY|THE|BANK|CARDS?|CREDIT|DEBIT|NET|BANKING|PAYMENT|ONLY|UPI|EMI|BNPL|PAY|LATER)\b", ' ', remainder)
        if re.search(r'[A-Z0-9]', remainder):
            raise ValueError('Part of that instruction cannot be enforced. Use the search form for other requirements.')
    for key in ('blacklisted_banks', 'whitelisted_banks', 'excluded_card_names', 'owned_card_names'):
        result[key] = list(dict.fromkeys(result[key]))
    if set(result['blacklisted_banks']) & set(result['whitelisted_banks']) or set(result['excluded_card_names']) & set(result['owned_card_names']):
        raise ValueError('The same bank/card is both owned and excluded. Clarify the restriction.')
    return result
