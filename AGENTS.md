# Repository instructions

This repository is intended to evolve into the Options Strategy Assistant in
[PRD.md](PRD.md). The current application is an Angular/FastAPI market
dashboard; treat the product documents as the target contract, not as evidence
that a feature already exists. Inspect the implementation before changing it.

## Workflow

- Keep changes within [PRD.md](PRD.md). For phase work, follow
  [PLAN.md](PLAN.md) and [TODO.md](TODO.md) in order; stop at each gate until
  its stated evidence is available.
- Load [ARCHITECTURE.md](ARCHITECTURE.md) when changing service boundaries,
  routing, or deployment; [DATA_CONTRACT.md](DATA_CONTRACT.md) for providers,
  market data, or degradation; [PLAYBOOK_SPEC.md](PLAYBOOK_SPEC.md) for
  strategies, parsing, or playbooks; [API_SPEC.md](API_SPEC.md) for endpoint
  behavior or schemas; and [src/AGENTS.md](src/AGENTS.md) when changing the
  Angular frontend.
- Keep each contract authoritative in its own document. Update directly
  related documentation and the phase tracker when behavior or phase status
  changes.
- A full rewrite or replacement of the existing application is allowed when
  it best meets the product contract. Do not preserve legacy code solely for
  backward compatibility; keep deployment behavior working or update and
  verify its configuration.
- Use the Google Gemini `gemini-3.1-flash-lite` model on the free tier for
  now. Read `GEMINI_API_KEY` from the server environment, using the local
  `.env.local` for development and deployment environment settings in
  production. Never expose or log the key in client code, responses, or docs.

## Product guardrails

- Do not present recommendations as financial advice. Analysis is educational.
- Keep all financial arithmetic deterministic and outside LLM prompts.
- Never fabricate market data or imply delayed data is real-time.
- Do not add authentication, accounts, a database, or WebSockets.
- Do not present placeholders as working implementations.
- Verify CBOE fields against the real provider payload and
  [DATA_CONTRACT.md](DATA_CONTRACT.md); do not guess field names. If in-scope
  work remains unimplemented, report it as incomplete and use
  `NotImplementedError("see TODO.md Phase N")` rather than a working-looking
  stub.

## Implementation conventions

- Follow the repository's configured Angular and Python versions and existing
  patterns. For Angular, favor standalone APIs, signals, typed forms, built-in
  template control flow, and accessible WCAG AA interactions.
- Keep TypeScript strict; avoid `any`. Use explicit types and validation at
  API boundaries.
- Validate changes with the smallest relevant configured test or build
  command. Add or update tests for changed behavior.
