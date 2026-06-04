"""Parameter config loader — reads config.json and provides lookup methods.

The config.json has two independent top-level keys:
  "layer1": partner definitions with commission, FX, and payout channels
  "layer2": settlement definitions with (Par_l, Bank_t) FX rates

The engine loads this and applies the universal formulas.
"""
import json
from decimal import Decimal
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class PartnerCurrencyConfig:
    commission_type: str  # "percentage" or "fixed"
    commission_rate: Decimal = Decimal("0")
    commission_fixed: Decimal = Decimal("0")


@dataclass
class FxConfig:
    fx_partner_rate: Decimal = Decimal("0")
    fx_cadorim_rate: Decimal = Decimal("0")
    fx_market_rate: Decimal = Decimal("0")


@dataclass
class PayoutChannelConfig:
    code: str
    cost_payout: Decimal = Decimal("0")
    cost_type: str = "fixed"  # "fixed" / "percentage" / "per_transaction"


@dataclass
class SettlementConfig:
    partner_code: str
    bank_code: str
    currency: str
    fx_settlement_rate: Decimal = Decimal("0")
    fx_reference_rate: Decimal = Decimal("0")


@dataclass
class PartnerConfig:
    code: str
    name: str
    is_international: bool
    currency: str
    commission: PartnerCurrencyConfig = field(default_factory=lambda: PartnerCurrencyConfig("percentage"))
    fx: FxConfig = field(default_factory=FxConfig)
    channels: dict[str, PayoutChannelConfig] = field(default_factory=dict)


class EngineConfig:
    """In-memory parameter configuration loaded from config.json."""

    def __init__(self):
        self.partners: dict[str, PartnerConfig] = {}
        self.settlements: list[SettlementConfig] = []

    @classmethod
    def from_json(cls, path: str | Path) -> "EngineConfig":
        with open(path) as f:
            raw = json.load(f)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "EngineConfig":
        config = cls()

        for p in raw.get("layer1", []):
            comm = PartnerCurrencyConfig(
                commission_type=p.get("commission_type", "percentage"),
                commission_rate=Decimal(str(p.get("commission_rate", 0))),
                commission_fixed=Decimal(str(p.get("commission_fixed", 0))),
            )
            fx = FxConfig(
                fx_partner_rate=Decimal(str(p.get("fx_partner_rate", 0))),
                fx_cadorim_rate=Decimal(str(p.get("fx_cadorim_rate", 0))),
                fx_market_rate=Decimal(str(p.get("fx_market_rate", 0))),
            )
            channels = {}
            for ch in p.get("channels", []):
                channels[ch["code"]] = PayoutChannelConfig(
                    code=ch["code"],
                    cost_payout=Decimal(str(ch.get("cost_payout", 0))),
                    cost_type=ch.get("cost_type", "fixed"),
                )

            config.partners[p["code"]] = PartnerConfig(
                code=p["code"],
                name=p.get("name", p["code"]),
                is_international=p.get("is_international", False),
                currency=p.get("currency", "MRU"),
                commission=comm,
                fx=fx,
                channels=channels,
            )

        for s in raw.get("layer2", []):
            config.settlements.append(SettlementConfig(
                partner_code=s["partner_code"],
                bank_code=s["bank_code"],
                currency=s.get("currency", "USD"),
                fx_settlement_rate=Decimal(str(s.get("fx_settlement_rate", 0))),
                fx_reference_rate=Decimal(str(s.get("fx_reference_rate", 0))),
            ))

        return config

    def get_partner(self, partner_code: str) -> PartnerConfig | None:
        return self.partners.get(partner_code)

    def get_commission_config(self, partner_code: str) -> PartnerCurrencyConfig | None:
        p = self.partners.get(partner_code)
        return p.commission if p else None

    def get_fx_config(self, partner_code: str) -> FxConfig | None:
        p = self.partners.get(partner_code)
        return p.fx if p else None

    def get_channel_config(self, partner_code: str, channel_code: str) -> PayoutChannelConfig | None:
        p = self.partners.get(partner_code)
        if not p:
            return None
        return p.channels.get(channel_code)

    def get_settlement_config(self, partner_code: str, bank_code: str) -> SettlementConfig | None:
        for s in self.settlements:
            if s.partner_code == partner_code and s.bank_code == bank_code:
                return s
        return None

    def to_dict(self) -> dict:
        """Export back to JSON-serializable dict."""
        layer1 = []
        for p in self.partners.values():
            layer1.append({
                "code": p.code,
                "name": p.name,
                "is_international": p.is_international,
                "currency": p.currency,
                "commission_type": p.commission.commission_type,
                "commission_rate": str(p.commission.commission_rate),
                "commission_fixed": str(p.commission.commission_fixed),
                "fx_partner_rate": str(p.fx.fx_partner_rate),
                "fx_cadorim_rate": str(p.fx.fx_cadorim_rate),
                "fx_market_rate": str(p.fx.fx_market_rate),
                "channels": [
                    {"code": ch.code, "cost_payout": str(ch.cost_payout), "cost_type": ch.cost_type}
                    for ch in p.channels.values()
                ],
            })

        layer2 = []
        for s in self.settlements:
            layer2.append({
                "partner_code": s.partner_code,
                "bank_code": s.bank_code,
                "currency": s.currency,
                "fx_settlement_rate": str(s.fx_settlement_rate),
                "fx_reference_rate": str(s.fx_reference_rate),
            })

        return {"layer1": layer1, "layer2": layer2}
