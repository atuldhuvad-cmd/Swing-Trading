from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, desc
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import statistics

from app.models import (
    StockMaster, BrokerMaster, BrokerRecommendation, 
    SourceReference, RecommendationSource, StockPrice
)
from app.schemas.consensus import (
    StockConsensusOut, ConsensusMetricsOut, RatingBreakdownItem,
    BrokerContributorOut, SourceReferenceOut, CandidateConsensusSummaryOut,
    CandidateListResponse
)

DEFAULT_BULLISH_RATINGS = {'BUY', 'STRONG_BUY', 'ACCUMULATE', 'OUTPERFORM'}

class ConsensusService:
    @staticmethod
    def _get_now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def get_latest_recommendations_per_broker(
        db: Session, 
        stock_id: Optional[int] = None,
        lifecycle_status: str = 'CURRENT',
        verification_status: str = 'ALL'
    ) -> List[Dict[str, Any]]:
        """
        Executes a SQLite-compatible ROW_NUMBER() window function query
        to retrieve the latest recommendation per broker per stock.
        """
        now = ConsensusService._get_now()
        
        # Build base CTE / subquery with window function
        subq = db.query(
            BrokerRecommendation.recommendation_id.label('rec_id'),
            func.row_number().over(
                partition_by=(BrokerRecommendation.stock_id, BrokerRecommendation.broker_id),
                order_by=(desc(BrokerRecommendation.recommendation_date), desc(BrokerRecommendation.recommendation_id))
            ).label('rn')
        )
        
        if lifecycle_status != 'ALL':
            subq = subq.filter(BrokerRecommendation.lifecycle_status == lifecycle_status)
            
        if stock_id is not None:
            subq = subq.filter(BrokerRecommendation.stock_id == stock_id)
            
        subq = subq.subquery()

        # Query top-ranked recommendations (rn == 1) joined with BrokerRecommendation & BrokerMaster
        query = db.query(BrokerRecommendation, BrokerMaster).join(
            subq, BrokerRecommendation.recommendation_id == subq.c.rec_id
        ).join(
            BrokerMaster, BrokerRecommendation.broker_id == BrokerMaster.broker_id
        ).filter(subq.c.rn == 1)

        results = query.all()
        
        # Process and filter by verification_status if needed
        output = []
        for rec, broker in results:
            rec_id = rec.recommendation_id
            
            # Fetch attached sources
            sources = db.query(SourceReference).join(
                RecommendationSource, RecommendationSource.source_reference_id == SourceReference.source_reference_id
            ).filter(RecommendationSource.recommendation_id == rec_id).all()
            
            # Check verification filter
            if verification_status != 'ALL':
                if verification_status == 'VERIFIED_ONLY':
                    verified_sources = [s for s in sources if s.verification_status in ('VERIFIED_PRIMARY', 'VERIFIED_SECONDARY')]
                    if not verified_sources:
                        continue
                else:
                    matching_sources = [s for s in sources if s.verification_status == verification_status]
                    if not matching_sources:
                        continue

            rec_date = rec.recommendation_date
            age_days = max(0, (now - rec_date).days) if rec_date else 0
            
            if age_days <= 30:
                freshness_category = 'FRESH'
            elif age_days <= 60:
                freshness_category = 'MODERATE'
            else:
                freshness_category = 'AGED'
                
            overall_ver_status = 'UNVERIFIED'
            if sources:
                if any(s.verification_status == 'VERIFIED_PRIMARY' for s in sources):
                    overall_ver_status = 'VERIFIED_PRIMARY'
                elif any(s.verification_status == 'VERIFIED_SECONDARY' for s in sources):
                    overall_ver_status = 'VERIFIED_SECONDARY'
                elif any(s.verification_status == 'PROVISIONAL' for s in sources):
                    overall_ver_status = 'PROVISIONAL'
                elif any(s.verification_status == 'REJECTED' for s in sources):
                    overall_ver_status = 'REJECTED'

            output.append({
                'recommendation_id': rec.recommendation_id,
                'stock_id': rec.stock_id,
                'broker_id': rec.broker_id,
                'broker_canonical_name': broker.canonical_name,
                'broker_display_name': broker.display_name,
                'recommendation_date': rec.recommendation_date,
                'original_rating': rec.original_rating,
                'normalized_rating': rec.normalized_rating,
                'recommended_price': rec.recommended_price,
                'entry_price_low': rec.entry_price_low,
                'entry_price_high': rec.entry_price_high,
                'target_price': rec.target_price,
                'stop_loss': rec.stop_loss,
                'analyst_name': rec.analyst_name,
                'lifecycle_status': rec.lifecycle_status,
                'age_days': age_days,
                'freshness_category': freshness_category,
                'verification_status': overall_ver_status,
                'sources': sources
            })
            
        return output

    @staticmethod
    def calculate_stock_consensus(
        db: Session,
        stock_id: int,
        verification_status: str = 'ALL',
        eligible_ratings: Optional[List[str]] = None
    ) -> Optional[StockConsensusOut]:
        stock = db.query(StockMaster).filter(StockMaster.stock_id == stock_id).first()
        if not stock:
            return None

        # Fetch CMP from StockPrice
        stock_price = db.query(StockPrice).filter(StockPrice.stock_id == stock_id).first()
        cmp_val = stock_price.last_price if stock_price else None
        cmp_updated_at = stock_price.updated_at if stock_price else None

        # Fetch latest recommendations per broker
        contributors_raw = ConsensusService.get_latest_recommendations_per_broker(
            db, stock_id=stock_id, lifecycle_status='CURRENT', verification_status=verification_status
        )

        eligible_set = set(r.upper() for r in (eligible_ratings or DEFAULT_BULLISH_RATINGS))

        unique_broker_count = len(contributors_raw)
        bullish_count = 0
        target_prices = []
        ages = []
        rating_counts: Dict[str, int] = {}
        rec_count_7d = 0
        rec_count_14d = 0
        rec_count_30d = 0

        contributors_out = []
        for c in contributors_raw:
            norm_rating = (c['normalized_rating'] or '').upper()
            rating_counts[norm_rating] = rating_counts.get(norm_rating, 0) + 1
            
            if norm_rating in eligible_set:
                bullish_count += 1
                
            if c['target_price'] is not None and c['target_price'] > 0:
                target_prices.append(c['target_price'])
                
            age_days = c['age_days']
            ages.append(age_days)
            if age_days <= 7:
                rec_count_7d += 1
            if age_days <= 14:
                rec_count_14d += 1
            if age_days <= 30:
                rec_count_30d += 1

            sources_out = [
                SourceReferenceOut(
                    source_reference_id=s.source_reference_id,
                    source_type_id=s.source_type_id,
                    publication_name=s.publication_name,
                    url=s.url,
                    source_date=s.source_date,
                    verification_status=s.verification_status,
                    reliability_score=s.reliability_score,
                    verification_notes=s.verification_notes
                ) for s in c['sources']
            ]

            contributors_out.append(
                BrokerContributorOut(
                    recommendation_id=c['recommendation_id'],
                    broker_id=c['broker_id'],
                    broker_canonical_name=c['broker_canonical_name'],
                    broker_display_name=c['broker_display_name'],
                    recommendation_date=c['recommendation_date'],
                    original_rating=c['original_rating'],
                    normalized_rating=c['normalized_rating'],
                    recommended_price=c['recommended_price'],
                    entry_price_low=c['entry_price_low'],
                    entry_price_high=c['entry_price_high'],
                    target_price=c['target_price'],
                    stop_loss=c['stop_loss'],
                    analyst_name=c['analyst_name'],
                    lifecycle_status=c['lifecycle_status'],
                    age_days=c['age_days'],
                    freshness_category=c['freshness_category'],
                    verification_status=c['verification_status'],
                    sources=sources_out
                )
            )

        bullish_pct = round((bullish_count / unique_broker_count * 100.0), 2) if unique_broker_count > 0 else 0.0
        
        # Target statistics
        total_target_count = len(target_prices)
        target_coverage_pct = round((total_target_count / unique_broker_count * 100.0), 2) if unique_broker_count > 0 else 0.0

        min_target = round(min(target_prices), 2) if target_prices else None
        max_target = round(max(target_prices), 2) if target_prices else None
        avg_target = round(sum(target_prices) / total_target_count, 2) if target_prices else None
        
        # Median target calculated in Python logic
        median_target = None
        if target_prices:
            sorted_targets = sorted(target_prices)
            n = len(sorted_targets)
            if n % 2 == 1:
                median_target = round(sorted_targets[n // 2], 2)
            else:
                median_target = round((sorted_targets[n // 2 - 1] + sorted_targets[n // 2]) / 2.0, 2)

        # Upside calculations
        avg_target_upside_pct = None
        median_target_upside_pct = None
        if cmp_val is not None and cmp_val > 0:
            if avg_target is not None:
                avg_target_upside_pct = round(((avg_target - cmp_val) / cmp_val) * 100.0, 2)
            if median_target is not None:
                median_target_upside_pct = round(((median_target - cmp_val) / cmp_val) * 100.0, 2)

        # Age & freshness summary
        avg_age_days = round(sum(ages) / len(ages), 1) if ages else None
        freshness_summary = 'NONE'
        if avg_age_days is not None:
            if avg_age_days <= 30:
                freshness_summary = 'FRESH'
            elif avg_age_days <= 60:
                freshness_summary = 'MODERATE'
            else:
                freshness_summary = 'AGED'

        # Rating breakdown
        rating_breakdown = [
            RatingBreakdownItem(
                rating=rating,
                count=cnt,
                percentage=round((cnt / unique_broker_count * 100.0), 2) if unique_broker_count > 0 else 0.0
            ) for rating, cnt in rating_counts.items()
        ]

        metrics = ConsensusMetricsOut(
            unique_broker_count=unique_broker_count,
            bullish_broker_count=bullish_count,
            bullish_percentage=bullish_pct,
            total_target_count=total_target_count,
            target_coverage_pct=target_coverage_pct,
            min_target=min_target,
            max_target=max_target,
            avg_target=avg_target,
            median_target=median_target,
            cmp=cmp_val,
            avg_target_upside_pct=avg_target_upside_pct,
            median_target_upside_pct=median_target_upside_pct,
            avg_age_days=avg_age_days,
            freshness_summary=freshness_summary,
            rec_count_7d=rec_count_7d,
            rec_count_14d=rec_count_14d,
            rec_count_30d=rec_count_30d
        )

        return StockConsensusOut(
            stock_id=stock.stock_id,
            nse_symbol=stock.nse_symbol,
            bse_symbol=stock.bse_symbol,
            company_name=stock.company_name,
            isin=stock.isin,
            sector=stock.sector,
            industry=stock.industry,
            market_cap_category=stock.market_cap_category,
            listing_status=stock.listing_status,
            cmp=cmp_val,
            cmp_updated_at=cmp_updated_at,
            metrics=metrics,
            rating_breakdown=rating_breakdown,
            contributors=contributors_out
        )

    @staticmethod
    def get_candidate_universe(
        db: Session,
        min_brokers: int = 1,
        min_upside: Optional[float] = None,
        min_bullish_pct: Optional[float] = None,
        max_age_days: Optional[int] = None,
        verification_status: str = 'ALL',
        eligible_ratings: Optional[List[str]] = None,
        sort_by: str = 'broker_count',
        sort_order: str = 'desc',
        skip: int = 0,
        limit: int = 100
    ) -> CandidateListResponse:

        stocks = db.query(StockMaster).filter(StockMaster.listing_status == 'ACTIVE').all()

        candidate_summaries: List[CandidateConsensusSummaryOut] = []
        for s in stocks:
            consensus = ConsensusService.calculate_stock_consensus(
                db, stock_id=s.stock_id, verification_status=verification_status, eligible_ratings=eligible_ratings
            )
            if not consensus:
                continue

            m = consensus.metrics
            
            # Apply Candidate Filters
            if m.unique_broker_count < min_brokers:
                continue
                
            if min_bullish_pct is not None and m.bullish_percentage < min_bullish_pct:
                continue

            if max_age_days is not None:
                if m.avg_age_days is None or m.avg_age_days > max_age_days:
                    continue

            if min_upside is not None:
                # Compare upside: check if either avg or median upside meets min_upside
                best_upside = None
                if m.avg_target_upside_pct is not None and m.median_target_upside_pct is not None:
                    best_upside = max(m.avg_target_upside_pct, m.median_target_upside_pct)
                elif m.avg_target_upside_pct is not None:
                    best_upside = m.avg_target_upside_pct
                elif m.median_target_upside_pct is not None:
                    best_upside = m.median_target_upside_pct

                if best_upside is None or best_upside < min_upside:
                    continue

            latest_date = max((c.recommendation_date for c in consensus.contributors), default=None)

            candidate_summaries.append(
                CandidateConsensusSummaryOut(
                    stock_id=s.stock_id,
                    nse_symbol=s.nse_symbol,
                    company_name=s.company_name,
                    sector=s.sector,
                    cmp=m.cmp,
                    unique_broker_count=m.unique_broker_count,
                    bullish_broker_count=m.bullish_broker_count,
                    bullish_percentage=m.bullish_percentage,
                    avg_target=m.avg_target,
                    median_target=m.median_target,
                    avg_target_upside_pct=m.avg_target_upside_pct,
                    median_target_upside_pct=m.median_target_upside_pct,
                    target_coverage_pct=m.target_coverage_pct,
                    rec_count_30d=m.rec_count_30d,
                    avg_age_days=m.avg_age_days,
                    freshness_summary=m.freshness_summary,
                    latest_rec_date=latest_date
                )
            )

        # Sorting logic
        reverse = (sort_order.lower() == 'desc')
        if sort_by == 'broker_count':
            candidate_summaries.sort(key=lambda x: x.unique_broker_count, reverse=reverse)
        elif sort_by == 'avg_upside':
            candidate_summaries.sort(key=lambda x: (x.avg_target_upside_pct if x.avg_target_upside_pct is not None else -999999.0), reverse=reverse)
        elif sort_by == 'median_upside':
            candidate_summaries.sort(key=lambda x: (x.median_target_upside_pct if x.median_target_upside_pct is not None else -999999.0), reverse=reverse)
        elif sort_by == 'recent_activity':
            candidate_summaries.sort(key=lambda x: x.rec_count_30d, reverse=reverse)
        elif sort_by == 'symbol':
            candidate_summaries.sort(key=lambda x: x.nse_symbol, reverse=reverse)

        total = len(candidate_summaries)
        paginated_items = candidate_summaries[skip : skip + limit]

        return CandidateListResponse(
            total=total,
            items=paginated_items
        )
