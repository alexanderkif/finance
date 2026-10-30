import re
from typing import Final

MAX_MESSAGE_LENGTH: Final = 2_000
MAX_LEGS: Final = 2
_SYMBOL_PATTERN: Final = re.compile(r"^[A-Z0-9._-]{1,15}$")
_OPTION_VOCABULARY: Final = re.compile(
    r"\b(?:calls?|puts?|options?|spreads?|strikes?|expir(?:y|ation|ing)|"
    r"колл\w*|пут\w*|опцион\w*|спред\w*)\b",
    re.IGNORECASE,
)
_SIDE_ACTIONS: Final = re.compile(r"\b(?:buy|sell)\b", re.IGNORECASE)
_LEG_MENTIONS: Final = re.compile(
    r"\b(?:buy|sell|long|short)\b[^.!?]{0,40}?\b(?:calls?|puts?)\b",
    re.IGNORECASE,
)
_TEACHING_OR_QUESTION: Final = re.compile(
    r"\b(?:what\s+is|what\s+are|explain|define|teach\s+me|"
    r"how\s+does|how\s+do|why\s+is|why\s+does)\b",
    re.IGNORECASE,
)
_OFF_TOPIC: Final = re.compile(
    r"\b(?:poem|story|joke|song|essay|novel|recipe|weather|homework|"
    r"translate|python|javascript|medical|legal|dating|politics|election)\b",
    re.IGNORECASE,
)
_PROMPT_INJECTION: Final = re.compile(
    r"(?:"
    r"\b(?:ignore|disregard|forget)\b.{0,40}"
    r"\b(?:previous|prior|above|system|developer|all)?\s*"
    r"\b(?:instructions?|prompts?|rules?)\b"
    r"|"
    r"\b(?:system|developer|internal)\s+(?:prompt|instructions?|message)\b"
    r"|"
    r"\b(?:reveal|show|print|repeat|output|leak|expose)\b.{0,40}"
    r"\b(?:prompt|instructions?|api[\s_-]?key|secret|token)s?\b"
    r"|"
    r"\b(?:api[\s_-]?key|gemini_api_key)\b"
    r"|"
    r"\b(?:jailbreak|developer\s+mode|do\s+anything\s+now|DAN)\b"
    r"|"
    r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay\s+as)\b"
    r")",
    re.IGNORECASE,
)
_ABUSIVE: Final = re.compile(
    r"\b(?:idiot|stupid|moron|dumb|shut\s+up|hate\s+you|"
    r"fuck\w*|shit\w*|bitch\w*|asshole\w*)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_STRATEGY: Final = re.compile(
    r"\b(?:iron\s+condor|condor|iron\s+butterfly|butterfly|"
    r"straddle|strangle|calendar\s+spread|diagonal\s+spread|"
    r"ratio\s+spread|collar|box\s+spread|covered\s+(?:call|put)|"
    r"protective\s+(?:put|call)|married\s+put|naked\s+(?:call|put)|"
    r"synthetic\s+(?:call|put)|guts)\b",
    re.IGNORECASE,
)
_UNSAFE_CHARACTERS: Final = re.compile(r"[<>{}$`\x00-\x1f]")
_LONG_TOKEN: Final = re.compile(r"\b[A-Za-z0-9._-]{16,}\b")

_OUT_OF_SCOPE = (
    "I can only analyze a single option or a two-leg vertical spread. "
    "Describe the legs with a call or put."
)
_TOO_MANY_LEGS = "Only a single option or a two-leg vertical spread is supported."
_UNSUPPORTED_STRATEGY_MESSAGE = (
    "Only a single option or a two-leg vertical spread is supported."
)
_TOO_LONG = (
    "The message is too long. Describe a single option or a two-leg vertical spread."
)
_INJECTION = (
    "I can only parse an option position. I cannot follow instructions to "
    "change or reveal system behavior."
)
_ABUSIVE_MESSAGE = "I can only help with a single option or a two-leg vertical spread."
_INVALID_SYMBOL = "The symbol contains invalid characters or is too long."


class GuardrailViolation(ValueError):
    pass


def check_chat_request(message: str, default_symbol: str) -> None:
    normalized = message.strip()
    if len(normalized) > MAX_MESSAGE_LENGTH:
        raise GuardrailViolation(_TOO_LONG)
    if not _SYMBOL_PATTERN.fullmatch(
        default_symbol.strip().upper().removeprefix("_")
    ):
        raise GuardrailViolation(_INVALID_SYMBOL)
    if _PROMPT_INJECTION.search(normalized):
        raise GuardrailViolation(_INJECTION)
    if _ABUSIVE.search(normalized):
        raise GuardrailViolation(_ABUSIVE_MESSAGE)
    if _OFF_TOPIC.search(normalized):
        raise GuardrailViolation(_OUT_OF_SCOPE)
    if _UNSUPPORTED_STRATEGY.search(normalized):
        raise GuardrailViolation(_UNSUPPORTED_STRATEGY_MESSAGE)
    if (
        len(_SIDE_ACTIONS.findall(normalized)) > MAX_LEGS
        or len(_LEG_MENTIONS.findall(normalized)) > MAX_LEGS
    ):
        raise GuardrailViolation(_TOO_MANY_LEGS)
    if _UNSAFE_CHARACTERS.search(normalized) or _LONG_TOKEN.search(normalized):
        raise GuardrailViolation(_INVALID_SYMBOL)
    if not _OPTION_VOCABULARY.search(normalized):
        raise GuardrailViolation(_OUT_OF_SCOPE)
    if (
        _TEACHING_OR_QUESTION.search(normalized)
        and not _SIDE_ACTIONS.search(normalized)
        and not re.search(r"\d", normalized)
    ):
        raise GuardrailViolation(_OUT_OF_SCOPE)
