from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

PlaybookKey = Literal[
    "bull_put_spread",
    "bear_call_spread",
    "bull_call_spread",
    "bear_put_spread",
    "long_call",
    "long_put",
    "short_call",
    "short_put",
]

_PLAYBOOK_DIRECTORY: Final = Path(__file__).parent / "playbooks"
_EVENT_KEYS: Final = frozenset({"earnings", "dividends", "macro"})
_REQUIRED_PLAYBOOK_KEYS: Final = frozenset(
    {
        "bull_put_spread",
        "bear_call_spread",
        "bull_call_spread",
        "bear_put_spread",
        "long_call",
        "long_put",
        "short_call",
        "short_put",
    }
)


class Playbook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_key: PlaybookKey
    display_name: str
    leg_count: Literal[1, 2]
    leg_requirements: list[Literal["side", "option_type", "strike", "expiration"]]
    profit_formula: str
    loss_formula: str
    breakeven_formula: str
    ideal_conditions: list[str]
    risk_flags: list[str]
    event_sensitivity: dict[Literal["earnings", "dividends", "macro"], bool]


def load_playbooks() -> dict[PlaybookKey, Playbook]:
    playbooks: dict[PlaybookKey, Playbook] = {}
    for path in sorted(_PLAYBOOK_DIRECTORY.glob("*.json")):
        playbook = Playbook.model_validate_json(path.read_text(encoding="utf-8"))
        if path.stem != playbook.strategy_key:
            raise ValueError(
                f"Playbook filename does not match strategy_key: {path.name}"
            )
        if set(playbook.event_sensitivity) != _EVENT_KEYS:
            raise ValueError(
                f"Playbook must define all event flags: {playbook.strategy_key}"
            )
        if playbook.strategy_key in playbooks:
            raise ValueError(f"Duplicate playbook: {playbook.strategy_key}")
        playbooks[playbook.strategy_key] = playbook

    if set(playbooks) != _REQUIRED_PLAYBOOK_KEYS:
        raise ValueError("All eight required playbooks must be present.")
    return playbooks
