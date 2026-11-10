import httpx
from agent.chat import AgentLoopError, AgentTimeoutError, run_chat_agent
from core.chat_models import (
    ChatStep,
    ChatSwitch,
    ChatTurnRequest,
    ChatTurnResponse,
    ChatUiAction,
)
from core.chat_text import (
    LOOP,
    NOT_CONFIGURED,
    RATE_LIMITED,
    TIMEOUT,
    UNAVAILABLE,
)
from core.gemini_provider import (
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiRequestError,
    GeminiResponseError,
)
from core.guardrails import GuardrailViolation, check_chat_turn_request
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.post("/api/chat/turn", response_model=ChatTurnResponse)
async def chat_turn(
    body: ChatTurnRequest,
    request: Request,
) -> ChatTurnResponse:
    try:
        check_chat_turn_request(body.message, body.symbol)
    except GuardrailViolation as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    client = getattr(request.app.state, "http_client", None)
    if not isinstance(client, httpx.AsyncClient):
        raise HTTPException(status_code=503, detail=UNAVAILABLE)

    try:
        result = await run_chat_agent(
            client,
            request,
            message=body.message,
            symbol=body.symbol,
            history=body.history,
            context=body.context,
            snapshot=body.market,
            ui=body.ui,
        )
    except AgentTimeoutError as error:
        raise HTTPException(status_code=504, detail=TIMEOUT) from error
    except AgentLoopError as error:
        raise HTTPException(status_code=502, detail=LOOP) from error
    except GeminiConfigurationError as error:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED) from error
    except GeminiRateLimitError as error:
        raise HTTPException(status_code=429, detail=RATE_LIMITED) from error
    except (GeminiRequestError, GeminiResponseError) as error:
        raise HTTPException(status_code=502, detail=UNAVAILABLE) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=UNAVAILABLE) from error

    switch = (
        ChatSwitch.model_validate(result.switch)
        if result.switch is not None
        else None
    )
    card = result.card.model_dump(mode="json") if result.card is not None else None
    intent = result.card.intent if result.card is not None else body.intent
    return ChatTurnResponse(
        mode="answer",
        text=result.text,
        language=body.language,
        intent=intent,
        card=card,
        steps=[ChatStep.model_validate(step) for step in result.steps],
        ui_actions=[
            ChatUiAction.model_validate(action) for action in result.ui_actions
        ],
        switch=switch,
        as_of=body.market.as_of,
        degraded=bool(result.warnings),
        warnings=result.warnings,
    )
