import pytest
import sys
import os

# Add backend to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler import (
    is_domestic_route, 
    is_international_only_coupon, 
    is_domestic_only_coupon,
    is_flight_coupon
)

def test_route_classification():
    # Domestic Indian routes
    assert is_domestic_route("DEL", "BOM") is True
    assert is_domestic_route("BOM", "BLR") is True
    assert is_domestic_route("HYD", "MAA") is True
    
    # International routes
    assert is_domestic_route("DEL", "DXB") is False
    assert is_domestic_route("JFK", "LHR") is False
    assert is_domestic_route("BOM", "SIN") is False

def test_coupon_classification():
    # International-only coupons (should be True for intl, False for domestic)
    assert is_international_only_coupon("VIDESH", "Flat 10% off up to Rs. 5000 on international flights") is True
    assert is_domestic_only_coupon("VIDESH", "Flat 10% off up to Rs. 5000 on international flights") is False
    
    assert is_international_only_coupon("PARDES", "Book international flight and get flat Rs. 2500 discount") is True
    assert is_domestic_only_coupon("PARDES", "Book international flight and get flat Rs. 2500 discount") is False

    # Domestic-only coupons (should be False for intl, True for domestic)
    assert is_international_only_coupon("MMTDEAL", "Flat Rs. 500 off on all domestic flights") is False
    assert is_domestic_only_coupon("MMTDEAL", "Flat Rs. 500 off on all domestic flights") is True
    
    assert is_international_only_coupon("EASEFLY", "Rs. 300 off on domestic flight bookings") is False
    assert is_domestic_only_coupon("EASEFLY", "Rs. 300 off on domestic flight bookings") is True

    # Generic or dual-purpose coupons (should be True/True or False/False)
    assert is_international_only_coupon("EMTDOCTOR", "Get 5% discount (max Rs. 3000) on domestic or international flights") is True
    assert is_domestic_only_coupon("EMTDOCTOR", "Get 5% discount (max Rs. 3000) on domestic or international flights") is True

    assert is_international_only_coupon("MMTDEALICICI", "Up to Rs. 1,500 off on ICICI Credit Cards") is False
    assert is_domestic_only_coupon("MMTDEALICICI", "Up to Rs. 1,500 off on ICICI Credit Cards") is False

def test_flight_coupon_filtering():
    # Valid flight coupons
    assert is_flight_coupon("EASEFLY", "Rs. 300 off on domestic flight bookings") is True
    assert is_flight_coupon("MMTDEAL", "Flat Rs. 500 off on all domestic flights") is True
    assert is_flight_coupon("CTDOM", "Discount Up To Rs 25% OFF Maximum Discount up to Rs 5000") is True
    
    # Non-flight coupons
    assert is_flight_coupon("WELCOMEMMT", "Flat 25% OFF on domestic hotel bookings") is False
    assert is_flight_coupon("MMTBUSGRAB", "Travel now to your favourite destinations on a bus") is False
    assert is_flight_coupon("NOCF", "Book your bus journey on Paytm with ease Enjoy 100% free cancel") is False
    assert is_flight_coupon("RECHDOMINOS", "Flat 20% OFF Up To Rs 100 on Dominos Orders") is False
    assert is_flight_coupon("TAKEITALL", "Get Rs 100 cashback on a successful mobile recharge") is False
    assert is_flight_coupon("BUSOTT", "Travel in a bus at the best prices Also, get 38+ OTT subscription") is False

def test_is_coupon_airline_match():
    from dispatcher import is_coupon_airline_match
    
    # 1. Coupon doesn't mention airline -> globally applicable
    assert is_coupon_airline_match("Flat Rs 500 off on all flight bookings", "IndiGo") is True
    assert is_coupon_airline_match("Flat Rs 500 off on all flight bookings", "SpiceJet") is True
    
    # 2. Coupon mentions IndiGo
    assert is_coupon_airline_match("Flat 10% off on IndiGo flights", "IndiGo") is True
    assert is_coupon_airline_match("Flat 10% off on IndiGo flights", "6E-201") is True
    assert is_coupon_airline_match("Flat 10% off on IndiGo flights", "SpiceJet") is False
    
    # 3. Coupon mentions SpiceJet or Akasa
    assert is_coupon_airline_match("Get Rs. 1000 off on SpiceJet & Akasa Air bookings", "SpiceJet") is True
    assert is_coupon_airline_match("Get Rs. 1000 off on SpiceJet & Akasa Air bookings", "Akasa Air") is True
    assert is_coupon_airline_match("Get Rs. 1000 off on SpiceJet & Akasa Air bookings", "IndiGo") is False

