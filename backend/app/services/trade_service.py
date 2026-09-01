from sqlalchemy.orm import Session
from app.models import TradeJournal
from app.schemas.trade import TradeJournalCreate, TradeJournalUpdate, PositionSizeRequest, PositionSizeResponse
from decimal import Decimal
from datetime import datetime
import math

class TradeService:
    @staticmethod
    def calculate_position_size(req: PositionSizeRequest) -> PositionSizeResponse:
        if req.entry_price <= 0 or req.stop_price <= 0 or req.max_risk_amount <= 0:
            return PositionSizeResponse(status='NOT_CALCULATED', reason='Invalid prices or risk amount')
        
        if req.entry_price <= req.stop_price:
            return PositionSizeResponse(status='NOT_CALCULATED', reason='Stop price must be below entry price for LONG trades')

        per_share_risk = req.entry_price - req.stop_price
        raw_quantity = req.max_risk_amount / per_share_risk
        
        # Floor quantity to nearest whole share
        quantity = math.floor(raw_quantity)

        if req.max_capital_allocation and req.max_capital_allocation > 0:
            max_qty_by_cap = math.floor(req.max_capital_allocation / req.entry_price)
            quantity = min(quantity, max_qty_by_cap)

        if quantity <= 0:
            return PositionSizeResponse(status='NOT_CALCULATED', reason='Risk budget too small for a single share')

        total_capital = Decimal(quantity) * req.entry_price

        return PositionSizeResponse(
            status='CALCULATED',
            quantity=quantity,
            per_share_risk=per_share_risk,
            total_capital=total_capital
        )

    @staticmethod
    def _validate_linkage(db: Session, trade_in):
        if trade_in.candidate_evaluation_id:
            from app.models import CandidateEvaluationRun
            run = db.query(CandidateEvaluationRun).filter_by(evaluation_id=trade_in.candidate_evaluation_id).first()
            if not run or run.stock_id != trade_in.stock_id:
                raise ValueError("Candidate evaluation does not belong to the given stock")
        if trade_in.risk_reward_result_id:
            from app.models import RiskRewardResult
            rr = db.query(RiskRewardResult).filter_by(result_id=trade_in.risk_reward_result_id).first()
            if not rr:
                raise ValueError("Risk reward result not found")
            if trade_in.candidate_evaluation_id and rr.evaluation_id != trade_in.candidate_evaluation_id:
                raise ValueError("Risk reward result does not belong to the given candidate evaluation")
            if not trade_in.candidate_evaluation_id:
                # If they passed RR but not run, we still check stock
                run_for_rr = db.query(CandidateEvaluationRun).filter_by(evaluation_id=rr.evaluation_id).first()
                if run_for_rr and run_for_rr.stock_id != trade_in.stock_id:
                    raise ValueError("Risk reward result does not belong to the given stock")

    @staticmethod
    def create_trade(db: Session, trade_in: TradeJournalCreate) -> TradeJournal:
        TradeService._validate_linkage(db, trade_in)
        trade = TradeJournal(**trade_in.model_dump())
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade

    @staticmethod
    def update_trade(db: Session, trade_id: int, trade_in: TradeJournalUpdate) -> TradeJournal:
        trade = db.query(TradeJournal).filter(TradeJournal.trade_id == trade_id).first()
        if not trade:
            return None

        # Validate lifecycle transitions
        if trade_in.status and trade_in.status != trade.status:
            valid_transitions = {
                'PLANNED': ['OPEN', 'CANCELLED'],
                'OPEN': ['CLOSED'],
                'CLOSED': [],
                'CANCELLED': []
            }
            if trade_in.status not in valid_transitions.get(trade.status, []):
                raise ValueError(f"Invalid transition from {trade.status} to {trade_in.status}")

        update_data = trade_in.model_dump(exclude_unset=True)
        
        # Merge old and new state to validate requirements
        merged = {**trade.__dict__, **update_data}

        new_status = merged.get('status')
        if new_status == 'OPEN':
            qty = merged.get('quantity')
            ep = merged.get('entry_price')
            if not qty or qty <= 0:
                raise ValueError("OPEN trades require quantity > 0")
            if not ep or ep <= 0:
                raise ValueError("OPEN trades require entry_price > 0")
            if not merged.get('entry_date'):
                raise ValueError("OPEN trades require entry_date")
            if not merged.get('entry_price_source'):
                raise ValueError("OPEN trades require entry_price_source")

        if new_status == 'CLOSED':
            xp = merged.get('exit_price')
            if not xp or xp <= 0:
                raise ValueError("CLOSED trades require exit_price > 0")
            if not merged.get('exit_date'):
                raise ValueError("CLOSED trades require exit_date")
            if not merged.get('exit_price_source'):
                raise ValueError("CLOSED trades require exit_price_source")

        for key, value in update_data.items():
            setattr(trade, key, value)

        if trade.status == 'CLOSED' and trade.entry_price and trade.exit_price and trade.quantity:
            trade.gross_pnl = (trade.exit_price - trade.entry_price) * trade.quantity
            if getattr(trade, 'manual_charges', None) is not None:
                trade.net_pnl = trade.gross_pnl - trade.manual_charges
            else:
                trade.net_pnl = None
        else:
            trade.gross_pnl = None
            trade.net_pnl = None

        db.commit()
        db.refresh(trade)
        return trade

    @staticmethod
    def get_trade(db: Session, trade_id: int) -> TradeJournal:
        return db.query(TradeJournal).filter(TradeJournal.trade_id == trade_id).first()

    @staticmethod
    def get_trades(db: Session, skip: int = 0, limit: int = 100) -> list[TradeJournal]:
        return db.query(TradeJournal).order_by(TradeJournal.created_at.desc()).offset(skip).limit(limit).all()
