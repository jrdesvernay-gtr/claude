from pipeline import db
from pipeline.models import FddFiling, FranchiseeCandidate, ItemRow
from tests.fake_supabase import FakeSupabaseClient


def test_upsert_franchisor_creates_then_reuses():
    client = FakeSupabaseClient()
    id1 = db.upsert_franchisor(client, "Wendy's", "https://www.wendys.com")
    id2 = db.upsert_franchisor(client, "Wendy's")
    assert id1 == id2
    assert len(client.data["franchisors"]) == 1


def test_insert_fdd_filing_upserts_on_unique_key():
    client = FakeSupabaseClient()
    franchisor_id = db.upsert_franchisor(client, "Wendy's")
    filing = FddFiling(franchisor_name="Wendy's", state="WI", source_url="http://x", parsed_row_count=2)
    id1 = db.insert_fdd_filing(client, filing, franchisor_id)
    id2 = db.insert_fdd_filing(client, filing, franchisor_id)
    assert id1 == id2
    assert len(client.data["fdd_filings"]) == 1


def test_upsert_franchisee_insert_then_merge():
    client = FakeSupabaseClient()
    candidate = FranchiseeCandidate(legal_name="Sunrise Restaurant Group LLC", guarantor_names=["John Smith"])
    fid = db.upsert_franchisee(client, candidate)
    assert len(client.data["franchisees"]) == 1
    assert client.data["franchisees"][0]["guarantor_names"] == ["John Smith"]

    # merging onto the existing row should not clobber legal_name with an empty update
    merged_id = db.upsert_franchisee(client, FranchiseeCandidate(legal_name="Sunrise Restaurant Group LLC"), franchisee_id=fid)
    assert merged_id == fid
    assert len(client.data["franchisees"]) == 1


def test_insert_units_requires_matching_lengths():
    client = FakeSupabaseClient()
    rows = [ItemRow(franchisee_raw="A LLC")]
    try:
        db.insert_units(client, rows, "filing-1", "franchisor-1", [])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on mismatched lengths")


def test_insert_units_writes_all_rows():
    client = FakeSupabaseClient()
    rows = [ItemRow(franchisee_raw="A LLC"), ItemRow(franchisee_raw="B LLC")]
    db.insert_units(client, rows, "filing-1", "franchisor-1", ["fr-1", "fr-2"])
    assert len(client.data["units"]) == 2
    assert client.data["units"][0]["franchisee_raw"] == "A LLC"
    assert client.data["units"][1]["franchisee_id"] == "fr-2"
