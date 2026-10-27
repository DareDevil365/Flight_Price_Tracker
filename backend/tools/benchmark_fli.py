"""Isolated public Fli benchmark; never writes quotes into the application database."""
import argparse
import json
from pathlib import Path
import time
from importlib.metadata import version
from fli.models import FlightSearchFilters
from fli.models.google_flights.base import PassengerInfo, FlightSegment, SeatType
from fli.models.airport import Airport
from fli.search import SearchFlights

parser=argparse.ArgumentParser()
parser.add_argument('--label',default='published')
parser.add_argument('--source-revision',default=None,help='Exact upstream revision when running from a checkout')
args=parser.parse_args()
cases=[('JAI','BLR','2026-11-08',1,'ECONOMY'),('BOM','HYD','2026-11-15',1,'ECONOMY'),
       ('HYD','BOM','2027-02-08',1,'ECONOMY'),('MAA','DEL','2027-02-18',1,'ECONOMY'),
       ('PNQ','GOX','2026-11-22',1,'ECONOMY'),('BLR','JAI','2027-02-12',1,'ECONOMY'),
       ('DEL','MAA','2026-11-25',2,'ECONOMY'),('BOM','DEL','2027-02-21',1,'BUSINESS')]
reports=[]
for origin,dest,day,adults,cabin in cases:
    start=time.monotonic()
    report=dict(origin=origin,destination=dest,day=day,adults=adults,cabin=cabin,installed_distribution_version=version('flights'),source_revision=args.source_revision)
    try:
        filters=FlightSearchFilters(passenger_info=PassengerInfo(adults=adults),seat_type=SeatType[cabin],
            flight_segments=[FlightSegment(departure_airport=[[Airport[origin],0]],arrival_airport=[[Airport[dest],0]],travel_date=day)])
        rows=SearchFlights().search(filters,currency='INR',language='en',country='IN') or []
        report['results']=[f.model_dump(mode='json',exclude={'booking_token'}) for f in rows]
        report['count']=len(rows)
    except Exception as exc:
        report['error']=str(exc)[:600]
    report['seconds']=round(time.monotonic()-start,2)
    reports.append(report)
    print(json.dumps({k:v for k,v in report.items() if k!='results'}),flush=True)
    folder=Path(__file__).resolve().parents[2]/'sessions'/'fli-benchmark'
    (folder/(args.label+'.json')).write_text(json.dumps(reports,indent=2),encoding='utf-8')
