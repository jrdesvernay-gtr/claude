from pipeline import db
from pipeline.parsing.handler_registry import HandlerRegistry, fingerprint_signature
from tests.fake_supabase import FakeSupabaseClient


def dummy_fn(item_20_text):
    return []


def test_fingerprint_signature_drops_row_count():
    # data_line_count is a specific filing's row count, not part of what
    # identifies "this is the same table format" -- must not be part of
    # the signature two different filings' fingerprints are compared on.
    fp1 = {"delimiter": "tab", "data_line_count": 5943, "has_semicolon_franchisee_field": True}
    fp2 = {"delimiter": "tab", "data_line_count": 12, "has_semicolon_franchisee_field": True}
    assert fingerprint_signature(fp1) == fingerprint_signature(fp2)


def test_agent_drafted_handler_is_findable_again_for_same_format_different_row_count():
    # Confirmed live: an earlier version never set matches() on an
    # agent-drafted handler at all (defaulted to always-False), so it could
    # never be found again via find_match() -- every filing re-drafted from
    # scratch even within the same process, regardless of matching format.
    registry = HandlerRegistry()
    fp_first_filing = {"delimiter": "tab", "data_line_count": 5943, "has_semicolon_franchisee_field": True}
    registry.register_agent_drafted(
        handler_id="wi_agent_drafted_abc123",
        state="WI",
        description="test handler",
        fn=dummy_fn,
        fingerprint=fingerprint_signature(fp_first_filing),
        fn_source="def parse(item_20_text):\n    return []\n",
    )

    fp_second_filing = {"delimiter": "tab", "data_line_count": 217, "has_semicolon_franchisee_field": True}
    found = registry.find_match("WI", fp_second_filing)
    assert found is not None
    assert found.id == "wi_agent_drafted_abc123"


def test_agent_drafted_handler_does_not_match_a_different_format():
    registry = HandlerRegistry()
    registry.register_agent_drafted(
        handler_id="wi_agent_drafted_abc123",
        state="WI",
        description="test handler",
        fn=dummy_fn,
        fingerprint=fingerprint_signature({"delimiter": "tab", "data_line_count": 5943, "has_semicolon_franchisee_field": True}),
        fn_source="def parse(item_20_text):\n    return []\n",
    )
    different_format = {"delimiter": "fixed_width", "data_line_count": 100, "has_semicolon_franchisee_field": False}
    assert registry.find_match("WI", different_format) is None


def test_register_persisted_preserves_earned_probation_state():
    # Unlike register_agent_drafted() (always starts a fresh probation
    # period), reloading a persisted handler must keep the probation state
    # it actually earned -- otherwise a handler that already proved itself
    # would restart probation every time the process restarts.
    registry = HandlerRegistry()
    registry.register_persisted(
        handler_id="wi_agent_drafted_proven",
        state="WI",
        description="already proven",
        fn=dummy_fn,
        fingerprint={"delimiter": "tab", "has_semicolon_franchisee_field": True},
        fn_source="def parse(item_20_text):\n    return []\n",
        probation_runs_remaining=0,
        confidence_score=1.0,
    )
    h = registry.get("wi_agent_drafted_proven")
    assert h.probation_runs_remaining == 0
    assert h.confidence_score == 1.0


def test_load_persisted_handlers_reconstitutes_and_finds_by_signature():
    client = FakeSupabaseClient()
    client.table("handler_registry").insert(
        {
            "id": "wi_agent_drafted_reload_me",
            "state": "WI",
            "description": "persisted handler",
            "source": "agent_drafted",
            "probation_runs_remaining": 1,
            "confidence_score": 0.85,
            "fingerprint": {"delimiter": "comma", "has_semicolon_franchisee_field": True},
            "fn_source": (
                "def parse(item_20_text):\n"
                "    return [{'franchisee_raw': line} for line in item_20_text.splitlines() if line]\n"
            ),
        }
    ).execute()

    loaded_count = db.load_persisted_handlers(client)
    assert loaded_count == 1

    from pipeline.parsing.handler_registry import registry

    # delimiter="comma" doesn't match wi_standard_v1 (tab-only), so this can
    # only resolve to the reloaded handler.
    fingerprint = {"delimiter": "comma", "data_line_count": 3, "has_semicolon_franchisee_field": True}
    handler = registry.find_match("WI", fingerprint)
    assert handler is not None
    assert handler.id == "wi_agent_drafted_reload_me"
    assert handler.probation_runs_remaining == 1
    rows = handler.fn("Alpha LLC\nBeta LLC\n")
    assert [r.franchisee_raw for r in rows] == ["Alpha LLC", "Beta LLC"]


def test_load_persisted_handlers_skips_a_handler_that_no_longer_compiles():
    client = FakeSupabaseClient()
    client.table("handler_registry").insert(
        {
            "id": "wi_agent_drafted_broken",
            "state": "WI",
            "description": "broken handler",
            "source": "agent_drafted",
            "probation_runs_remaining": 2,
            "confidence_score": 0.7,
            "fingerprint": {"delimiter": "comma", "has_semicolon_franchisee_field": False},
            "fn_source": "this is not valid python at all {{{",
        }
    ).execute()

    assert db.load_persisted_handlers(client) == 0
