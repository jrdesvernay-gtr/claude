from pipeline.parsing.state_normalization import normalize_state


def test_already_valid_abbreviation_passes_through():
    assert normalize_state("AK") == "AK"
    assert normalize_state("ak") == "AK"


def test_full_state_name():
    assert normalize_state("NORTH CAROLINA") == "NC"
    assert normalize_state("North Carolina") == "NC"


def test_full_state_name_with_irregular_whitespace():
    assert normalize_state("NORTH   CAROLINA") == "NC"
    assert normalize_state("  Wisconsin  ") == "WI"


def test_combined_code_statename_format():
    # Confirmed live: Taco Bell's real format.
    assert normalize_state("AR-Arkansas") == "AR"
    assert normalize_state("AZ-Arizona") == "AZ"


def test_district_of_columbia_and_territories():
    assert normalize_state("District of Columbia") == "DC"
    assert normalize_state("Puerto Rico") == "PR"
    assert normalize_state("DC") == "DC"


def test_unrecognized_value_returns_none_rather_than_guessing():
    assert normalize_state("Not A Real State") is None
    assert normalize_state("XX") is None


def test_empty_or_none_returns_none():
    assert normalize_state(None) is None
    assert normalize_state("") is None
    assert normalize_state("   ") is None
