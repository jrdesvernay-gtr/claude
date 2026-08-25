from pipeline.models import FddFiling, ItemRow
from pipeline.orchestrator import load_filing_to_db
from tests.fake_supabase import FakeSupabaseClient


def test_review_flagged_filing_writes_no_units():
    client = FakeSupabaseClient()
    filing = FddFiling(
        franchisor_name="Wendy's", state="WI", source_url="http://x",
        parsed_row_count=2, table1_outlet_count=99, table1_match=False, review_flag=True,
    )
    rows = [ItemRow(franchisee_raw="A LLC"), ItemRow(franchisee_raw="B LLC")]

    fdd_filing_id = load_filing_to_db(client, "Wendy's", "https://www.wendys.com", filing, rows)

    assert fdd_filing_id is not None
    assert client.data["fdd_filings"][0]["review_flag"] is True
    assert "units" not in client.data or client.data["units"] == []
    assert "franchisees" not in client.data or client.data["franchisees"] == []


def test_clean_filing_loads_units_and_resolves_franchisees():
    client = FakeSupabaseClient()
    filing = FddFiling(
        franchisor_name="Wendy's", state="WI", source_url="http://x",
        parsed_row_count=2, table1_outlet_count=2, table1_match=True, review_flag=False,
    )
    rows = [
        ItemRow(franchisee_raw="Sunrise Restaurant Group LLC; John Smith", city="Madison", state="WI"),
        # near-duplicate of the same entity -> should auto-merge onto the same franchisee row
        ItemRow(franchisee_raw="Sunrise Restaurant Group, LLC", city="Green Bay", state="WI"),
    ]

    load_filing_to_db(client, "Wendy's", "https://www.wendys.com", filing, rows)

    assert len(client.data["units"]) == 2
    assert len(client.data["franchisees"]) == 1  # both rows resolved to the same entity
    franchisee = client.data["franchisees"][0]
    assert franchisee["guarantor_names"] == ["John Smith"]
    unit_franchisee_ids = {u["franchisee_id"] for u in client.data["units"]}
    assert unit_franchisee_ids == {franchisee["id"]}
