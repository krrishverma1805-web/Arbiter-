from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MethodMix:
    upi: float
    card: float
    netbanking: float
    wallet: float

    def as_pairs(self) -> list[tuple[str, float]]:
        return [
            ("upi", self.upi),
            ("card", self.card),
            ("netbanking", self.netbanking),
            ("wallet", self.wallet),
        ]


@dataclass(frozen=True)
class Scenario:
    name: str
    order_value_mu: float  # lognormal mu (natural log of rupees)
    order_value_sigma: float
    method_mix: MethodMix
    refund_rate: float
    period_days: int = 31
    # MDR rates by method (fraction of gross); UPI has a small flat platform fee instead
    mdr: dict[str, float] = field(
        default_factory=lambda: {
            "upi": 0.0,
            "card": 0.018,
            "netbanking": 0.009,
            "wallet": 0.019,
        }
    )
    upi_flat_fee_paise: int = 0
    gst_rate: float = 0.18


SCENARIOS: dict[str, Scenario] = {
    "d2c": Scenario(
        name="d2c",
        order_value_mu=7.24,
        order_value_sigma=0.7,
        method_mix=MethodMix(upi=0.55, card=0.30, netbanking=0.10, wallet=0.05),
        refund_rate=0.06,
    ),
    "marketplace": Scenario(
        name="marketplace",
        order_value_mu=6.80,
        order_value_sigma=0.9,
        method_mix=MethodMix(upi=0.65, card=0.25, netbanking=0.07, wallet=0.03),
        refund_rate=0.09,
    ),
    "saas": Scenario(
        name="saas",
        order_value_mu=8.70,
        order_value_sigma=0.5,
        method_mix=MethodMix(upi=0.05, card=0.70, netbanking=0.25, wallet=0.0),
        refund_rate=0.02,
    ),
}
