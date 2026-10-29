# Latest completed phase

## Phase 3 — Analysis pipeline and metrics

- Added `POST /api/analysis/run` with request validation for a single option or
  a two-leg vertical spread, rejecting unsupported legs with `422`.
- Added deterministic calculations in `api/core/metrics.py`: signed net
  credit/debit, bounded and unbounded outcomes, breakeven, delta-implied
  probability, daily theta, worst-leg liquidity, event flags, and the 1-sigma
  expected move. Dollar values are per one contract per leg.
- Added the deterministic header (short/long order for spreads), the fixed
  disclaimer, and the answer language.
- Added one Gemini synthesis call in `api/agent/graph.py`; `iv_rank` is `null`
  with a warning until a historical IV source exists.
- Fixed CBOE index handling found during live verification: `XSP` now maps to
  `_XSP`, and index payloads that echo `^XSP` in `data.symbol` are accepted.
- Verified 57 backend tests pass
  (`python -m unittest discover -p "test_*.py"`) and 2 Angular tests pass
  (`npm test`).
- Acceptance evidence for 2026-10-29: the mocked bull put spread analysis
  returns `Bull Put Spread SPY 732/729 2026-11-20`, net credit 150.00, max
  profit 150.00, max loss 150.00, breakeven 730.50, probability 0.70, theta
  5.00/day, and exactly one Gemini call. `422`, `429`, `502`, and `503` paths
  are covered. A live deterministic check of `XSP 732/729 2026-11-20` returned
  net credit 21.00, max loss 279.00, breakeven 731.79, probability 0.8758, and
  theta 0.72/day. Gemini synthesis is mocked; no live model call was recorded.

## Previous

- Phase 2 — Playbooks and parser: eight playbooks, deterministic vertical
  classification, and Gemini structured parsing with mocked contract tests.
- Phase 1 — CBOE provider and schemas: live SPY chain with delta, IV, bid, ask,
  open interest, `source: "cboe_delayed"`, and `as_of`.
