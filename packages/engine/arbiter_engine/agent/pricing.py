"""One place for model pricing, so a cost is either real or explicitly unknown.

Never let a run report `$0.00` for a paid API call: `estimate_cost` returns
`None` for any model not in the table, and the caller must render that as
"unavailable for this provider", not as zero.

Prices are USD per million tokens (input, output), rough and current as of
2026-01. They drive (a) the per-run cost ceiling and (b) the scorecard estimate;
neither needs to be exact, but both need to be honest about coverage.
"""

from __future__ import annotations

PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    # OpenAI
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    # Groq (openai/gpt-oss-120b, on-demand rate — https://groq.com/pricing)
    "openai/gpt-oss-120b": (0.15, 0.60),
    # Gemini (introductory rate through 2026-12-31, reverts to (1.50, 7.50) after —
    # https://ai.google.dev/gemini-api/docs/pricing)
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
}

#: used for the per-run cost ceiling when the model is unknown — deliberately
#: high so an unknown model trips the budget sooner rather than running free.
CONSERVATIVE_CEILING_RATE: tuple[float, float] = (5.0, 25.0)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    """USD estimate, or None if we don't have a price for this model."""
    rate = PRICE_PER_MTOK.get(model)
    if rate is None:
        return None
    return round(tokens_in / 1e6 * rate[0] + tokens_out / 1e6 * rate[1], 4)


def ceiling_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """USD spent for the cost ceiling — falls back to a conservative rate so an
    unpriced model still counts against the budget."""
    rate = PRICE_PER_MTOK.get(model, CONSERVATIVE_CEILING_RATE)
    return tokens_in / 1e6 * rate[0] + tokens_out / 1e6 * rate[1]
