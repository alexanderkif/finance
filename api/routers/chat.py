import re
from datetime import date, datetime
from typing import Literal

import httpx
from agent.chat import ChatModelOutput, route_chat_turn
from core.cboe_provider import (
    CboePayloadError,
    CboeRateLimitedError,
    CboeUnavailableError,
)
from core.chat_i18n import (
    ambiguous_spread_text,
    analyzing_text,
    cancel_text,
    confirm_text,
    draft_text,
    empty_option_text,
    fallback_answer_text,
    localize_warning,
    need_chain_text,
    need_more_text,
    previous_position_text,
    reference_error_text,
    refusal_text,
    switch_text,
)
from core.chat_models import (
    ChatConfirm,
    ChatDraft,
    ChatDraftLeg,
    ChatSwitch,
    ChatTurnRequest,
    ChatTurnResponse,
)
from core.draft_suggestions import DraftCompletion, complete_draft, nearest_hint
from core.gemini_provider import (
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiRequestError,
    GeminiResponseError,
)
from core.guardrails import GuardrailViolation, check_chat_turn_request
from core.market_digest import MarketDigest, build_market_digest
from core.metrics import AnalysisPosition, OptionLeg, format_header
from core.option_parsing import (
    ParsedLeg,
    classify_strategy,
    parse_expiration,
)
from core.playbook_registry import PlaybookKey, load_playbooks
from core.reference_edits import (
    ReferenceEdit,
    ReferenceResolutionError,
    resolve_reference_position,
)
from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from routers.options import get_options_provider

router = APIRouter()
_PLAYBOOKS = load_playbooks()

_YES = re.compile(
    r"^(?:yes|y|yeah|yep|ok|okay|sure|go\s+ahead|use\s+these|use\s+it|"
    r"do\s+it|analy[sz]e|да|ок|хорошо|верно|давай|подходит)[.!]?$",
    re.IGNORECASE,
)
_CANCEL = re.compile(
    r"^(?:cancel|start\s+over|reset|never\s*mind|not\s+now|forget\s+it|"
    r"drop\s+it|отмена|начать\s+заново|сброс|не\s+сейчас|забудь)[.!]?$",
    re.IGNORECASE,
)
_USE_SUGGESTIONS = re.compile(
    r"^(?:use\s+these(?:\s+values)?|apply\s+(?:these|the\s+suggestions)|"
    r"yes\s+use\s+these)[.!]?$",
    re.IGNORECASE,
)
_EXPLICIT_SWITCH = (
    re.compile(
        r"^(?:show|display|load|open|switch\s+to|go\s+to|take\s+me\s+to)\s+"
        r"(?:me\s+)?(?:the\s+)?(?:chart\s+(?:for|of)\s+)?"
        r"([A-Za-z0-9._-]{1,15})(?:\s+(?:chart|levels|news))?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:покажи(?:те)?|открой(?:те)?)\s+(?:мне\s+)?(?:график\s+)?"
        r"([A-Za-z0-9._-]{1,15})(?:\s+график)?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^переключи(?:сь|те)?\s+на\s+([A-Za-z0-9._-]{1,15})$",
        re.IGNORECASE,
    ),
)
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_MARKET_QUESTION = re.compile(
    r"\b(?:trend|patterns?|candles?|sentiment|news|levels?|support|resistance|"
    r"price|vix|volatility|rsi|sma|chart|"
    r"тренд\w*|паттерн\w*|свеч\w*|настроен\w*|новост\w*|уровн\w*|"
    r"поддерж\w*|сопротив\w*|цен\w*|волатильн\w*|график\w*|объ[её]м\w*)\b",
    re.IGNORECASE,
)
_NON_SYMBOL_WORDS = frozenset(
    {
        "chart",
        "charts",
        "price",
        "levels",
        "level",
        "news",
        "market",
        "option",
        "options",
        "put",
        "call",
        "spread",
        "position",
        "analysis",
        "trend",
        "the",
        "me",
        "it",
        "this",
        "that",
        "today",
        "now",
    }
)
_CHAIN_ERRORS = (
    CboeRateLimitedError,
    CboeUnavailableError,
    httpx.HTTPStatusError,
    httpx.RequestError,
    CboePayloadError,
    ValueError,
)


def _response(
    body: ChatTurnRequest,
    *,
    mode: Literal["answer", "draft", "confirm", "switch_symbol", "refused"],
    text: str,
    language: str | None = None,
    intent: Literal["open", "close", "roll"] | None = None,
    draft: ChatDraft | None = None,
    missing: list[str] | None = None,
    suggestions=None,
    confirm: ChatConfirm | None = None,
    switch: ChatSwitch | None = None,
    pending_draft: ChatDraft | None = None,
    as_of: datetime | None = None,
    warnings: list[str] | None = None,
) -> ChatTurnResponse:
    values = warnings or []
    return ChatTurnResponse(
        mode=mode,
        text=text,
        language=language or body.language or "English",
        intent=intent or body.intent or "open",
        draft=draft,
        missing=missing or [],
        suggestions=suggestions,
        confirm=confirm,
        switch=switch,
        pending_draft=pending_draft,
        as_of=as_of or body.market.as_of,
        degraded=bool(values),
        warnings=values,
    )


def _refused(
    body: ChatTurnRequest,
    language: str | None = None,
) -> ChatTurnResponse:
    resolved = language or body.language
    return _response(
        body,
        mode="refused",
        text=refusal_text(resolved),
        language=resolved,
        draft=body.draft,
    )


def _normalize_language(message: str, detected: str | None) -> str:
    if re.search(r"[іїєґ]", message, re.IGNORECASE):
        return "Ukrainian"
    if re.search(r"[\u0400-\u04FF]", message):
        return "Russian"
    return detected or "English"


def _normalize_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper().removeprefix("_")
    return normalized or None


def _is_yes(text: str) -> bool:
    return bool(_YES.fullmatch(text.strip()))


def _is_cancel(text: str) -> bool:
    return bool(_CANCEL.fullmatch(text.strip()))


def _explicit_switch_symbol(text: str) -> str | None:
    normalized = text.strip()
    if len(normalized) > 60:
        return None
    for pattern in _EXPLICIT_SWITCH:
        match = pattern.fullmatch(normalized)
        if match is None:
            continue
        symbol = _normalize_symbol(match.group(1))
        if symbol is None or symbol.lower() in _NON_SYMBOL_WORDS:
            continue
        return symbol
    return None


def _draft_from_position(position: AnalysisPosition) -> ChatDraft:
    return ChatDraft(
        position_type=position.position_type,
        legs=[
            ChatDraftLeg(
                symbol=leg.symbol,
                side=leg.side,
                option_type=leg.option_type,
                strike=leg.strike,
                expiration=leg.expiration,
            )
            for leg in position.legs
        ],
        strategy_key=classify_strategy(
            [
                ParsedLeg(
                    symbol=leg.symbol,
                    side=leg.side,
                    option_type=leg.option_type,
                    strike=leg.strike,
                    expiration=leg.expiration,
                )
                for leg in position.legs
            ]
        ),
    )


def _position_from_draft(draft: ChatDraft) -> AnalysisPosition | None:
    legs: list[OptionLeg] = []
    for leg in draft.legs:
        if (
            leg.side is None
            or leg.option_type is None
            or leg.strike is None
            or leg.expiration is None
        ):
            return None
        legs.append(
            OptionLeg(
                symbol=leg.symbol,
                side=leg.side,
                option_type=leg.option_type,
                strike=leg.strike,
                expiration=leg.expiration,
            )
        )
    return AnalysisPosition(
        position_type="single" if len(legs) == 1 else "strategy",
        legs=legs,
    )


def _confirm_from_draft(draft: ChatDraft) -> ChatConfirm | None:
    position = _position_from_draft(draft)
    if position is None:
        return None
    parsed = [
        ParsedLeg(
            symbol=leg.symbol,
            side=leg.side,
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
        )
        for leg in position.legs
    ]
    strategy_key = draft.strategy_key or classify_strategy(parsed)
    if strategy_key is None:
        return None
    playbook = _PLAYBOOKS[strategy_key]
    return ChatConfirm(
        summary=format_header(playbook.display_name, position.legs),
        position=position,
    )


def _missing_draft(draft: ChatDraft) -> list[str]:
    missing: list[str] = []
    for leg in draft.legs:
        for field in ("side", "option_type", "strike", "expiration"):
            if getattr(leg, field) is None and field not in missing:
                missing.append(field)
    return missing


def _merge_draft(
    existing: ChatDraft | None,
    extracted: list[ChatDraftLeg],
    *,
    default_symbol: str,
    strategy_hint: PlaybookKey | None,
    intent: Literal["open", "close", "roll"] | None,
) -> ChatDraft:
    resolved_intent = intent or (existing.intent if existing is not None else None)
    if not extracted:
        if existing is not None:
            return existing.model_copy(update={"intent": resolved_intent})
        return ChatDraft(
            position_type="single",
            legs=[ChatDraftLeg(symbol=default_symbol)],
            strategy_key=strategy_hint,
            intent=resolved_intent,
        )
    if existing is None:
        return ChatDraft(
            position_type="single" if len(extracted) == 1 else "strategy",
            legs=[
                leg.model_copy(
                    update={"symbol": leg.symbol or default_symbol}
                )
                for leg in extracted
            ],
            strategy_key=strategy_hint,
            intent=resolved_intent,
        )

    merged = [leg.model_copy() for leg in existing.legs]
    if len(extracted) > len(merged):
        merged = [
            ChatDraftLeg(
                symbol=leg.symbol or default_symbol,
                side=leg.side,
                option_type=leg.option_type,
                strike=leg.strike,
                expiration=leg.expiration,
            )
            for leg in extracted
        ]
    else:
        for index, leg in enumerate(extracted):
            target = _target_index(merged, leg, index)
            current = merged[target]
            merged[target] = current.model_copy(
                update={
                    "symbol": leg.symbol or current.symbol or default_symbol,
                    "side": leg.side if leg.side is not None else current.side,
                    "option_type": (
                        leg.option_type
                        if leg.option_type is not None
                        else current.option_type
                    ),
                    "strike": leg.strike if leg.strike is not None else current.strike,
                    "expiration": (
                        leg.expiration
                        if leg.expiration is not None
                        else current.expiration
                    ),
                }
            )
    for leg in merged:
        if leg.symbol is None:
            leg.symbol = default_symbol
    return ChatDraft(
        position_type="single" if len(merged) == 1 else "strategy",
        legs=merged,
        strategy_key=strategy_hint or existing.strategy_key,
        intent=resolved_intent,
    )


def _target_index(
    legs: list[ChatDraftLeg],
    extracted: ChatDraftLeg,
    fallback: int,
) -> int:
    if extracted.side is not None:
        for index, leg in enumerate(legs):
            if leg.side == extracted.side:
                if (
                    extracted.option_type is None
                    or leg.option_type in (None, extracted.option_type)
                ):
                    return index
    if fallback < len(legs):
        return fallback
    return 0


def _extract_legs(
    output: ChatModelOutput,
    default_symbol: str,
) -> list[ChatDraftLeg]:
    legs: list[ChatDraftLeg] = []
    for item in output.legs[:2]:
        try:
            expiration = parse_expiration(item.expiration)
        except GeminiResponseError:
            expiration = None
        legs.append(
            ChatDraftLeg(
                symbol=_normalize_symbol(item.symbol) or default_symbol,
                side=item.side,
                option_type=item.option_type,
                strike=item.strike,
                expiration=expiration,
            )
        )
    return legs


def _reference_from_output(output: ChatModelOutput) -> ReferenceEdit | None:
    reference = output.reference
    if reference is None or reference.kind is None:
        return None
    try:
        return ReferenceEdit.model_validate(
            {
                "kind": reference.kind,
                "strikes": reference.strikes,
                "direction": reference.direction,
                "expiration": parse_expiration(reference.expiration),
            }
        )
    except (ValueError, ValidationError, GeminiResponseError):
        return None


def _pending_draft_for_switch(
    draft: ChatDraft | None,
    symbol: str,
) -> ChatDraft | None:
    if draft is None or not draft.legs:
        return None
    if all(leg.symbol == symbol for leg in draft.legs):
        return draft
    return None


def _switch_response(
    body: ChatTurnRequest,
    symbol: str,
    *,
    explicit: bool,
    reason: str,
    pending_draft: ChatDraft | None = None,
    language: str | None = None,
    text: str | None = None,
) -> ChatTurnResponse:
    resolved_language = language or body.language
    if text is None:
        text = switch_text(
            resolved_language,
            symbol=symbol,
            current=body.symbol,
            explicit=explicit,
        )
    return _response(
        body,
        mode="switch_symbol",
        text=text,
        language=resolved_language,
        draft=body.draft,
        pending_draft=pending_draft,
        switch=ChatSwitch(symbol=symbol, explicit=explicit, reason=reason),
    )


def _chain_warning(error: Exception) -> str:
    if isinstance(error, CboeRateLimitedError):
        return "rate_limited"
    if isinstance(error, CboeUnavailableError):
        return "upstream_error"
    if isinstance(error, httpx.HTTPStatusError):
        return "not_found" if error.response.status_code == 404 else "upstream_error"
    if isinstance(error, httpx.RequestError):
        return "unreachable"
    if isinstance(error, CboePayloadError):
        return "payload_error"
    return "market_data_unavailable"


def _as_of(chain_as_of: datetime | None) -> date:
    return chain_as_of.date() if chain_as_of is not None else date.today()


async def _underlying_price(
    request: Request,
    body: ChatTurnRequest,
    symbol: str,
) -> float | None:
    if body.market.symbol == symbol and body.market.price is not None:
        return body.market.price
    provider = get_options_provider(request)
    try:
        quote = await provider.get_market_quote(symbol)
        return quote.price
    except (
        httpx.HTTPStatusError,
        httpx.RequestError,
        CboePayloadError,
        CboeRateLimitedError,
        CboeUnavailableError,
        ValueError,
    ):
        return None


def _confirm_text(
    completion: DraftCompletion,
    price: float | None,
    language: str,
) -> str:
    warning = (
        localize_warning(language, completion.warnings[0])
        if completion.warnings
        else None
    )
    return confirm_text(
        language,
        symbol=completion.draft.legs[0].symbol if completion.draft.legs else "",
        price=price,
        summary=completion.confirm_summary or "the position",
        has_suggestions=bool(
            completion.suggestions and completion.suggestions.fields
        ),
        warning=warning,
    )


def _draft_text(completion: DraftCompletion, language: str) -> str:
    warning = (
        localize_warning(language, completion.warnings[0])
        if completion.warnings
        else None
    )
    return draft_text(language, missing=completion.missing, warning=warning)


async def _handle_option(
    body: ChatTurnRequest,
    output: ChatModelOutput,
    request: Request,
) -> ChatTurnResponse:
    language = output.detected_language or body.language
    extracted = _extract_legs(output, body.symbol)
    reference = _reference_from_output(output)

    if reference is not None:
        base_context: list[AnalysisPosition] = []
        if body.draft is not None:
            draft_position = _position_from_draft(body.draft)
            if draft_position is not None:
                base_context = [draft_position]
        if not base_context:
            base_context = list(body.context)
        if not base_context:
            return _response(
                body,
                mode="answer",
                text=previous_position_text(language),
                language=language,
                draft=body.draft,
            )
        base = base_context[-1]
        base_symbol = base.legs[0].symbol
        try:
            provider = get_options_provider(request)
            chain = await provider.get_chain(base_symbol)
        except _CHAIN_ERRORS as error:
            return _response(
                body,
                mode="draft",
                text=need_chain_text(language),
                language=language,
                draft=body.draft,
                warnings=[_chain_warning(error)],
            )
        target_expiration = (
            reference.expiration or base.legs[0].expiration
        )
        try:
            position = resolve_reference_position(
                reference,
                base_context,
                chain.contracts,
                target_expiration,
            )
        except ReferenceResolutionError:
            hint = _nearby_for_reference(
                chain.contracts,
                reference,
                base,
                target_expiration,
            )
            return _response(
                body,
                mode="draft",
                text=reference_error_text(language, hint),
                language=language,
                draft=body.draft,
                warnings=list(chain.warnings),
            )
        resolved = _draft_from_position(position).model_copy(
            update={"intent": output.intent or body.intent or "open"}
        )
        if base_symbol != body.symbol:
            return _switch_response(
                body,
                base_symbol,
                explicit=False,
                reason="The edited position belongs to another instrument.",
                pending_draft=resolved,
                language=language,
            )
        completion = complete_draft(
            resolved,
            chain.contracts,
            await _underlying_price(request, body, base_symbol),
            _as_of(chain.as_of),
            strategy_hint=resolved.strategy_key,
            playbooks=_PLAYBOOKS,
        )
        return _completion_response(
            body,
            completion,
            language,
            chain.as_of,
            list(chain.warnings),
        )

    if not extracted and body.draft is None:
        return _response(
            body,
            mode="draft",
            text=empty_option_text(language),
            language=language,
            draft=ChatDraft(
                position_type="single",
                legs=[ChatDraftLeg(symbol=body.symbol)],
                intent=body.intent,
            ),
        )

    if (
        reference is None
        and output.strategy_hint is None
        and len(extracted) == 1
        and (body.draft is None or body.draft.strategy_key is None)
        and re.search(r"\bspread\b", body.message, re.IGNORECASE)
    ):
        draft = _merge_draft(
            body.draft,
            extracted,
            default_symbol=body.symbol,
            strategy_hint=None,
            intent=output.intent or body.intent,
        )
        return _response(
            body,
            mode="draft",
            text=ambiguous_spread_text(language),
            language=language,
            intent=draft.intent or body.intent,
            draft=draft,
            missing=["strategy_type"],
        )

    symbol = body.symbol
    if extracted:
        symbol = extracted[0].symbol or body.symbol
    elif body.draft and body.draft.legs:
        symbol = body.draft.legs[0].symbol or body.symbol

    merged = _merge_draft(
        body.draft,
        extracted,
        default_symbol=symbol,
        strategy_hint=output.strategy_hint,
        intent=output.intent or body.intent,
    )
    if symbol != body.symbol:
        return _switch_response(
            body,
            symbol,
            explicit=False,
            reason="The option position belongs to another instrument.",
            pending_draft=merged,
            language=language,
        )

    try:
        provider = get_options_provider(request)
        chain = await provider.get_chain(symbol)
    except _CHAIN_ERRORS as error:
        return _response(
            body,
            mode="draft",
            text=need_chain_text(language),
            language=language,
            draft=merged,
            missing=_missing_draft(merged),
            warnings=[_chain_warning(error)],
        )
    if not chain.contracts:
        return _response(
            body,
            mode="draft",
            text=need_chain_text(language),
            language=language,
            draft=merged,
            missing=_missing_draft(merged),
            warnings=list(chain.warnings) or ["market_data_unavailable"],
        )
    completion = complete_draft(
        merged,
        chain.contracts,
        await _underlying_price(request, body, symbol),
        _as_of(chain.as_of),
        strategy_hint=output.strategy_hint or merged.strategy_key,
        playbooks=_PLAYBOOKS,
    )
    return _completion_response(
        body,
        completion,
        language,
        chain.as_of,
        list(chain.warnings),
    )


def _completion_response(
    body: ChatTurnRequest,
    completion: DraftCompletion,
    language: str,
    chain_as_of: datetime | None,
    chain_warnings: list[str],
) -> ChatTurnResponse:
    warnings = [
        *chain_warnings,
        *[localize_warning(language, warning) for warning in completion.warnings],
    ]
    if completion.confirm_position is not None and completion.confirm_summary:
        confirm = ChatConfirm(
            summary=completion.confirm_summary,
            position=completion.confirm_position,
        )
        price = body.market.price
        return _response(
            body,
            mode="confirm",
            text=_confirm_text(completion, price, language),
            language=language,
            intent=completion.draft.intent or body.intent,
            draft=completion.draft,
            suggestions=completion.suggestions,
            confirm=confirm,
            as_of=chain_as_of,
            warnings=warnings,
        )
    return _response(
        body,
        mode="draft",
        text=_draft_text(completion, language),
        language=language,
        intent=completion.draft.intent or body.intent,
        draft=completion.draft,
        missing=completion.missing,
        suggestions=completion.suggestions,
        as_of=chain_as_of,
        warnings=warnings,
    )


async def _continue_draft(
    body: ChatTurnRequest,
    request: Request,
) -> ChatTurnResponse:
    draft = body.draft
    if draft is None or not draft.legs:
        return _response(
            body,
            mode="draft",
            text=empty_option_text(body.language),
            draft=ChatDraft(
                position_type="single",
                legs=[ChatDraftLeg(symbol=body.symbol)],
                intent=body.intent,
            ),
        )
    symbol = draft.legs[0].symbol or body.symbol
    if symbol != body.symbol:
        return _switch_response(
            body,
            symbol,
            explicit=False,
            reason="The option position belongs to another instrument.",
            pending_draft=draft,
        )
    try:
        provider = get_options_provider(request)
        chain = await provider.get_chain(symbol)
    except _CHAIN_ERRORS as error:
        return _response(
            body,
            mode="draft",
            text=need_chain_text(body.language),
            draft=draft,
            missing=_missing_draft(draft),
            warnings=[_chain_warning(error)],
        )
    if not chain.contracts:
        return _response(
            body,
            mode="draft",
            text=need_chain_text(body.language),
            draft=draft,
            missing=_missing_draft(draft),
            warnings=list(chain.warnings) or ["market_data_unavailable"],
        )
    completion = complete_draft(
        draft,
        chain.contracts,
        await _underlying_price(request, body, symbol),
        _as_of(chain.as_of),
        strategy_hint=draft.strategy_key,
        playbooks=_PLAYBOOKS,
    )
    return _completion_response(
        body,
        completion,
        body.language,
        chain.as_of,
        list(chain.warnings),
    )


def _nearby_for_reference(
    contracts,
    reference: ReferenceEdit,
    base: AnalysisPosition,
    expiration: date,
) -> str:
    if not base.legs:
        return ""
    leg = base.legs[0]
    return nearest_hint(contracts, leg.option_type, expiration, leg.strike)


def _handle_switch(
    body: ChatTurnRequest,
    output: ChatModelOutput,
) -> ChatTurnResponse:
    symbol = _normalize_symbol(output.switch_symbol)
    if symbol is None or not re.fullmatch(r"[A-Z0-9._-]{1,15}", symbol):
        return _refused(body)
    explicit = bool(output.explicit_switch)
    pending = _pending_draft_for_switch(body.draft, symbol)
    return _switch_response(
        body,
        symbol,
        explicit=explicit,
        reason=(
            "Explicit instrument command."
            if explicit
            else "The user asked about another instrument."
        ),
        pending_draft=pending,
        language=output.detected_language or "English",
        text=output.answer or None,
    )


def _russian_market_answer(digest: MarketDigest) -> str:
    trend = {
        "up": "вверх",
        "down": "вниз",
        "sideways": "боковой",
        "unknown": "недостаточно данных",
    }[digest.trend]
    regime = {
        "calm": "спокойный",
        "elevated": "повышенный",
        "panic": "панический",
        "unknown": "неизвестен",
    }[digest.vix_regime]
    price = f"{digest.price:.2f}" if digest.price is not None else "недоступна"
    change = (
        f", изменение {digest.change_pct:+.2f}%"
        if digest.change_pct is not None
        else ""
    )
    rsi = f"{digest.rsi14:.1f}" if digest.rsi14 is not None else "нет данных"
    vix = f"{digest.vix:.2f}" if digest.vix is not None else "недоступен"
    support = ", ".join(f"{value:g}" for value in digest.support) or "нет данных"
    resistance = (
        ", ".join(f"{value:g}" for value in digest.resistance) or "нет данных"
    )
    pattern_names = {
        "doji": "доджи",
        "hammer": "молот",
        "shooting_star": "падающая звезда",
        "inside_bar": "внутренний бар",
        "bullish_engulfing": "бычье поглощение",
        "bearish_engulfing": "медвежье поглощение",
    }
    patterns = ""
    if digest.patterns:
        names = ", ".join(
            pattern_names.get(pattern.name, pattern.name)
            for pattern in digest.patterns[:3]
        )
        patterns = f" Свечные паттерны: {names}."
    return (
        f"{digest.symbol}: цена около {price}{change}. Тренд: {trend}. "
        f"RSI: {rsi}. VIX: {vix} ({regime}). Поддержка: {support}; "
        f"сопротивление: {resistance}.{patterns} Данные с задержкой 15 минут. "
        "Это образовательный контекст, не инвестиционная рекомендация."
    )


async def _handle_output(
    body: ChatTurnRequest,
    output: ChatModelOutput,
    request: Request,
    digest: MarketDigest,
) -> ChatTurnResponse:
    if output.mode == "refuse":
        if _CYRILLIC.search(body.message) and _MARKET_QUESTION.search(body.message):
            return _response(
                body,
                mode="answer",
                text=_russian_market_answer(digest),
                language="Russian",
                draft=body.draft,
            )
        return _refused(body, output.detected_language)
    if output.mode == "switch":
        return _handle_switch(body, output)
    if output.mode == "option" or output.legs:
        return await _handle_option(body, output, request)
    return _response(
        body,
        mode="answer",
        text=(
            output.answer.strip()
            if output.answer and output.answer.strip()
            else fallback_answer_text(output.detected_language or body.language)
        ),
        language=output.detected_language or body.language,
        draft=body.draft,
    )


@router.post("/api/chat/turn", response_model=ChatTurnResponse)
async def chat_turn(
    body: ChatTurnRequest,
    request: Request,
) -> ChatTurnResponse:
    language = _normalize_language(body.message, body.language)
    try:
        check_chat_turn_request(body.message, body.symbol)
    except GuardrailViolation:
        return _refused(body, language)

    if _is_cancel(body.message):
        return _response(
            body,
            mode="answer",
            text=cancel_text(language),
            language=language,
            draft=None,
        )

    if _is_yes(body.message) and body.draft is not None:
        confirm = _confirm_from_draft(body.draft)
        if confirm is not None:
            return _response(
                body,
                mode="confirm",
                text=analyzing_text(language, confirm.summary),
                language=language,
                intent=body.draft.intent or body.intent,
                draft=body.draft,
                confirm=confirm,
            )
        missing = _missing_draft(body.draft)
        if not missing:
            missing = ["strategy_type"]
        return _response(
            body,
            mode="draft",
            text=need_more_text(language, missing),
            language=language,
            intent=body.draft.intent or body.intent,
            draft=body.draft,
            missing=missing,
        )

    if _USE_SUGGESTIONS.fullmatch(body.message.strip()) and body.draft is not None:
        return await _continue_draft(body, request)

    explicit = _explicit_switch_symbol(body.message)
    if explicit is not None:
        return _switch_response(
            body,
            explicit,
            explicit=True,
            reason="Explicit instrument command.",
            pending_draft=_pending_draft_for_switch(body.draft, explicit),
            language=language,
        )

    if body.continuation and body.draft is not None:
        return await _continue_draft(body, request)

    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(status_code=503, detail="Analysis service is not ready.")

    digest = build_market_digest(body.market)
    try:
        output = await route_chat_turn(
            client,
            message=body.message,
            selected_symbol=body.symbol,
            intent=body.intent,
            history=body.history,
            draft=body.draft,
            context=[
                position.model_dump(mode="json") for position in body.context
            ],
            digest=digest,
        )
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GeminiRateLimitError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except (GeminiRequestError, GeminiResponseError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    output = output.model_copy(
        update={
            "detected_language": _normalize_language(
                body.message,
                output.detected_language,
            )
        }
    )
    return await _handle_output(body, output, request, digest)
