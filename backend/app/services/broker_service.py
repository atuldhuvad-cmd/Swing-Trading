from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.models import BrokerMaster, BrokerAlias, BrokerRelationship
from datetime import datetime

class BrokerService:
    @staticmethod
    def resolve_broker_identity(db: Session, search_term: str, recommendation_date: datetime = None):
        """
        Resolves a search term to a broker identity considering canonical name, 
        normalized name, display name, and aliases.
        Also considers temporal validity if a recommendation date is provided.
        Returns a list of potential matches. If multiple are returned, it's ambiguous.
        """
        normalized_term = search_term.strip().lower()
        
        # 1. Exact match canonical, normalized or display
        query = db.query(BrokerMaster).outerjoin(BrokerAlias).filter(
            or_(
                func.lower(BrokerMaster.canonical_name) == normalized_term,
                func.lower(BrokerMaster.normalized_name) == normalized_term,
                func.lower(BrokerMaster.display_name) == normalized_term,
                func.lower(BrokerAlias.alias_name) == normalized_term
            )
        ).distinct()

        if recommendation_date:
            # Filter by temporal validity
            query = query.filter(
                or_(
                    BrokerMaster.valid_from == None,
                    BrokerMaster.valid_from <= recommendation_date
                ),
                or_(
                    BrokerMaster.valid_until == None,
                    BrokerMaster.valid_until >= recommendation_date
                )
            )

        return query.all()

    @staticmethod
    def get_broker_lineage(db: Session, broker_id: int):
        """
        Retrieves the predecessors and successors for a given broker.
        """
        predecessors = db.query(BrokerRelationship).filter(BrokerRelationship.successor_id == broker_id).all()
        successors = db.query(BrokerRelationship).filter(BrokerRelationship.predecessor_id == broker_id).all()
        
        return {
            "predecessors": predecessors,
            "successors": successors
        }
