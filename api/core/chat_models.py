import re
from datetime import date, datetime
from typing import Literal

from core.finnhub_provider import NewsHeadline
from core.indicators import Candle, ChartRange, IndicatorSeries
from core.metrics import AnalysisPosition
from core.option_parsing import OptionType, Side
from core.playbook_registry import PlaybookKey
from core.reference_edits import ReferenceEdit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ChatMode = Literal["answer", "draft", "confirm", "switch_symbol", "refused"]
ChatRole = Literal["user", "assistant"]
ChartSource = Literal["twelve_data", "cboe_index_history"]
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._-]{1,15}$")


class ChatHistoryTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ChatRole
    text: str = Field(min_length=1, max_length=2_000)


class ChatDraftLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Side | None = None
    option_type: OptionType | None = None
    strike: float | None = Field(default=None, gt=0)
    expiration: date | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper().removeprefix("_")
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Symbol contains invalid characters.")
        return normalized


class ChatDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_type: Literal["single", "strategy"] = "single"
    legs: list[ChatDraftLeg] = Field(min_length=1, max_length=2)
    strategy_key: PlaybookKey | None = None
    reference: ReferenceEdit | None = None
    intent: Literal["open", "close", "roll"] | None = None


class ChatSnapshotSources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: Literal["cboe_delayed"] | None = None
    vix: Literal["cboe_delayed"] | None = None
    news: Literal["finnhub"] | None = None


class ChatMarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    price: float | None = None
    change_pct: float | None = None
    vix: float | None = None
    support: list[float] = Field(default_factory=list, max_length=3)
    resistance: list[float] = Field(default_factory=list, max_length=3)
    candles: list[Candle] = Field(default_factory=list, max_length=120)
    sma: list[IndicatorSeries] = Field(default_factory=list, max_length=3)
    rsi: IndicatorSeries = Field(default_factory=lambda: IndicatorSeries(period=14, points=[]))
    news: list[NewsHeadline] = Field(default_factory=list, max_length=5)
    range: ChartRange = "6mo"
    chart_source: ChartSource | None = None
    chart_as_of: datetime | None = None
    as_of: datetime | None = None
    quote_as_of: datetime | None = None
    vix_as_of: datetime | None = None
    news_as_of: datetime | None = None
    sources: ChatSnapshotSources = Field(default_factory=ChatSnapshotSources)
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper().removeprefix("_")
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Symbol contains invalid characters.")
        return normalized

    @model_validator(mode="after")
    def enforce_limits(self) -> "ChatMarketSnapshot":
        for series in self.sma:
            if len(series.points) > 120:
                raise ValueError("SMA series is too long.")
        if len(self.rsi.points) > 120:
            raise ValueError("RSI series is too long.")
        if any(
            len(headline.title) > 300 or len(headline.url) > 2_000
            for headline in self.news
        ):
            raise ValueError("Headline is too long.")
        return self


class ChatDraftSuggestions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[str] = Field(default_factory=list)
    expiration: date | None = None
    strike: float | None = None
    long_strike: float | None = None
    width: int | None = None


class ChatSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    explicit: bool
    reason: str

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper().removeprefix("_")
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Symbol contains invalid characters.")
        return normalized


class ChatConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    position: AnalysisPosition


class ChatTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=15)
    message: str = Field(default="", max_length=2_000)
    intent: Literal["open", "close", "roll"] = "open"
    language: str = Field(default="English", min_length=2, max_length=24)
    history: list[ChatHistoryTurn] = Field(default_factory=list, max_length=8)
    draft: ChatDraft | None = None
    context: list[AnalysisPosition] = Field(default_factory=list, max_length=3)
    continuation: bool = False
    market: ChatMarketSnapshot

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper().removeprefix("_")
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Symbol contains invalid characters.")
        return normalized

    @model_validator(mode="after")
    def require_message(self) -> "ChatTurnRequest":
        if not self.continuation and not self.message.strip():
            raise ValueError("Message must not be empty.")
        return self


class ChatTurnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ChatMode
    text: str
    language: str
    intent: Literal["open", "close", "roll"] = "open"
    draft: ChatDraft | None = None
    missing: list[str] = Field(default_factory=list)
    suggestions: ChatDraftSuggestions | None = None
    confirm: ChatConfirm | None = None
    switch: ChatSwitch | None = None
    pending_draft: ChatDraft | None = None
    as_of: datetime | None = None
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)
