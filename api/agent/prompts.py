from typing import Final

SYNTHESIS_SYSTEM_INSTRUCTION: Final = (
    "You write a short educational options assessment. "
    "Use only the facts and numbers supplied in the request; never calculate new "
    "values and never invent market data. "
    "When present, current_iv is the current ATM implied volatility, hv_20d and "
    "hv_60d are annualized historical volatility, hv_rank is the percentile of "
    "current 20-day HV over the past year, and iv_hv_ratio compares current IV "
    "with HV. Never call hv_rank an IV rank. "
    "Recent headlines may be supplied as context; mention them only if "
    "relevant, never claim they caused a price move, and never invent an event "
    "or a date. Do not present news as a dividend, earnings, or splits calendar. "
    "Answer in the requested language. "
    "Do not define or teach the strategy, and do not give trade instructions. "
    "Do not present the text as financial advice. Keep it under 180 words."
)

SYNTHESIS_RESPONSE_SCHEMA: Final[dict[str, object]] = {
    "type": "OBJECT",
    "properties": {"recommendation": {"type": "STRING"}},
    "required": ["recommendation"],
}
