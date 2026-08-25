# Reference data

- `fdd-registration-portals.csv` — reconstructed from the handoff spec's
  state-by-state portal notes (15 rows, all 14 FDD states + FRED).
- `franchisor-seed-list.csv` — the 10 seed QSR brands named in the spec.
- `wendys-top50-multiunit-franchisees.csv` — proof-of-concept parse output,
  provided by the user (pulled from the WI Wendy's FDD filing referenced in
  the handoff spec: 5,943 outlet rows / 576 distinct franchisee entities
  overall). This file itself is a derived top-50 summary: each row is a
  (franchisee, state) pair ranked by `number_of_units` in that state — e.g.
  `HAZA FOODS, LLC` appears on three rows (TX/126, LA/85, and via its
  `HAZA FOODS OF NORTHEAST, LLC` / `HAZA FOODS OF MINNESOTA LLC` affiliates
  in OH/NY/MN), not a single row per distinct legal entity. Useful for
  validating the row/field shape a Step 3.5+ rollup should produce
  (`franchisor_name, legal_franchisee_name, number_of_units, state`), but
  not itself the full 576-entity Item 20 parse.
