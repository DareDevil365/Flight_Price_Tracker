import pytest
import sys
import os

# Add backend to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from savings_stacker import calculate_net_emi_savings

def test_non_emi_coupon():
    # A standard coupon should not incur any interest cost or warnings
    net, interest, warning = calculate_net_emi_savings(
        coupon_code="MMTDEAL",
        coupon_desc="Flat Rs. 500 off on all domestic flights",
        requires_emi=False,
        base_price=6000.0,
        face_discount=500.0
    )
    assert net == 500.0
    assert interest == 0.0
    assert warning == ""

def test_standard_emi_coupon():
    # An EMI coupon should calculate reducing interest cost
    # Base price: 6000, Face discount: 1000 -> Principal: 5000
    # Interest for 6 months at 14% p.a. on 5000 is approx 206 Rs
    # Net savings: 1000 - 206 = 794 Rs
    net, interest, warning = calculate_net_emi_savings(
        coupon_code="AXISEMI",
        coupon_desc="Flat Rs. 1000 off on Axis Bank EMI",
        requires_emi=True,
        base_price=6000.0,
        face_discount=1000.0
    )
    assert interest > 0.0
    assert interest < 300.0
    assert net == 1000.0 - interest
    assert "EMI Offer:" in warning
    assert f"Net savings is ₹{net:.0f}." in warning

def test_no_cost_emi_coupon():
    # A No-Cost EMI coupon should have true net savings of 0
    # and interest cost equal to the face discount
    net, interest, warning = calculate_net_emi_savings(
        coupon_code="IDFCNOCOSTEMI",
        coupon_desc="No-cost EMI on IDFC cards",
        requires_emi=True,
        base_price=6000.0,
        face_discount=1000.0
    )
    assert interest == 1000.0
    assert net == 0.0
    assert "No-Cost EMI:" in warning
    assert "True savings is ₹0." in warning
