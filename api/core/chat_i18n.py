import re

_FIELD_PROMPTS = {
    "English": {
        "side": "whether the option is a buy or a sell",
        "option_type": "whether it is a call or a put",
        "strike": "the strike price",
        "expiration": "the expiration date",
        "strategy_type": "which two-leg spread you mean",
    },
    "Russian": {
        "side": "покупаете вы или продаёте",
        "option_type": "это call или put",
        "strike": "страйк",
        "expiration": "дату экспирации",
        "strategy_type": "какой двухногий спред вы имеете в виду",
    },
}

_WARNING_PATTERNS = (
    (
        re.compile(r"^The requested expiration is not listed; using (.+)\.$"),
        "Запрошенная экспирация не листится; использую {0}.",
    ),
    (
        re.compile(r"^([0-9.]+) is not listed; using ([0-9.]+)\.$"),
        "{0} не листится; использую {1}.",
    ),
)
_WARNING_CODES = {
    "Not enough listed strike steps for the default width; used the widest available.": (
        "Недостаточно листинговых шагов для ширины по умолчанию; "
        "использую максимально доступную."
    ),
    "No distinct listed strikes are available for this spread.": (
        "Для этого спреда нет различных листинговых страйков."
    ),
    "underlying_price_unavailable": "Цена базового актива недоступна.",
    "expiration_unavailable": "Экспирация недоступна.",
    "strikes_unavailable": "Страйки недоступны.",
    "ambiguous_spread_direction": "Непонятно направление спреда.",
}


def is_russian(language: str | None) -> bool:
    return bool(language) and language.lower().startswith("russ")


def need_more_text(language: str | None, missing: list[str]) -> str:
    if not missing:
        return (
            "Эти ноги не образуют поддерживаемый одиночный опцион или "
            "вертикальный спред. Измените одну ногу или начните заново."
            if is_russian(language)
            else "Those legs do not form a supported single option or vertical "
            "spread. Change one leg or start over."
        )
    prompts = _FIELD_PROMPTS["Russian" if is_russian(language) else "English"]
    values = [prompts.get(field, field) for field in missing]
    if is_russian(language):
        joined = values[0] if len(values) == 1 else (
            ", ".join(values[:-1]) + " и " + values[-1]
        )
        return f"Чтобы построить карточку, мне ещё нужно: {joined}."
    joined = values[0] if len(values) == 1 else (
        ", ".join(values[:-1]) + ", and " + values[-1]
    )
    return f"I still need {joined} before I can build the card."


def confirm_text(
    language: str | None,
    *,
    symbol: str,
    price: float | None,
    summary: str,
    has_suggestions: bool,
    warning: str | None = None,
) -> str:
    if is_russian(language):
        prefix = f"{symbol}: цена около {price:.2f}. " if price is not None else ""
        if has_suggestions:
            text = (
                f"{prefix}Могу использовать {summary}. Скажите «да» или нажмите "
                "Analyze, либо скажите, что изменить. Предложенные значения — "
                "пример структуры, не рекомендация."
            )
        else:
            text = (
                f"{prefix}У меня есть {summary}. Скажите «да» или нажмите "
                "Analyze, либо скажите, что изменить."
            )
    else:
        prefix = f"{symbol} is near {price:.2f}. " if price is not None else ""
        if has_suggestions:
            text = (
                f"{prefix}I can use {summary}. Say yes or click Analyze, or tell "
                "me what to change. Suggested values are an example structure, "
                "not a recommendation."
            )
        else:
            text = (
                f"{prefix}I have {summary}. Say yes or click Analyze, or tell me "
                "what to change."
            )
    if warning:
        text = f"{text} {warning}"
    return text


def draft_text(
    language: str | None,
    *,
    missing: list[str],
    warning: str | None = None,
) -> str:
    if missing:
        text = need_more_text(language, missing)
    elif is_russian(language):
        text = (
            "Позиция есть, но нужен листинговый страйк или экспирация, чтобы "
            "построить карточку."
        )
    else:
        text = (
            "I have the position, but I need a listed strike or expiration "
            "before I can build the card."
        )
    if warning:
        text = f"{text} {warning}"
    return text


def cancel_text(language: str | None) -> str:
    return (
        "Черновик отменён. Можем продолжить разговор о выбранном инструменте."
        if is_russian(language)
        else "Draft cancelled. We can keep talking about the selected instrument."
    )


def need_chain_text(language: str | None) -> str:
    return (
        "Сейчас не удаётся получить опционную цепочку. Назовите страйк и "
        "экспирацию или попробуйте через минуту."
        if is_russian(language)
        else "I can't reach the option chain right now. Tell me the strike and "
        "expiration, or try again in a minute."
    )


def refusal_text(language: str | None) -> str:
    return (
        "Я помогаю с графиком, рыночным контекстом, новостями и опционными "
        "позициями по выбранному инструменту. С этой просьбой помочь не могу."
        if is_russian(language)
        else "I can help with this instrument's chart, market context, news, and "
        "option positions. I can't help with that request."
    )


def switch_text(
    language: str | None,
    *,
    symbol: str,
    current: str,
    explicit: bool,
) -> str:
    if is_russian(language):
        return (
            f"Переключаюсь на {symbol}."
            if explicit
            else f"Вы спрашиваете про {symbol}, а на графике {current}. "
            f"Переключиться на {symbol}?"
        )
    return (
        f"Switching to {symbol}."
        if explicit
        else f"You're asking about {symbol}, while the chart shows {current}. "
        f"Switch to {symbol}?"
    )


def previous_position_text(language: str | None) -> str:
    return (
        "Мне нужна предыдущая позиция, чтобы применить это изменение. "
        "Опишите полную позицию."
        if is_russian(language)
        else "I need the previous position before I can apply that change. "
        "Please describe the full position."
    )


def reference_error_text(language: str | None, hint: str) -> str:
    if is_russian(language):
        localized_hint = hint.replace(
            "Nearby listed strikes:",
            "Ближайшие листинговые страйки:",
        )
        return (
            "Не удалось применить изменение к предыдущей позиции. Проверьте "
            f"страйки и экспирацию. {localized_hint}".strip()
        )
    return f"{hint}".strip()


def analyzing_text(language: str | None, summary: str) -> str:
    return (
        f"Анализирую {summary}."
        if is_russian(language)
        else f"Analyzing {summary}."
    )


def empty_option_text(language: str | None) -> str:
    return (
        "Назовите тип опциона, сторону, страйк и экспирацию или спросите про "
        "график."
        if is_russian(language)
        else "Tell me the option type, side, strike, and expiration, or ask "
        "about the chart instead."
    )


def ambiguous_spread_text(language: str | None) -> str:
    return (
        "Это бычий или медвежий спред? Назовите направление, и я предложу "
        "страйки."
        if is_russian(language)
        else "Is this a bull or bear spread? Tell me the direction and I will "
        "propose the strikes."
    )


def fallback_answer_text(language: str | None) -> str:
    return (
        "Я помогаю с графиком, рыночным контекстом, новостями и опционными "
        "позициями по выбранному инструменту."
        if is_russian(language)
        else "I can help with the selected instrument's chart, market context, "
        "news, and option positions."
    )


def localize_warning(language: str | None, warning: str) -> str:
    if not is_russian(language):
        return warning
    if warning in _WARNING_CODES:
        return _WARNING_CODES[warning]
    for pattern, template in _WARNING_PATTERNS:
        match = pattern.fullmatch(warning)
        if match is not None:
            return template.format(*match.groups())
    return warning
