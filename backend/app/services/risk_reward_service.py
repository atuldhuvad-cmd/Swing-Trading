import json
import hashlib
from typing import Dict, Any, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from ..models import RiskRewardResult, CandidateEvaluationRun

class RiskRewardService:
    @classmethod
    def serialize_config(cls, config: Dict[str, Any]) -> str:
        return json.dumps(config, sort_keys=True)
        
    @classmethod
    def get_config_fingerprint(cls, config: Dict[str, Any]) -> str:
        serialized = cls.serialize_config(config)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    @classmethod
    def calculate_risk_reward(
        cls,
        db: Session,
        evaluation_id: int,
        config: Dict[str, Any],
        technical_evidence: Dict[str, Any],
        current_price: float
    ) -> RiskRewardResult:
        config_snapshot = cls.serialize_config(config)
        config_fingerprint = cls.get_config_fingerprint(config)
        
        atr = technical_evidence.get('ATR14')
        support = technical_evidence.get('support', current_price * 0.9) # Simple fallback if not provided
        resistance = technical_evidence.get('resistance', current_price * 1.1)
        
        atr_multiplier = Decimal(str(config.get('atr_multiplier', 1.5)))
        buffer = Decimal(str(config.get('buffer_percent', 0.01)))
        
        stop_loss = None
        target = None
        risk = None
        reward = None
        rr_ratio = None
        entry = Decimal(str(current_price))
        
        if atr is not None and not (isinstance(atr, float) and (atr != atr or abs(atr) == float('inf'))):
            stop_loss = entry - (Decimal(str(atr)) * atr_multiplier)
        elif support is not None and support > 0:
            stop_loss = Decimal(str(support)) * (Decimal('1.0') - buffer)
            
        if resistance is not None and resistance > current_price:
            target = Decimal(str(resistance)) * (Decimal('1.0') - buffer)
            
        if stop_loss is not None and stop_loss > 0 and stop_loss < entry:
            risk = entry - stop_loss
            
        if target is not None and target > entry:
            reward = target - entry
            
        if risk is not None and risk > 0 and reward is not None and reward > 0:
            rr_ratio = reward / risk
            
        result = RiskRewardResult(
            evaluation_id=evaluation_id,
            support=Decimal(str(round(support, 4))) if support is not None else None,
            resistance=Decimal(str(round(resistance, 4))) if resistance is not None else None,
            entry_reference=Decimal(str(round(entry, 4))),
            stop_loss=Decimal(str(round(stop_loss, 4))) if stop_loss is not None else None,
            target=Decimal(str(round(target, 4))) if target is not None else None,
            risk_per_share=Decimal(str(round(risk, 4))) if risk is not None else None,
            reward_per_share=Decimal(str(round(reward, 4))) if reward is not None else None,
            risk_reward_ratio=Decimal(str(round(rr_ratio, 4))) if rr_ratio is not None else None,
            config_fingerprint=config_fingerprint,
            config_snapshot=config_snapshot
        )
        db.add(result)
        db.flush()
        return result
