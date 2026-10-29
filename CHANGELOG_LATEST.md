# Latest completed phase

## Phase 2 — Playbooks and parser

- Added all eight playbook definitions under `api/core/playbooks/` with a
  validated registry that rejects unknown keys and incomplete event flags.
- Implemented `POST /api/analysis/parse` with Gemini structured output,
  `default_symbol` resolution, ISO and `DD.MM.YYYY` date normalization, and
  422 rejection of strategies with more than two legs.
- Classified vertical spreads from the lower-strike leg, with tests for all four
  spreads, all four single legs, and the differing-expiration case.
- Verified 37 backend tests pass
  (`python -m unittest discover -s api -p "test_*.py"`) and 2 Angular tests pass
  (`npm test`).
- Acceptance evidence for 2026-10-29: `sell 732 put and buy 729 put XSP
  2026-11-20` resolves to `bull_put_spread`; `buy call SPY 600` returns exactly
  `missing_fields: ["expiration"]`. Gemini calls are covered by mocked contract
  tests; no live model call was recorded.

## Previous

- Phase 1 — CBOE provider and schemas: live SPY chain with delta, IV, bid, ask,
  open interest, `source: "cboe_delayed"`, and `as_of`.
