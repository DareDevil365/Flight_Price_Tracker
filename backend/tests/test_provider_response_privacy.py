"""Provider response observers retain criteria/status metadata, never API bodies."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from workers.cleartrip_worker import CleartripWorker
from workers.easemytrip_worker import EaseMyTripWorker
from workers.makemytrip_worker import MakeMyTripWorker


QUERY='from=BLR&to=LKO&depart_date=23%2F02%2F2027&adults=1&class=Economy'
URL='https://www.cleartrip.com/flight/search/v2?'+QUERY


def response(url,status=200):
    return SimpleNamespace(url=url,status=status,json=AsyncMock(side_effect=AssertionError('Body must not be read')))


@pytest.mark.asyncio
@pytest.mark.parametrize('worker_class,url',[
    (MakeMyTripWorker,'https://www.makemytrip.com/api/listing'),
    (EaseMyTripWorker,'https://flight.easemytrip.com/FlightList/GetFlight'),
    (CleartripWorker,URL),
])
async def test_repeated_responses_never_decode_or_accumulate_bodies(worker_class,url):
    worker=worker_class();observed=response(url)
    for _ in range(150):
        await worker._response_handler(observed)
    observed.json.assert_not_awaited()
    assert worker._intercepted_responses==[]
    assert not worker._interception_event.is_set()


@pytest.mark.asyncio
async def test_cleartrip_keeps_only_successful_exact_search_criteria():
    worker=CleartripWorker()
    await worker._response_handler(response(URL+'&email=private%40example.invalid&token=secret'))
    assert worker._confirmed_criteria==dict(
        **{'from':'BLR','class':'Economy'},to='LKO',depart_date='23/02/2027',adults='1')


@pytest.mark.asyncio
@pytest.mark.parametrize('url,status',[
    (URL,403),
    (URL,302),
    (URL+'&from=DEL',200),
    (URL.replace('&adults=1',''),200),
    (URL.replace('class=Economy','class='),200),
    (URL+'&'+('&'.join('x=1' for _ in range(101))),200),
    (URL+'&x='+('x'*8192),200),
])
async def test_failed_or_ambiguous_search_cannot_confirm_previous_criteria(url,status):
    worker=CleartripWorker();worker._confirmed_criteria={'from':'BLR'}
    observed=response(url,status)
    await worker._response_handler(observed)
    assert worker._confirmed_criteria is None
    observed.json.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('url',[
    URL.replace('https:','http:'),
    URL.replace('www.cleartrip.com','www.cleartrip.com.evil.invalid'),
    URL.replace('www.cleartrip.com','www.cleartrip.com:444'),
    URL.replace('www.cleartrip.com','user@www.cleartrip.com'),
    URL.replace('/flight/search/v2','/flight/benefits'),
])
async def test_unrelated_origins_and_paths_do_not_change_criteria(url):
    worker=CleartripWorker();worker._confirmed_criteria={'from':'BLR'}
    await worker._response_handler(response(url))
    assert worker._confirmed_criteria=={'from':'BLR'}
