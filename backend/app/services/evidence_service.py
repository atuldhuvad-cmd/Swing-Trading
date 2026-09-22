from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    StockMaster, DailyOhlcv, DataImportBatch, CandidateEvaluationRun,
    CandidateCriterionResult, RiskRewardResult, FundamentalSnapshot, FundamentalMetric,
)
from app.services.corporate_action_service import CorporateActionService
from app.services.technical_service import TechnicalService
from app.services.consensus_service import ConsensusService


CLASSIFICATION_MEANING = {
    "FINAL_CANDIDATE": "Passes current Phase 5 trend screen.",
    "WATCH": "Primary trend criterion passes, trend confirmation fails.",
    "REJECTED": "Primary mandatory trend criterion fails.",
    "INSUFFICIENT_DATA": "Mandatory evidence unavailable.",
    "RULE_CONFIGURATION_REQUIRED": "Candidate rule configuration is required.",
}


def jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class EvidenceService:
    TECH_KEYS = [
        "SMA20", "SMA50", "SMA200", "RSI14", "MACD", "MACD_signal", "MACD_hist",
        "ATR14", "ATR_percent", "ROC20", "Breakout20_threshold", "Breakout20_status",
        "Support20", "Resistance20", "Liquidity20",
    ]

    @classmethod
    def technical_for_stock(cls, db: Session, stock_id: int) -> Dict[str, Any]:
        raw = (
            db.query(DailyOhlcv)
            .filter(DailyOhlcv.stock_id == stock_id, DailyOhlcv.series == "EQ")
            .order_by(DailyOhlcv.trading_date.asc())
            .all()
        )
        if not raw:
            return {
                "sessions": 0,
                "sma200_ready": False,
                "insufficient_history": True,
                "adjustment_status": "NO_DATA",
                "indicators": {k: None for k in cls.TECH_KEYS},
            }
        originals = [(r.open, r.high, r.low, r.close, r.volume, r.trading_date) for r in raw]
        adjusted = CorporateActionService.apply_adjustments(db, stock_id, raw)
        after = [(r.open, r.high, r.low, r.close, r.volume, r.trading_date) for r in raw]
        if originals != after:
            raise RuntimeError("Raw OHLCV mutated during adjustment")
        tech = TechnicalService.calculate_technical_evidence(adjusted)
        indicators = {k: jsonable(tech.get(k)) for k in cls.TECH_KEYS}
        sessions = tech.get("sessions", len(raw))
        return {
            "sessions": sessions,
            "sma200_ready": sessions >= 200,
            "insufficient_history": sessions < 20,
            "latest_trading_date": jsonable(tech.get("latest_trading_date")),
            "latest_close": jsonable(tech.get("latest_close")),
            "adjustment_status": tech.get("adjustment_status"),
            "indicators": indicators,
        }

    @classmethod
    def criteria_by_evaluation(cls, db: Session, evaluation_ids: List[int]) -> Dict[int, List[CandidateCriterionResult]]:
        """Criterion rows per evaluation in persisted order (result_id).

        CandidateService writes criteria in configuration order, so this is the
        rule sequence of the evaluation's own config snapshot. Every endpoint uses
        this so the same evaluation always lists the same criteria in the same order.
        """
        grouped: Dict[int, List[CandidateCriterionResult]] = {}
        if not evaluation_ids:
            return grouped
        rows = (
            db.query(CandidateCriterionResult)
            .filter(CandidateCriterionResult.evaluation_id.in_(evaluation_ids))
            .order_by(CandidateCriterionResult.evaluation_id.asc(), CandidateCriterionResult.result_id.asc())
            .all()
        )
        for row in rows:
            grouped.setdefault(row.evaluation_id, []).append(row)
        return grouped

    @classmethod
    def serialize_criterion(cls, row: CandidateCriterionResult) -> Dict[str, Any]:
        return {
            "criterion": row.criterion_identifier,
            "evidence_value": jsonable(row.observed_value),
            "operator": row.operator,
            "threshold": jsonable(row.threshold),
            "result": row.state,
            "reason": row.reason,
            "evidence_reference": row.evidence_reference,
        }

    @classmethod
    def decisive_reason(cls, classification: Optional[str], rows: List[CandidateCriterionResult]) -> Optional[str]:
        if not classification:
            return None
        by_id = {r.criterion_identifier: r for r in rows}
        if classification == "INSUFFICIENT_DATA":
            unknown = [r.criterion_identifier for r in rows if r.state == "UNKNOWN"]
            if unknown:
                return "Mandatory evidence unavailable: " + ", ".join(unknown)
            return CLASSIFICATION_MEANING[classification]
        if classification == "REJECTED":
            close = by_id.get("close_gt_sma50")
            if close and close.state == "FAIL":
                return close.reason or CLASSIFICATION_MEANING[classification]
            revenue = by_id.get("revenue_positive")
            if revenue and revenue.state == "FAIL":
                return revenue.reason or CLASSIFICATION_MEANING[classification]
            fails = [r for r in rows if r.state == "FAIL" and r.criterion_identifier != "sma50_gt_sma200"]
            if fails:
                return fails[0].reason or CLASSIFICATION_MEANING[classification]
            return CLASSIFICATION_MEANING[classification]
        if classification == "WATCH":
            confirm = by_id.get("sma50_gt_sma200")
            if confirm and confirm.state == "FAIL":
                return confirm.reason or CLASSIFICATION_MEANING[classification]
            return CLASSIFICATION_MEANING[classification]
        return CLASSIFICATION_MEANING.get(classification, classification)

    @classmethod
    def criterion_by_id(cls, rows: List[CandidateCriterionResult], identifier: str) -> Optional[Dict[str, Any]]:
        for row in rows:
            if row.criterion_identifier == identifier:
                return cls.serialize_criterion(row)
        return None

    @classmethod
    def latest_run(cls, db: Session, stock_id: int) -> Optional[CandidateEvaluationRun]:
        return (
            db.query(CandidateEvaluationRun)
            .filter(CandidateEvaluationRun.stock_id == stock_id)
            .order_by(CandidateEvaluationRun.evaluation_date.desc(), CandidateEvaluationRun.evaluation_id.desc())
            .first()
        )

    @classmethod
    def stock_evidence(cls, db: Session, stock: StockMaster) -> Dict[str, Any]:
        run = cls.latest_run(db, stock.stock_id)
        criteria = []
        criterion_rows: List[CandidateCriterionResult] = []
        if run:
            criterion_rows = cls.criteria_by_evaluation(db, [run.evaluation_id]).get(run.evaluation_id, [])
            criteria = [cls.serialize_criterion(r) for r in criterion_rows]
        rr = None
        if run:
            rr_res = (
                db.query(RiskRewardResult)
                .filter(RiskRewardResult.evaluation_id == run.evaluation_id)
                .order_by(RiskRewardResult.result_id.desc())
                .first()
            )
            if rr_res:
                rr = {
                    "result_id": rr_res.result_id,
                    "support": jsonable(rr_res.support),
                    "resistance": jsonable(rr_res.resistance),
                    "entry": jsonable(rr_res.entry_reference),
                    "entry_reference": jsonable(rr_res.entry_reference),
                    "target": jsonable(rr_res.target),
                    "stop": jsonable(rr_res.stop_loss),
                    "stop_loss": jsonable(rr_res.stop_loss),
                    "risk": jsonable(rr_res.risk_per_share),
                    "reward": jsonable(rr_res.reward_per_share),
                    "rr_ratio": jsonable(rr_res.risk_reward_ratio),
                    "methodology": rr_res.config_snapshot,
                }

        snapshot = (
            db.query(FundamentalSnapshot)
            .filter(FundamentalSnapshot.stock_id == stock.stock_id, FundamentalSnapshot.is_superseded == False)
            .order_by(FundamentalSnapshot.as_of_date.desc(), FundamentalSnapshot.captured_at.desc())
            .first()
        )
        fundamentals = []
        if snapshot:
            metrics = (
                db.query(FundamentalMetric)
                .filter(FundamentalMetric.snapshot_id == snapshot.snapshot_id)
                .order_by(FundamentalMetric.metric_name.asc())
                .all()
            )
            fundamentals = [
                {
                    "metric_name": m.metric_name,
                    "metric_value": jsonable(m.metric_value),
                    "status": m.status,
                }
                for m in metrics
            ]

        technical = cls.technical_for_stock(db, stock.stock_id)
        
        consensus_obj = ConsensusService.calculate_stock_consensus(db, stock.stock_id)
        consensus_data = {"status": "NO_CONSENSUS"}
        
        if consensus_obj and consensus_obj.metrics.unique_broker_count > 0:
            consensus_data = {
                "status": "CONSENSUS_AVAILABLE",
                "metrics": consensus_obj.metrics.model_dump(),
                "contributors": [c.model_dump() for c in consensus_obj.contributors],
                "rating_breakdown": [r.model_dump() for r in consensus_obj.rating_breakdown],
            }

        return {
            "stock": {
                "id": stock.stock_id,
                "nse_symbol": stock.nse_symbol,
                "company_name": stock.company_name,
            },
            "candidate": {
                "evaluation_id": run.evaluation_id if run else None,
                "classification": run.classification if run else None,
                "classification_meaning": CLASSIFICATION_MEANING.get(run.classification) if run else None,
                "decisive_reason": cls.decisive_reason(run.classification, criterion_rows) if run else None,
                "evaluation_date": jsonable(run.evaluation_date) if run else None,
                "config_fingerprint": run.config_fingerprint if run else None,
                "missing_evidence": run.classification == "INSUFFICIENT_DATA" if run else True,
            },
            "close_gt_sma50": cls.criterion_by_id(criterion_rows, "close_gt_sma50"),
            "sma50_gt_sma200": cls.criterion_by_id(criterion_rows, "sma50_gt_sma200"),
            "criteria": criteria,
            "technical": technical,
            "fundamentals": fundamentals,
            "fundamental_entity_type": snapshot.entity_type if snapshot else None,
            "fundamental_provenance": {
                "statement_scope": snapshot.statement_scope,
                "source_line_item": snapshot.source_line_item,
                "original_unit": snapshot.original_unit,
                "normalized_unit": "INR_CRORE",
            } if snapshot else None,
            "risk_reward": rr,
            "consensus": consensus_data,
        }

    @classmethod
    def list_candidates(cls, db: Session) -> List[Dict[str, Any]]:
        subq = (
            db.query(
                CandidateEvaluationRun.stock_id,
                func.max(CandidateEvaluationRun.evaluation_id).label("max_id"),
            )
            .group_by(CandidateEvaluationRun.stock_id)
            .subquery()
        )
        runs = (
            db.query(CandidateEvaluationRun)
            .join(subq, CandidateEvaluationRun.evaluation_id == subq.c.max_id)
            .order_by(CandidateEvaluationRun.evaluation_date.desc(), CandidateEvaluationRun.evaluation_id.desc())
            .all()
        )
        stock_ids = [r.stock_id for r in runs]
        stocks = {s.stock_id: s for s in db.query(StockMaster).filter(StockMaster.stock_id.in_(stock_ids)).all()} if stock_ids else {}
        rr_rows = (
            db.query(RiskRewardResult)
            .filter(RiskRewardResult.evaluation_id.in_([r.evaluation_id for r in runs]))
            .all()
        ) if runs else []
        rr_by_eval = {}
        for rr in rr_rows:
            rr_by_eval[rr.evaluation_id] = rr
        snap_rows = (
            db.query(FundamentalSnapshot)
            .filter(FundamentalSnapshot.stock_id.in_(stock_ids), FundamentalSnapshot.is_superseded == False)
            .all()
        ) if stock_ids else []
        snap_by_stock = {s.stock_id: s for s in snap_rows}

        crit_by_eval = cls.criteria_by_evaluation(db, [r.evaluation_id for r in runs])
        snap_ids = [s.snapshot_id for s in snap_rows]
        revenue_by_snap: Dict[int, FundamentalMetric] = {}
        if snap_ids:
            for metric in (
                db.query(FundamentalMetric)
                .filter(FundamentalMetric.snapshot_id.in_(snap_ids), FundamentalMetric.metric_name == "revenue")
                .all()
            ):
                revenue_by_snap[metric.snapshot_id] = metric

        items = []
        for run in runs:
            stock = stocks.get(run.stock_id)
            if not stock:
                continue
            tech = cls.technical_for_stock(db, stock.stock_id)
            rr = rr_by_eval.get(run.evaluation_id)
            snap = snap_by_stock.get(run.stock_id)
            fund_state = "UNKNOWN"
            revenue_value = None
            revenue_status = "UNKNOWN"
            if snap:
                fund_state = "PRESENT"
                revenue = revenue_by_snap.get(snap.snapshot_id)
                if revenue:
                    revenue_value = jsonable(revenue.metric_value)
                    revenue_status = revenue.status
            rows = crit_by_eval.get(run.evaluation_id, [])
            items.append({
                "stock_id": stock.stock_id,
                "nse_symbol": stock.nse_symbol,
                "company_name": stock.company_name,
                "evaluation_id": run.evaluation_id,
                "status": run.classification,
                "classification_meaning": CLASSIFICATION_MEANING.get(run.classification),
                "decisive_reason": cls.decisive_reason(run.classification, rows),
                "config_fingerprint": run.config_fingerprint,
                "evaluation_date": jsonable(run.evaluation_date),
                "latest_close": tech.get("latest_close"),
                "technical": tech["indicators"],
                "fundamental_state": fund_state,
                "revenue": revenue_value,
                "revenue_status": revenue_status,
                "criteria": [cls.serialize_criterion(r) for r in rows],
                "close_gt_sma50": cls.criterion_by_id(rows, "close_gt_sma50"),
                "sma50_gt_sma200": cls.criterion_by_id(rows, "sma50_gt_sma200"),
                "entry": jsonable(rr.entry_reference) if rr else None,
                "target": jsonable(rr.target) if rr else None,
                "stop": jsonable(rr.stop_loss) if rr else None,
                "rr_ratio": jsonable(rr.risk_reward_ratio) if rr else None,
                "rr_available": rr is not None and rr.risk_reward_ratio is not None,
            })
        return items

    @classmethod
    def market_data_status(cls, db: Session) -> List[Dict[str, Any]]:
        stocks = db.query(StockMaster).order_by(StockMaster.nse_symbol.asc()).all()
        stats = {
            r.stock_id: r
            for r in db.query(
                DailyOhlcv.stock_id,
                func.count(DailyOhlcv.daily_ohlcv_id).label("sessions"),
                func.max(DailyOhlcv.trading_date).label("latest_trading_date"),
                func.max(DailyOhlcv.import_batch_id).label("latest_batch_id"),
            ).group_by(DailyOhlcv.stock_id).all()
        }
        batch_ids = [s.latest_batch_id for s in stats.values() if s.latest_batch_id]
        batches = {
            b.import_batch_id: b
            for b in db.query(DataImportBatch).filter(DataImportBatch.import_batch_id.in_(batch_ids)).all()
        } if batch_ids else {}
        out = []
        for stock in stocks:
            st = stats.get(stock.stock_id)
            sessions = int(st.sessions) if st else 0
            batch = batches.get(st.latest_batch_id) if st and st.latest_batch_id else None
            out.append({
                "stock_id": stock.stock_id,
                "nse_symbol": stock.nse_symbol,
                "company_name": stock.company_name,
                "latest_trading_date": jsonable(st.latest_trading_date) if st else None,
                "session_count": sessions,
                "sma200_ready": sessions >= 200,
                "latest_import_status": batch.status if batch else None,
                "latest_import_filename": batch.original_filename if batch else None,
            })
        return out
