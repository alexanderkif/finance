# Python API instructions

Extends [../AGENTS.md](../AGENTS.md). Run Python commands from `api/` unless a
command says otherwise.

## Toolchain

- Python `>=3.14`; manage dependencies with `uv` (`uv sync`, `uv lock`).
- Ruff for linting and import order (config: [../ruff.toml](../ruff.toml)).
- Pyright in `basic` mode for type checking; Pylance uses the same settings in
  VS Code (`../pyrightconfig.json`).
- Tests use the standard `unittest` runner.

```powershell
uv run ruff check .
uv run pyright
uv run python -m unittest discover -s tests -t . -p "test_*.py"
```

From the repository root, the test command is:

```powershell
api\.venv\Scripts\python.exe -m unittest discover -s api\tests -t api -p "test_*.py"
```

## Layout

```text
api/
├── index.py        # FastAPI app and lifespan
├── settings.py     # environment keys; read server-side only
├── mcp_dev.py      # development-only MCP bridge
├── routers/        # HTTP routing and request/response validation
├── core/           # providers, deterministic metrics, parsing, guardrails
├── agent/          # LLM orchestration and prompts
└── tests/          # unittest API and unit tests
```

Keep routing, provider access, deterministic calculations, and LLM
orchestration in their respective modules. Tests import application modules
with `api/` as the import root, so `from core...`, `from routers...`, and
`from index import app` remain valid.

## Style and correctness

- Follow PEP 8 and PEP 257; keep lines to the configured 88 characters.
- Annotate public functions and return types. Prefer PEP 604 unions
  (`float | None`) and builtin generics (`list[str]`).
- Validate untrusted input at API and LLM boundaries with Pydantic models.
- Avoid `Any` in application code. Test payload builders may use `Any` when
  mutating nested JSON fixtures.
- Keep financial arithmetic deterministic and outside prompts. Never
  fabricate provider data.
- Raise typed exceptions in `core/` and translate them to `HTTPException` in
  routers.
- Never log or return API keys or internal prompts.
- Add or update tests for changed behavior; do not add working-looking stubs
  for unimplemented work.

## References

- Python: <https://docs.python.org/3/>
- Typing: <https://typing.python.org/en/latest/>
- PEP 8: <https://peps.python.org/pep-0008/>
- PEP 257: <https://peps.python.org/pep-0257/>
- `unittest`: <https://docs.python.org/3/library/unittest.html>
- FastAPI: <https://fastapi.tiangolo.com/>
- Pydantic: <https://docs.pydantic.dev/>
- uv: <https://docs.astral.sh/uv/>
- Ruff: <https://docs.astral.sh/ruff/>
- Pyright: <https://microsoft.github.io/pyright/>

The `finance-api` MCP server in `../opencode.json` already exposes this API's
tools for development. Use Pylance/Pyright for Python code intelligence; the
repository does not ship a separate Python documentation MCP server.
