import json
import hashlib
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from sqlalchemy.orm import Session
from ..models import CandidateEvaluationRun, CandidateCriterionResult
from .candidate_config import ACTIVE_CANDIDATE_CONFIG

class CandidateService:
    @classmethod
    def serialize_config(cls, config: Dict[str, Any]) -> str:
        return json.dumps(config, sort_keys=True)
        
    @classmethod
    def get_config_fingerprint(cls, config: Dict[str, Any]) -> str:
        serialized = cls.serialize_config(config)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    @classmethod
    def get_active_config(cls) -> Dict[str, Any]:
        return ACTIVE_CANDIDATE_CONFIG

    @staticmethod
    def _extract_observation(source_dict: Dict[str, Any], key: str) -> Tuple[Optional[float], str, str]:
        obs_dict = source_dict.get(key, {})
        if isinstance(obs_dict, dict):
            obs_val = obs_dict.get("value")
            obs_status = obs_dict.get("status", "UNKNOWN")
        else:
            obs_val = obs_dict
            obs_status = "KNOWN" if obs_val is not None else "UNKNOWN"

        numeric_state = "UNKNOWN"
        coerced = None
        if obs_val is None:
            return None, obs_status, "UNKNOWN"
        try:
            coerced = float(obs_val)
            if coerced != coerced or abs(coerced) == float("inf"):
                return None, obs_status, "UNKNOWN"
            numeric_state = "KNOWN"
        except (TypeError, ValueError):
            return None, obs_status, "UNKNOWN"
        return coerced, obs_status, numeric_state

    @classmethod
    def evaluate_candidate(
        cls,
        db: Session,
        stock_id: int,
        config: Dict[str, Any],
        technical_evidence: Dict[str, Any],
        fundamental_evidence: Dict[str, Any],
        technical_ref: str = None,
        fundamental_ref: int = None
    ) -> CandidateEvaluationRun:
        if not config:
            run = CandidateEvaluationRun(
                stock_id=stock_id,
                technical_snapshot_reference=technical_ref,
                fundamental_snapshot_id=fundamental_ref,
                classification='RULE_CONFIGURATION_REQUIRED',
                config_fingerprint='EMPTY',
                config_snapshot='{}'
            )
            db.add(run)
            db.flush()
            return run
            
        config_snapshot = cls.serialize_config(config)
        config_fingerprint = cls.get_config_fingerprint(config)
        
        results = []
        has_insufficient_data = False
        has_fail = False
        watch_reasons = []
        reject_reasons = []
        
        for crit in config.get('criteria', []):
            crit_id = crit['id']
            field = crit.get('field', crit_id)
            crit_type = crit.get('type', 'TECHNICAL')
            mandatory = crit.get('mandatory', True)
            threshold = crit.get('threshold')
            operator = crit.get('operator')
            compare_to = crit.get('compare_to')
            source_dict = technical_evidence if crit_type == 'TECHNICAL' else fundamental_evidence

            obs_val, obs_status, state = cls._extract_observation(source_dict, field)
            compare_val = None
            if compare_to:
                compare_val, compare_status, compare_state = cls._extract_observation(source_dict, compare_to)
                if compare_status in ['NOT_APPLICABLE', 'UNSUPPORTED']:
                    obs_status = compare_status
                elif compare_state == 'UNKNOWN' or compare_val is None:
                    state = 'UNKNOWN'
                    if obs_status not in ['NOT_APPLICABLE', 'UNSUPPORTED']:
                        obs_status = 'UNKNOWN'

            crit_state = 'UNKNOWN'
            reason = None
            stored_threshold = threshold

            if obs_status in ['NOT_APPLICABLE', 'UNSUPPORTED']:
                crit_state = 'NOT_APPLICABLE'
                reason = f"Metric is {obs_status}"
                if mandatory:
                    has_fail = True
                    reject_reasons.append(f"Failed mandatory criterion: {crit_id} ({obs_status})")
                else:
                    watch_reasons.append(f"Failed optional criterion: {crit_id} ({obs_status})")
            elif operator == 'KNOWN':
                if state == 'KNOWN' and obs_val is not None and obs_status not in ['UNKNOWN', 'STALE']:
                    crit_state = 'PASS'
                    reason = f"{field} is KNOWN"
                else:
                    crit_state = 'UNKNOWN'
                    reason = "Value is UNKNOWN"
                    if mandatory:
                        has_insufficient_data = True
            elif state == 'UNKNOWN' or obs_val is None:
                crit_state = 'UNKNOWN'
                reason = "Value is UNKNOWN"
                if mandatory:
                    has_insufficient_data = True
            else:
                right = compare_val if compare_to else threshold
                stored_threshold = right
                if compare_to and (compare_val is None):
                    crit_state = 'UNKNOWN'
                    reason = f"{compare_to} is UNKNOWN"
                    if mandatory:
                        has_insufficient_data = True
                elif operator == '>':
                    crit_state = 'PASS' if obs_val > right else 'FAIL'
                elif operator == '>=':
                    crit_state = 'PASS' if obs_val >= right else 'FAIL'
                elif operator == '<':
                    crit_state = 'PASS' if obs_val < right else 'FAIL'
                elif operator == '<=':
                    crit_state = 'PASS' if obs_val <= right else 'FAIL'
                else:
                    crit_state = 'UNKNOWN'
                    reason = f"Unsupported operator {operator}"
                    if mandatory:
                        has_insufficient_data = True

                if crit_state == 'FAIL':
                    if compare_to:
                        reason = f"{field} {operator} {compare_to} failed"
                    if mandatory:
                        has_fail = True
                        reject_reasons.append(f"Failed mandatory criterion: {crit_id}")
                    else:
                        watch_reasons.append(f"Failed optional criterion: {crit_id}")
                elif crit_state == 'PASS' and compare_to:
                    reason = f"{field} {operator} {compare_to}"

            results.append(CandidateCriterionResult(
                criterion_identifier=crit_id,
                observed_value=Decimal(str(obs_val)) if obs_val is not None else None,
                operator=operator,
                threshold=Decimal(str(stored_threshold)) if stored_threshold is not None else None,
                state=crit_state,
                reason=reason,
                evidence_reference=f"{crit_type}_{field}"
            ))

        if not config.get('criteria'):
            classification = 'RULE_CONFIGURATION_REQUIRED'
        elif has_insufficient_data:
            classification = 'INSUFFICIENT_DATA'
        elif has_fail:
            classification = 'REJECTED'
        elif watch_reasons:
            classification = 'WATCH'
        else:
            classification = 'FINAL_CANDIDATE'
            
        run = CandidateEvaluationRun(
            stock_id=stock_id,
            technical_snapshot_reference=technical_ref,
            fundamental_snapshot_id=fundamental_ref,
            classification=classification,
            config_fingerprint=config_fingerprint,
            config_snapshot=config_snapshot
        )
        db.add(run)
        db.flush()
        
        for res in results:
            res.evaluation_id = run.evaluation_id
            db.add(res)
        db.flush()
        return run
