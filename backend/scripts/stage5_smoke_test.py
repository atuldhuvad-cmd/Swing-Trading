import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import Base
from app.models import (
    StockMaster, BrokerMaster, BrokerRecommendation, SourceReference,
    RecommendationSource, StockPrice, SourceTypeMaster
)
from app.services.consensus_service import ConsensusService

def run_stage5_smoke_test():
    print("==================================================")
    print("STARTING STAGE 5 TEMPORARY-DB SMOKE WORKFLOW")
    print("==================================================")

    # 1. Setup isolated temporary SQLite DB
    db_path = "stage5_smoke_temp.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # 2. Setup Source Types
        st = SourceTypeMaster(type_name="WEBSITE", description="Web Article")
        db.add(st)
        db.commit()
        db.refresh(st)

        # 3. Create Stocks & CMPs
        stock1 = StockMaster(nse_symbol="RELIANCE_SMOKE", company_name="Reliance Industries Smoke Test", sector="Energy")
        stock2 = StockMaster(nse_symbol="TCS_SMOKE", company_name="Tata Consultancy Services Smoke Test", sector="IT")
        db.add_all([stock1, stock2])
        db.commit()

        sp1 = StockPrice(stock_id=stock1.stock_id, last_price=2500.0)
        sp2 = StockPrice(stock_id=stock2.stock_id, last_price=4000.0)
        db.add_all([sp1, sp2])
        db.commit()

        # 4. Create Brokers
        b1 = BrokerMaster(canonical_name="ICICI Direct", normalized_name="icici_direct", display_name="ICICI Direct")
        b2 = BrokerMaster(canonical_name="HDFC Securities", normalized_name="hdfc_securities", display_name="HDFC Securities")
        b3 = BrokerMaster(canonical_name="Motilal Oswal", normalized_name="motilal_oswal", display_name="Motilal Oswal")
        b4 = BrokerMaster(canonical_name="Axis Capital", normalized_name="axis_capital", display_name="Axis Capital")
        db.add_all([b1, b2, b3, b4])
        db.commit()

        now = datetime.utcnow()

        # 5. Insert Recommendations for RELIANCE_SMOKE
        # ICICI Direct: Old rec (10d ago, target 2800) SUPERSEDED
        rec_icici_old = BrokerRecommendation(
            stock_id=stock1.stock_id, broker_id=b1.broker_id, recommendation_date=now - timedelta(days=10),
            original_rating="BUY", normalized_rating="BUY", target_price=2800.0, lifecycle_status="SUPERSEDED"
        )
        # ICICI Direct: New rec (2d ago, target 3000) CURRENT
        rec_icici_new = BrokerRecommendation(
            stock_id=stock1.stock_id, broker_id=b1.broker_id, recommendation_date=now - timedelta(days=2),
            original_rating="BUY", normalized_rating="BUY", target_price=3000.0, lifecycle_status="CURRENT"
        )

        # HDFC Securities: Rec (5d ago, target 3200) CURRENT
        rec_hdfc = BrokerRecommendation(
            stock_id=stock1.stock_id, broker_id=b2.broker_id, recommendation_date=now - timedelta(days=5),
            original_rating="BUY", normalized_rating="BUY", target_price=3200.0, lifecycle_status="CURRENT"
        )

        # Motilal Oswal: Rec (1d ago, target 2900) CURRENT with 3 attached evidence sources
        rec_motilal = BrokerRecommendation(
            stock_id=stock1.stock_id, broker_id=b3.broker_id, recommendation_date=now - timedelta(days=1),
            original_rating="BUY", normalized_rating="BUY", target_price=2900.0, lifecycle_status="CURRENT"
        )

        db.add_all([rec_icici_old, rec_icici_new, rec_hdfc, rec_motilal])
        db.commit()

        # Attach 3 evidence sources to rec_motilal to test non-inflation
        src1 = SourceReference(source_type_id=st.source_type_id, publication_name="Moneycontrol", url="http://mc.com/motilal", verification_status="VERIFIED_PRIMARY")
        src2 = SourceReference(source_type_id=st.source_type_id, publication_name="Economic Times", url="http://et.com/motilal", verification_status="VERIFIED_SECONDARY")
        src3 = SourceReference(source_type_id=st.source_type_id, publication_name="Motilal Portal", url="http://motilal.com/report", verification_status="VERIFIED_PRIMARY")
        db.add_all([src1, src2, src3])
        db.commit()

        db.add_all([
            RecommendationSource(recommendation_id=rec_motilal.recommendation_id, source_reference_id=src1.source_reference_id),
            RecommendationSource(recommendation_id=rec_motilal.recommendation_id, source_reference_id=src2.source_reference_id),
            RecommendationSource(recommendation_id=rec_motilal.recommendation_id, source_reference_id=src3.source_reference_id),
        ])
        db.commit()

        # 6. Insert Recommendation for TCS_SMOKE (70 days old, CURRENT)
        rec_tcs = BrokerRecommendation(
            stock_id=stock2.stock_id, broker_id=b4.broker_id, recommendation_date=now - timedelta(days=70),
            original_rating="BUY", normalized_rating="BUY", target_price=4800.0, lifecycle_status="CURRENT"
        )
        db.add(rec_tcs)
        db.commit()

        # 7. Test Consensus Service on RELIANCE_SMOKE
        c1 = ConsensusService.calculate_stock_consensus(db, stock1.stock_id)
        assert c1 is not None, "Consensus object for RELIANCE_SMOKE is None!"
        
        m1 = c1.metrics
        print(f"[CHECK 1] RELIANCE_SMOKE Unique Broker Count: {m1.unique_broker_count} (Expected: 3)")
        assert m1.unique_broker_count == 3, f"Expected 3 brokers, got {m1.unique_broker_count}"

        print(f"[CHECK 2] Multiple Source Non-Inflation: Motilal rec has {len(c1.contributors[0].sources)} sources, total broker count remains 3.")
        assert len(c1.contributors) == 3, f"Expected 3 contributors, got {len(c1.contributors)}"

        print(f"[CHECK 3] Target Prices: Min={m1.min_target}, Max={m1.max_target}, Avg={m1.avg_target}, Median={m1.median_target}")
        assert m1.min_target == 2900.0
        assert m1.max_target == 3200.0
        assert m1.median_target == 3000.0
        assert m1.avg_target == 3033.33

        print(f"[CHECK 4] CMP Upside: Avg Upside={m1.avg_target_upside_pct}%, Median Upside={m1.median_target_upside_pct}%")
        assert m1.avg_target_upside_pct == 21.33
        assert m1.median_target_upside_pct == 20.0

        # 8. Test Lifecycle vs Freshness on TCS_SMOKE
        c2 = ConsensusService.calculate_stock_consensus(db, stock2.stock_id)
        assert c2 is not None
        m2 = c2.metrics
        tcs_contrib = c2.contributors[0]
        
        print(f"[CHECK 5] TCS_SMOKE Lifecycle vs Freshness: Age={tcs_contrib.age_days}d, Freshness={tcs_contrib.freshness_category}, Lifecycle={tcs_contrib.lifecycle_status}")
        assert tcs_contrib.age_days >= 70
        assert tcs_contrib.freshness_category == 'AGED'
        assert tcs_contrib.lifecycle_status == 'CURRENT' # Lifecycle remains CURRENT despite >60d age!

        # 9. Test Candidate API Universe
        candidates = ConsensusService.get_candidate_universe(db, min_brokers=1)
        print(f"[CHECK 6] Candidate Universe returned {candidates.total} candidates.")
        assert candidates.total == 1

        print("==================================================")
        print("STAGE 5 SMOKE WORKFLOW SUCCESSFUL — ALL CHECKS PASSED")
        print("==================================================")

    finally:
        db.close()
        engine.dispose()
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass

if __name__ == "__main__":
    run_stage5_smoke_test()
