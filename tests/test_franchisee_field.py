from pipeline.parsing.franchisee_field import split_franchisee_field


def test_splits_legal_name_and_guarantors():
    legal, guarantors = split_franchisee_field("Sunrise Restaurant Group LLC; John Smith; Jane Smith")
    assert legal == "Sunrise Restaurant Group LLC"
    assert guarantors == ["John Smith", "Jane Smith"]


def test_no_guarantors():
    legal, guarantors = split_franchisee_field("Acme Foods Inc")
    assert legal == "Acme Foods Inc"
    assert guarantors == []


def test_does_not_drop_second_guarantor():
    # regression test for the earlier bug: dropping everything after the first ';'
    legal, guarantors = split_franchisee_field("A LLC; Guarantor One; Guarantor Two; Guarantor Three")
    assert legal == "A LLC"
    assert guarantors == ["Guarantor One", "Guarantor Two", "Guarantor Three"]


def test_empty_string():
    legal, guarantors = split_franchisee_field("")
    assert legal == ""
    assert guarantors == []
