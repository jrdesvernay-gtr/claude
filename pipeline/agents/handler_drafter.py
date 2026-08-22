"""Agent 1: drafts a new Item 20 format handler when no registered handler
matches a filing's structural fingerprint (Step 3.4).

We ask the model for the function body only, sandbox-check and exec() it
(see handler_sandbox.py), and register the result on probation (see
handler_registry.register_agent_drafted) -- with a real fingerprint-based
matches() this time, and the raw source persisted, so it can actually be
found again and reused (pipeline.db.sync_handler_registry /
load_persisted_handlers), instead of every filing re-drafting from scratch.
"""
from __future__ import annotations

import uuid

from pipeline.agents.client import complete
from pipeline.agents.handler_sandbox import compile_handler_code, extract_code
from pipeline.parsing.handler_registry import HandlerFn, fingerprint_signature, registry

SYSTEM_PROMPT = """You draft Python parsers for Item 20 franchisee-outlet
tables extracted from Franchise Disclosure Document exhibits.

Write ONE function:

    def parse(item_20_text: str) -> list[dict]:
        ...

Each returned dict has keys: franchisee_raw (str, required), address, city,
state, zip, phone, status (all optional, default None).

Rules:
- Pure function only: no imports beyond `re`, no file I/O, no network calls,
  no exec/eval, no access to os/sys/subprocess.
- franchisee_raw must be the VERBATIM field as it appears (semicolon-
  delimited legal name + guarantor names) — do not split or truncate it,
  downstream code does that.
- Return [] if you can't parse a line; never raise on a single bad line.

Splitting address from city when there's no reliable delimiter between them
(a common real case: space-separated columns with no comma, tab, or other
punctuation marking the boundary) is the single most error-prone part of
this task. A naive split on the first digit-led token, or on a fixed word
count, gets it wrong most of the time -- confirmed live: real drafted
handlers have split a house number alone into `address` and dumped the rest
of the street name into `city` (e.g. "133 Southwest Drive Jonesboro" ->
address="133", city="Southwest Drive Jonesboro" -- wrong; the whole street
address is "133 Southwest Drive", city is "Jonesboro"), and separately split
a person's own two-word name across `franchisee_raw`/`address` (e.g.
"MICHAEL DAVIDSON 800 W NORTHERN LIGHTS BLVD" -> franchisee_raw="MICHAEL",
address="DAVIDSON 800 W NORTHERN LIGHTS BLVD" -- wrong; the name is "MICHAEL
DAVIDSON", the address starts at "800").

Use these anchors instead of guessing from position -- confirmed live, a
FIRST attempt at this guidance fixed the two examples above but broke a
different real case, Taco Bell's "408 State Highway 149 North Travel
Centers of America (PH K04060) Earle AR-Arkansas 72331" -> cutting right
after "Highway" gave address="408 State Highway", city="149 North Travel
Centers of America (PH K04060) Earle" -- wrong; a route/highway NUMBER
following the suffix word is still part of the street address, and a
site/location name between the street address and the real city (here,
"Travel Centers of America (PH K04060)") is not the city either. The
correct split is address="408 State Highway 149 North", city="Earle" (with
"Travel Centers of America (PH K04060)" having nowhere to go in this
schema -- fold it into `address` rather than misassign it as `city`).

- The state is the most reliable anchor: a 2-letter code, a full state
  name, or a combined "XX-Statename" token. Locate it first, then work
  BACKWARD from it -- don't split left-to-right by counting words or by
  the first delimiter you find.
- City is the LAST word or short phrase immediately before the state token
  -- a real municipality name, not a business/site name or a parenthetical.
  If there's ambiguous descriptive text between the street portion and the
  city (a site name, a mall/plaza name, a "(PH ######)" style code), that
  text isn't the city -- fold it into `address` instead, since there's no
  separate field for it in this schema. Default to putting uncertain
  middle text in `address`, never in `city`.
- The franchisee/entity field ends and the address begins at the first
  token that is a plain number (a house number) OR a token containing both
  letters and digits in an address-like pattern. A person's or company's
  name never starts with a bare number, so don't cut into it looking for
  one too early -- scan from the START of the line for the first such
  number-led token, not from a fixed word count.
- A street-type suffix word (ST, AVE, BLVD, RD, DR, HWY, HIGHWAY, PKWY, LN,
  CT, WAY, CIR, PL, TRL, PIKE, ROUTE, RTE, etc.) does NOT necessarily end
  the address -- if a number and/or a directional (N, S, E, W, NE, NW, SE,
  SW) immediately follows it (e.g. "Highway 149 North", "Route 66 West"),
  that's still part of the street address, not the city. A trailing
  suite/unit marker ("STE 100", "SUITE B", "#7", "UNIT 2") is also still
  part of the address if present.

Return ONLY the function source code, no prose, no markdown fences.
"""


def draft_handler(state: str, item_20_sample: str, fingerprint: dict) -> tuple[str, HandlerFn]:
    """Returns (handler_id, fn). Raises if the drafted code fails the
    sandboxing check or doesn't compile.
    """
    user_prompt = (
        f"State: {state}\n"
        f"Structural fingerprint: {fingerprint}\n\n"
        f"Sample Item 20 text (may be truncated):\n{item_20_sample[:6000]}"
    )
    # Confirmed live: messier, irregular formats (e.g. Taco Bell's combined
    # state field, optional phone, multi-word entity names) repeatedly made
    # the model spend its whole budget on internal reasoning and hit
    # max_tokens before emitting code, or before finishing it (Wendy's got
    # a real drafted function cut off mid-string). Raising max_tokens alone
    # wasn't a reliable fix -- client.complete()'s default effort="medium"
    # is the actual lever for thinking depth on this model; max_tokens is
    # raised too, to the ~16000 the Anthropic API guide recommends as a
    # non-streaming default, purely for extra headroom on top of that.
    raw = complete(SYSTEM_PROMPT, user_prompt, max_tokens=16000)
    code = extract_code(raw)
    fn = compile_handler_code(code, source_label=" (Agent 1 draft)")

    handler_id = f"{state.lower()}_agent_drafted_{uuid.uuid4().hex[:8]}"
    registry.register_agent_drafted(
        handler_id=handler_id,
        state=state,
        description=f"Agent-drafted handler for {state}, fingerprint={fingerprint}",
        fn=fn,
        fingerprint=fingerprint_signature(fingerprint),
        fn_source=code,
    )
    return handler_id, fn
