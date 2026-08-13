from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class StockMaster(Base):
    __tablename__ = 'stock_master'
    stock_id = Column(Integer, primary_key=True, autoincrement=True)
    nse_symbol = Column(String(50), unique=True, nullable=False, index=True)
    bse_symbol = Column(String(50), nullable=True)
    company_name = Column(String(255), nullable=False)
    isin = Column(String(12), unique=True, nullable=True)
    sector = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)
    market_cap_category = Column(String(50), nullable=True)
    listing_status = Column(String(50), nullable=False, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BrokerMaster(Base):
    __tablename__ = 'broker_master'
    broker_id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_name = Column(String(255), unique=True, nullable=False)
    normalized_name = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    website = Column(String(255), nullable=True)
    active_status = Column(Boolean, default=True)
    credibility_status = Column(String(50), nullable=True)
    is_historical_only = Column(Boolean, default=False)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    enabled_for_new_ingestion = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BrokerAlias(Base):
    __tablename__ = 'broker_alias'
    alias_id = Column(Integer, primary_key=True, autoincrement=True)
    broker_id = Column(Integer, ForeignKey('broker_master.broker_id'), nullable=False)
    alias_name = Column(String(255), nullable=False, unique=True)
    
    broker = relationship("BrokerMaster")

class BrokerRelationship(Base):
    __tablename__ = 'broker_relationship'
    relationship_id = Column(Integer, primary_key=True, autoincrement=True)
    predecessor_id = Column(Integer, ForeignKey('broker_master.broker_id'), nullable=False)
    successor_id = Column(Integer, ForeignKey('broker_master.broker_id'), nullable=False)
    relationship_type = Column(String(50), nullable=False)
    effective_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    
    predecessor = relationship("BrokerMaster", foreign_keys=[predecessor_id])
    successor = relationship("BrokerMaster", foreign_keys=[successor_id])

class RecommendationStream(Base):
    __tablename__ = 'recommendation_stream'
    stream_id = Column(Integer, primary_key=True, autoincrement=True)
    broker_id = Column(Integer, ForeignKey('broker_master.broker_id'), nullable=False)
    stream_name = Column(String(255), nullable=False)
    stream_type = Column(String(100), nullable=False)
    frequency = Column(String(50), nullable=False)
    source_url = Column(String(500), nullable=True)
    enabled = Column(Boolean, default=True)
    last_checked = Column(DateTime, nullable=True)
    next_check_due = Column(DateTime, nullable=True)
    last_successful_update = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(frequency.in_(['DAILY', 'WEEKLY', 'MONTHLY', 'IRREGULAR', 'MANUAL']), name='check_frequency_allowed'),
    )

class BrokerRecommendation(Base):
    __tablename__ = 'broker_recommendation'
    recommendation_id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey('stock_master.stock_id'), nullable=False)
    broker_id = Column(Integer, ForeignKey('broker_master.broker_id'), nullable=False)
    stream_id = Column(Integer, ForeignKey('recommendation_stream.stream_id'), nullable=True)
    recommendation_date = Column(DateTime, nullable=False)
    original_rating = Column(String(100), nullable=False)
    normalized_rating = Column(String(100), nullable=False)
    recommended_price = Column(Float, nullable=True)
    entry_price_low = Column(Float, nullable=True)
    entry_price_high = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    time_horizon_text = Column(String(100), nullable=True)
    normalized_horizon = Column(String(50), nullable=True)
    expected_end_date = Column(DateTime, nullable=True)
    analyst_name = Column(String(255), nullable=True)
    currency = Column(String(10), default='INR')
    lifecycle_status = Column(String(50), nullable=False, default='CURRENT')
    superseded_by_id = Column(Integer, ForeignKey('broker_recommendation.recommendation_id'), nullable=True)
    superseded_timestamp = Column(DateTime, nullable=True)
    fingerprint = Column(String(255), unique=True, nullable=True)
    import_batch_id = Column(Integer, ForeignKey('import_batch.batch_id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(target_price >= 0, name='check_target_positive'),
        CheckConstraint(stop_loss >= 0, name='check_stop_loss_positive'),
        CheckConstraint(lifecycle_status.in_(['CURRENT', 'SUPERSEDED', 'WITHDRAWN', 'HORIZON_EXPIRED', 'HISTORICAL']), name='check_lifecycle_status'),
    )

class RecommendationStatusHistory(Base):
    __tablename__ = 'recommendation_status_history'
    history_id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(Integer, ForeignKey('broker_recommendation.recommendation_id'), nullable=False)
    status = Column(String(50), nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

class SourceTypeMaster(Base):
    __tablename__ = 'source_type_master'
    source_type_id = Column(Integer, primary_key=True, autoincrement=True)
    type_name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)

class SourceReference(Base):
    __tablename__ = 'source_reference'
    source_reference_id = Column(Integer, primary_key=True, autoincrement=True)
    source_type_id = Column(Integer, ForeignKey('source_type_master.source_type_id'), nullable=False)
    publication_name = Column(String(255), nullable=True)
    url = Column(String(1000), nullable=True)
    source_date = Column(DateTime, nullable=True)
    collection_timestamp = Column(DateTime, default=datetime.utcnow)
    original_text = Column(Text, nullable=True)
    verification_status = Column(String(50), nullable=False, default='PROVISIONAL')
    reliability_score = Column(Float, nullable=True)
    verified_by = Column(String(255), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    verification_notes = Column(Text, nullable=True)
    import_batch_id = Column(Integer, ForeignKey('import_batch.batch_id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(verification_status.in_(['VERIFIED_PRIMARY', 'VERIFIED_SECONDARY', 'PROVISIONAL', 'REJECTED']), name='check_verification_status'),
    )

class RecommendationSource(Base):
    __tablename__ = 'recommendation_source'
    id = Column(Integer, primary_key=True, autoincrement=True)
    recommendation_id = Column(Integer, ForeignKey('broker_recommendation.recommendation_id'), nullable=False)
    source_reference_id = Column(Integer, ForeignKey('source_reference.source_reference_id'), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('recommendation_id', 'source_reference_id', name='uq_rec_source'),
    )

class RatingNormalization(Base):
    __tablename__ = 'rating_normalization'
    id = Column(Integer, primary_key=True, autoincrement=True)
    original_rating = Column(String(100), unique=True, nullable=False)
    normalized_rating = Column(String(100), nullable=False)

class StockPrice(Base):
    __tablename__ = 'stock_price'
    stock_id = Column(Integer, ForeignKey('stock_master.stock_id'), primary_key=True)
    last_price = Column(Float, nullable=False)
    previous_price = Column(Float, nullable=True)
    price_change = Column(Float, nullable=True)
    percentage_change = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PriceObservation(Base):
    __tablename__ = 'price_observation'
    observation_id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey('stock_master.stock_id'), nullable=False)
    observed_price = Column(Float, nullable=False)
    observed_timestamp = Column(DateTime, nullable=False)
    source = Column(String(255), nullable=False)
    source_reference_id = Column(Integer, ForeignKey('source_reference.source_reference_id'), nullable=True)
    notes = Column(Text, nullable=True)
    created_timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(observed_price > 0, name='check_observed_price_positive'),
    )

class ImportBatch(Base):
    __tablename__ = 'import_batch'
    batch_id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=True)
    import_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), nullable=False, default='PENDING')
    total_rows = Column(Integer, default=0)
    accepted_rows = Column(Integer, default=0)
    rejected_rows = Column(Integer, default=0)
    duplicate_rows = Column(Integer, default=0)
    review_rows = Column(Integer, default=0)

class ImportBatchDetail(Base):
    __tablename__ = 'import_batch_detail'
    detail_id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey('import_batch.batch_id'), nullable=False)
    row_number = Column(Integer, nullable=True)
    status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)
    raw_data = Column(Text, nullable=True)
    mapped_data = Column(Text, nullable=True)
    action = Column(String(50), nullable=True)
    recommendation_id = Column(Integer, ForeignKey('broker_recommendation.recommendation_id'), nullable=True)
    source_reference_id = Column(Integer, ForeignKey('source_reference.source_reference_id'), nullable=True)

class ReviewQueue(Base):
    __tablename__ = 'review_queue'
    review_id = Column(Integer, primary_key=True, autoincrement=True)
    item_type = Column(String(100), nullable=False)
    item_reference_id = Column(Integer, nullable=True)
    reason = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default='PENDING')
    import_batch_id = Column(Integer, ForeignKey('import_batch.batch_id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class SystemSetting(Base):
    __tablename__ = 'system_setting'
    setting_key = Column(String(100), primary_key=True)
    setting_value = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

class DataImportBatch(Base):
    __tablename__ = 'data_import_batch'
    import_batch_id = Column(Integer, primary_key=True, autoincrement=True)
    import_type = Column(String(50), nullable=False)
    source_name = Column(String(100), nullable=False)
    source_reference = Column(String(255), nullable=True)
    original_filename = Column(String(255), nullable=True)
    file_sha256 = Column(String(64), nullable=True)
    retrieval_date = Column(DateTime, nullable=True)
    trading_date_from = Column(DateTime, nullable=True)
    trading_date_to = Column(DateTime, nullable=True)
    rows_received = Column(Integer, default=0)
    rows_accepted = Column(Integer, default=0)
    rows_rejected = Column(Integer, default=0)
    status = Column(String(50), nullable=False, default='PENDING')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DailyOhlcv(Base):
    __tablename__ = 'daily_ohlcv'
    daily_ohlcv_id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey('stock_master.stock_id'), nullable=False)
    trading_date = Column(DateTime, nullable=False)
    series = Column(String(10), nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    source_name = Column(String(100), nullable=False)
    import_batch_id = Column(Integer, ForeignKey('data_import_batch.import_batch_id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('stock_id', 'trading_date', 'series', name='uq_stock_date_series'),
    )
