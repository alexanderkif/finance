from typing import Final

SYNTHESIS_SYSTEM_INSTRUCTION: Final = (
    "You write a short educational options assessment. "
    "Use only the facts and numbers supplied in the request; never calculate new "
    "values and never invent market data. "
    "Answer in the requested language. "
    "Do not define or teach the strategy, and do not give trade instructions. "
    "Do not present the text as financial advice. Keep it under 180 words."
)

SYNTHESIS_RESPONSE_SCHEMA: Final[dict[str, object]] = {
    "type": "OBJECT",
    "properties": {"recommendation": {"type": "STRING"}},
    "required": ["recommendation"],
}
