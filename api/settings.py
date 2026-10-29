import os
from pathlib import Path

from dotenv import load_dotenv

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(_REPOSITORY_ROOT / ".env.local", override=False)

GEMINI_MODEL = "gemini-3.1-flash-lite"


def require_gemini_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for Gemini requests.")
    return api_key
