# Playbook specification

## JSON model

Each playbook follows this schema:

```python
class Playbook(BaseModel):
    strategy_key: str
    display_name: str
    leg_count: Literal[1, 2]
    leg_requirements: list[Literal["side", "option_type", "strike", "expiration"]]
    profit_formula: str
    loss_formula: str
    breakeven_formula: str
    ideal_conditions: list[str]
    risk_flags: list[str]
    event_sensitivity: dict[str, bool]  # earnings, dividends, macro
```

## Required files

Place all eight files in `api/core/playbooks/`.

| File                    | Display name     | Playbook facts                    |
| ----------------------- | ---------------- | --------------------------------- |
| `bull_put_spread.json`  | Bull Put Spread  | Credit; max loss = width − credit |
| `bear_call_spread.json` | Bear Call Spread | Credit; mirror of bull put        |
| `bull_call_spread.json` | Bull Call Spread | Debit; max profit = width − debit |
| `bear_put_spread.json`  | Bear Put Spread  | Debit; mirror of bull call        |
| `long_call.json`        | Long Call        | Theta decay and IV crush          |
| `long_put.json`         | Long Put         | Theta decay and IV crush          |
| `short_call.json`       | Short Call       | Unlimited risk; margin            |
| `short_put.json`        | Short Put        | Margin                            |

## Vertical-spread identification

Two legs form a vertical spread only when they have the same option type and
expiration, and different strikes. The side of the lower-strike leg identifies
the strategy:

| Lower-strike leg | Option type | Strategy key       |
| ---------------- | ----------- | ------------------ |
| Buy              | Call        | `bull_call_spread` |
| Sell             | Call        | `bear_call_spread` |
| Buy              | Put         | `bull_put_spread`  |
| Sell             | Put         | `bear_put_spread`  |

The higher-strike leg must have the opposite side. If these conditions are
not met, this rule does not identify a vertical spread.

Example: sell the higher-strike put and buy the lower-strike put to identify a
`bull_put_spread`.

## Draft suggestion defaults

When the chat proposes a complete option draft, use the live listed chain and
these deterministic rules:

- Expiration: the listed expiration closest to 40 days, preferring 21-60 days.
- Long call: the strike closest to the underlying price.
- Long put: the strike closest to the underlying price.
- Short call: the first listed strike above the underlying price.
- Short put: the first listed strike below the underlying price.
- Bull put spread: the highest listed put strike at or below 99% of the
  underlying price as the short leg, and the second next listed strike lower as
  the long leg.
- Bear call spread: the lowest listed call strike at or above 101% of the
  underlying price as the short leg, and the second next listed strike higher as
  the long leg.
- Bull call spread: the strike closest to the underlying price as the long leg,
  and the second next listed strike higher as the short leg.
- Bear put spread: the strike closest to the underlying price as the long leg,
  and the second next listed strike lower as the short leg.

The default width is two listed strike steps: the long leg is the second next
listed strike from the short leg. If the ladder has fewer steps, use the widest
available width and say so. If no listed candidate exists, return the nearest
listed strikes or ask for an explicit strike; never invent a contract.

Every proposal is an example structure, not a recommendation. The server
validates every proposed leg against the listed chain before the analysis runs.
