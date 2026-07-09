from app.services.site_onboarding_scraper import _extract_facts


def test_extracts_south_african_parenthesized_phone_and_address():
    text = (
        "Busamed Gateway Private Hospital\n"
        "URL: https://maps.apple.com/place?place-id=I651D27612BF56652\n"
        "Phone. +27 (31) 492-1130\n"
        "Address. 36-38 Aurora Drive. Umhlanga Rocks. Umhlanga. KZN. 4319.\n"
    )

    facts = _extract_facts(text)

    assert facts["contact_phone"] == "+27 31 492 1130"
    assert facts["whatsapp_phone"] == "+27 31 492 1130"
    assert facts["address"] == "36-38 Aurora Drive. Umhlanga Rocks. Umhlanga. KZN. 4319"
