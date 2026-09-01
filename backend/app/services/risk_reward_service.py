import json
import hashlib
from typing import Dict, Any
from decimal import Decimal
from sqlalchemy.orm import Session
from ..models import RiskRewardResult


class RiskRewardService:
    @classmethod
    def serialize_config(cls, config: Dict[str, Any]) -> str:
        return json.dumps(config, sort_keys=True)

    @classmethod
    def get_config_fingerprint(cls, config: Dict[str, Any]) -> str:
        serialized = cls.serialize_config(config)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def calculate_risk_reward(
        cls,
        db: Session,
        evaluation_id: int,
        config: Dict[str, Any],
        technical_evidence: Dict[str, Any],
        current_price: float,
    ) -> RiskRewardResult:
        atr = technical_evidence.get("ATR14")
        support = technical_evidence.get("support")
        if support is None:
            support = technical_evidence.get("Support20")
        resistance = technical_evidence.get("resistance")
        if resistance is None:
            resistance = technical_evidence.get("Resistance20")

        atr_multiplier = Decimal(str(config.get("atr_multiplier", 1.5)))
        buffer = Decimal(str(config.get("buffer_percent", 0.01)))
        entry = Decimal(str(current_price))

        stop_loss = None
        target = None
        risk = None
        reward = None
        rr_ratio = None
        methodology = {
            "entry": "provided current_price (typically latest close)",
            "support": "explicit support or prior-20-session low (Support20); never invented",
            "resistance": "explicit resistance or prior-20-session high (Resistance20); never invented",
            "stop": "entry - ATR14 * atr_multiplier when ATR is finite; else Support20 * (1 - buffer)",
            "target": "resistance * (1 - buffer) when resistance > entry",
        }

        atr_ok = atr is not None and not (
            isinstance(atr, float) and (atr != atr or abs(atr) == float("inf"))
        )
        if atr_ok:
            stop_loss = entry - (Decimal(str(atr)) * atr_multiplier)
        elif support is not None and Decimal(str(support)) > 0:
            stop_loss = Decimal(str(support)) * (Decimal("1.0") - buffer)

        if resistance is not None and Decimal(str(resistance)) > entry:
            target = Decimal(str(resistance)) * (Decimal("1.0") - buffer)

        if stop_loss is not None and stop_loss > 0 and stop_loss < entry:
            risk = entry - stop_loss
        else:
            stop_loss = None

        if target is not None and target > entry:
            reward = target - entry
        else:
            target = None

        if risk is not None and risk > 0 and reward is not None and reward > 0:
            rr_ratio = reward / risk

        snapshot_obj = {
            "config": config,
            "methodology": methodology,
            "insufficient": rr_ratio is None,
        }
        config_snapshot = json.dumps(snapshot_obj, sort_keys=True, default=str)
        config_fingerprint = hashlib.sha256(config_snapshot.encode("utf-8")).hexdigest()

        def q(val, places=4):
            if val is None:
                return None
            return Decimal(str(round(Decimal(str(val)), places)))

        result = RiskRewardResult(
            evaluation_id=evaluation_id,
            support=q(support),
            resistance=q(resistance),
            entry_reference=q(entry),
            stop_loss=q(stop_loss),
            target=q(target),
            risk_per_share=q(risk),
            reward_per_share=q(reward),
            risk_reward_ratio=q(rr_ratio),
            config_fingerprint=config_fingerprint,
            config_snapshot=config_snapshot,
        )
        db.add(result)
        db.flush()
        return result
