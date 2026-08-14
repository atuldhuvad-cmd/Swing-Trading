import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from ..models import CandidateEvaluationRun, CandidateCriterionResult

class CandidateService:
    @classmethod
    def serialize_config(cls, config: Dict[str, Any]) -> str:
        return json.dumps(config, sort_keys=True)
        
    @classmethod
    def get_config_fingerprint(cls, config: Dict[str, Any]) -> str:
        serialized = cls.serialize_config(config)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

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
            crit_type = crit.get('type', 'TECHNICAL')
            mandatory = crit.get('mandatory', True)
            threshold = crit.get('threshold')
            operator = crit.get('operator')
            source_dict = technical_evidence if crit_type == 'TECHNICAL' else fundamental_evidence
            
            obs_dict = source_dict.get(crit_id, {})
            # Handle standard tech dict or fundamental dict (which has 'value' and 'status')
            if isinstance(obs_dict, dict):
                obs_val = obs_dict.get('value')
                obs_status = obs_dict.get('status', 'UNKNOWN')
            else:
                obs_val = obs_dict
                obs_status = 'KNOWN' if obs_val is not None else 'UNKNOWN'
                
            if obs_val is None:
                state = 'UNKNOWN'
            else:
                try:
                    obs_val = float(obs_val)
                    if obs_val != obs_val: # NaN check
                        state = 'UNKNOWN'
                        obs_val = None
                    elif abs(obs_val) == float('inf'):
                        state = 'UNKNOWN'
                        obs_val = None
                    else:
                        state = 'KNOWN'
                except:
                    state = 'UNKNOWN'
                    
            crit_state = 'UNKNOWN'
            reason = None
            
            if obs_status in ['NOT_APPLICABLE', 'UNSUPPORTED']:
                crit_state = 'NOT_APPLICABLE'
                reason = f"Metric is {obs_status}"
                if mandatory:
                    has_fail = True
                    reject_reasons.append(f"Failed mandatory criterion: {crit_id} ({obs_status})")
                else:
                    watch_reasons.append(f"Failed optional criterion: {crit_id} ({obs_status})")
            elif state == 'UNKNOWN' or obs_val is None:
                crit_state = 'UNKNOWN'
                reason = "Value is UNKNOWN"
                if mandatory:
                    has_insufficient_data = True
            else:
                if operator == '>':
                    crit_state = 'PASS' if obs_val > threshold else 'FAIL'
                elif operator == '>=':
                    crit_state = 'PASS' if obs_val >= threshold else 'FAIL'
                elif operator == '<':
                    crit_state = 'PASS' if obs_val < threshold else 'FAIL'
                elif operator == '<=':
                    crit_state = 'PASS' if obs_val <= threshold else 'FAIL'
                else:
                    crit_state = 'UNKNOWN'
                    
                if crit_state == 'FAIL':
                    if mandatory:
                        has_fail = True
                        reject_reasons.append(f"Failed mandatory criterion: {crit_id}")
                    else:
                        watch_reasons.append(f"Failed optional criterion: {crit_id}")
                        
            # preserve result
            results.append(CandidateCriterionResult(
                criterion_identifier=crit_id,
                observed_value=Decimal(str(obs_val)) if obs_val is not None else None,
                operator=operator,
                threshold=Decimal(str(threshold)) if threshold is not None else None,
                state=crit_state,
                reason=reason,
                evidence_reference=f"{crit_type}_{crit_id}"
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
            
        return run
