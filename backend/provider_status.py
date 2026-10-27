"""Classify public failures without turning an access error into 'no flights'."""
import re


class ProviderError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code=code


def page_problem(text, url='', responses=()):
    text=text.lower().strip()
    denied=any(status in (401,403,429) and re.search(r'itinerary/create|flight/search|listing|review',path,re.I)
               for path,status in responses)
    if denied:
        return ProviderError('ACCESS_DENIED','Provider refused the search/booking request (HTTP 401/403/429). Final price unavailable; manual provider access may be needed.')
    if 'network problem' in text or 'unable to connect to our systems' in text:
        return ProviderError('PROVIDER_NETWORK','Provider displays a network/system connection error. This does not mean the route has no flights.')
    if '/itinerary/failure' in url or 'server error' in text:
        return ProviderError('BOOKING_FAILED','Provider could not create the itinerary and displayed its error page. No payment total was verified.')
    if text in ('200-ok','200 ok','access denied') or re.search(r'verify (?:you are|that you)|unusual traffic|temporarily blocked',text):
        return ProviderError('ACCESS_DENIED','Provider returned an access/verification page instead of flight results. Manual provider access is needed.')
    if re.search(r'\bno (?:flights|results) (?:found|available)\b',text):
        return ProviderError('NO_INVENTORY','Provider explicitly reports no flights for this search.')
    return None
