from types import SimpleNamespace

from app.payments import pricing_region_for_request, public_pricing


def request_with_country(country_code: str):
    return SimpleNamespace(headers={"cf-ipcountry": country_code})


def test_pricing_region_uses_india_for_in_country_code():
    assert pricing_region_for_request(request_with_country("IN")) == "india"


def test_pricing_region_uses_international_for_other_country_codes():
    assert pricing_region_for_request(request_with_country("US")) == "international"


def test_public_pricing_returns_regional_prices():
    assert public_pricing("india")["personal_plans"][1]["price"] == "₹499"
    assert public_pricing("international")["personal_plans"][1]["price"] == "$20"
