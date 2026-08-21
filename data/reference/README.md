# Reference data

- `fdd-registration-portals.csv` — reconstructed from the handoff spec's
  state-by-state portal notes (15 rows, all 14 FDD states + FRED).
- `franchisor-seed-list.csv` — the 10 seed QSR brands named in the spec.
- `wendys-top50-multiunit-franchisees.csv` — **not included.** The handoff
  spec references this as an existing proof-of-concept parse output (5,943
  outlet rows / 576 distinct franchisee entities from the WI Wendy's
  filing), but the file itself was not found in the linked Drive folder and
  this environment's network egress to `apps.dfi.wi.gov` is blocked, so it
  could not be located or regenerated here. Two ways to unblock:
  1. Locate the original file and drop it in this directory, or
  2. Run `pipeline/orchestrator.find_filing_for_franchisor("Wendy's")` /
     `parse_item_20` against the live WI portal from an environment with
     network access, and confirm the WI portal selectors marked `TODO` in
     `pipeline/portals/wi.py` first.
