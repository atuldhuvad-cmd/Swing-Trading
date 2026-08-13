from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from app.database import get_db
from app.schemas.consensus import StockConsensusOut, CandidateListResponse
from app.services.consensus_service import ConsensusService

router = APIRouter(prefix="/api/consensus", tags=["consensus"])

@router.get("/candidates", response_model=CandidateListResponse)
def get_candidate_universe(
    min_brokers: int = Query(1, ge=0),
    min_upside: Optional[float] = Query(None),
    min_bullish_pct: Optional[float] = Query(None),
    max_age_days: Optional[int] = Query(None),
    verification_status: str = Query('ALL'),
    eligible_ratings: Optional[List[str]] = Query(None),
    sort_by: str = Query('broker_count'),
    sort_order: str = Query('desc'),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    return ConsensusService.get_candidate_universe(
        db=db,
        min_brokers=min_brokers,
        min_upside=min_upside,
        min_bullish_pct=min_bullish_pct,
        max_age_days=max_age_days,
        verification_status=verification_status,
        eligible_ratings=eligible_ratings,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit
    )

@router.get("/stocks/{stock_id}", response_model=StockConsensusOut)
def get_stock_consensus(
    stock_id: int,
    verification_status: str = Query('ALL'),
    eligible_ratings: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    consensus = ConsensusService.calculate_stock_consensus(
        db=db,
        stock_id=stock_id,
        verification_status=verification_status,
        eligible_ratings=eligible_ratings
    )
    if not consensus:
        raise HTTPException(status_code=404, detail="Stock not found")
    return consensus

@router.get("/source-readiness")
def get_source_readiness(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Stage 6 - Source Collection Readiness Assessment.

    Derives readiness from existing broker_master + recommendation_stream tables.
    No new DB tables. Covers the five pilot Indian providers.

    Categories:
      PUBLIC_STABLE    - Public, stable, suitable for future scheduled fetching
      PUBLIC_UNSTABLE  - Publicly accessible but inconsistent structure
      LOGIN_REQUIRED   - Requires brokerage login/session
      DOCUMENT_MANUAL  - Best handled via manually downloaded PDF/XLSX/CSV
      SECONDARY_ONLY   - No reliable direct source; reputable secondary attribution exists
      UNSUITABLE       - No reliable compliant collection path identified
    """
    from app.models import BrokerMaster, RecommendationStream, BrokerRecommendation

    PILOT_PROVIDERS = [
        "Angel One",
        "HDFC Securities",
        "Motilal Oswal",
        "ICICI Securities",
        "Mirae Asset Sharekhan",
    ]

    # Source readiness classification per Stage 6 STEP 9
    READINESS_ASSESSMENTS: Dict[str, Dict[str, str]] = {
        "Angel One": {
            "category": "LOGIN_REQUIRED",
            "reasoning": (
                "Angel One research requires brokerage account login via SmartAPI "
                "or the Angel One mobile app. No public unauthenticated research feed "
                "is available. Manual PDF/document ingestion is the recommended path."
            ),
            "collection_method": "DOCUMENT_MANUAL",
        },
        "HDFC Securities": {
            "category": "LOGIN_REQUIRED",
            "reasoning": (
                "HDFC Securities research reports are accessible only to account holders "
                "via HDFC Sky or the brokerage portal. No unauthenticated public research "
                "endpoint has been identified. Manual document ingestion is recommended."
            ),
            "collection_method": "DOCUMENT_MANUAL",
        },
        "Motilal Oswal": {
            "category": "PUBLIC_UNSTABLE",
            "reasoning": (
                "Motilal Oswal publishes research summaries on their public website "
                "(motilaloswal.com). However, the structure changes frequently and "
                "is inconsistent across pages. Individual stock recommendations may be "
                "partially accessible. Manual verification is required before any "
                "automated fetching is attempted."
            ),
            "collection_method": "DOCUMENT_MANUAL",
        },
        "ICICI Securities": {
            "category": "LOGIN_REQUIRED",
            "reasoning": (
                "ICICIdirect research requires brokerage account authentication. "
                "The ICICIdirect.com portal restricts full research access to account "
                "holders. No public unauthenticated research feed is available."
            ),
            "collection_method": "DOCUMENT_MANUAL",
        },
        "Mirae Asset Sharekhan": {
            "category": "SECONDARY_ONLY",
            "reasoning": (
                "Sharekhan/Mirae Asset Sharekhan research is primarily distributed to "
                "clients. Some recommendations are cited by reputable financial publications "
                "(Moneycontrol, ET Markets, Livemint) which serve as VERIFIED_SECONDARY "
                "sources. No direct public primary research endpoint has been identified."
            ),
            "collection_method": "SECONDARY_PUBLICATION",
        },
    }

    result = []
    for canonical_name in PILOT_PROVIDERS:
        broker = db.query(BrokerMaster).filter(
            BrokerMaster.canonical_name == canonical_name
        ).first()

        if not broker:
            result.append({
                "canonical_name": canonical_name,
                "display_name": canonical_name,
                "broker_id": None,
                "active": False,
                "enabled_for_new_ingestion": False,
                "streams": [],
                "recommendation_count": 0,
                "readiness_category": "UNSUITABLE",
                "collection_method": "NONE",
                "reasoning": "Broker not found in broker_master.",
                "notes": None,
            })
            continue

        streams = db.query(RecommendationStream).filter(
            RecommendationStream.broker_id == broker.broker_id,
            RecommendationStream.enabled == True
        ).all()

        rec_count = db.query(BrokerRecommendation).filter(
            BrokerRecommendation.broker_id == broker.broker_id
        ).count()

        assessment = READINESS_ASSESSMENTS.get(canonical_name, {
            "category": "UNSUITABLE",
            "reasoning": "No assessment available.",
            "collection_method": "UNKNOWN",
        })

        result.append({
            "canonical_name": broker.canonical_name,
            "display_name": broker.display_name,
            "broker_id": broker.broker_id,
            "active": bool(broker.active_status),
            "enabled_for_new_ingestion": bool(broker.enabled_for_new_ingestion),
            "streams": [
                {
                    "stream_id": s.stream_id,
                    "stream_name": s.stream_name,
                    "stream_type": s.stream_type,
                    "frequency": s.frequency,
                    "source_url": s.source_url,
                    "last_checked": s.last_checked.isoformat() if s.last_checked else None,
                    "last_successful_update": s.last_successful_update.isoformat() if s.last_successful_update else None,
                }
                for s in streams
            ],
            "recommendation_count": rec_count,
            "readiness_category": assessment["category"],
            "collection_method": assessment["collection_method"],
            "reasoning": assessment["reasoning"],
            "notes": broker.notes,
        })

    return result
