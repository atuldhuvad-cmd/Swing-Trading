import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from app.models import FundamentalSnapshot, FundamentalMetric, StockMaster, SourceTypeMaster, SourceReference
from app.services.fundamental_service import FundamentalService

def test_ordinary_company_snapshot(db_session):
    stock = StockMaster(nse_symbol='ORD1', company_name='Ord Co')
    db_session.add(stock)
    db_session.commit()
    
    metrics = {
        'revenue': {'value': 1000.5, 'status': 'KNOWN'},
        'ebitda': {'value': 200.0, 'status': 'KNOWN'},
        'missing_metric': {'value': None, 'status': 'UNKNOWN'},
        'irrelevant_metric': {'value': None, 'status': 'NOT_APPLICABLE'},
        'unsupported': {'value': None, 'status': 'UNSUPPORTED'}
    }
    
    snapshot = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q1 FY24',
        period_type='QUARTERLY',
        entity_type='ORDINARY',
        metrics=metrics
    )
    
    db_session.commit()
    
    assert snapshot.snapshot_id is not None
    evidence = FundamentalService.get_metric_evidence(db_session, snapshot.snapshot_id)
    assert evidence['revenue']['status'] == 'KNOWN'
    assert evidence['revenue']['value'] == Decimal('1000.5')
    assert evidence['missing_metric']['status'] == 'UNKNOWN'
    assert evidence['irrelevant_metric']['status'] == 'NOT_APPLICABLE'
    assert evidence['unsupported']['status'] == 'UNSUPPORTED'

def test_staleness(db_session):
    stock = StockMaster(nse_symbol='STALE1', company_name='Stale Co')
    db_session.add(stock)
    db_session.commit()
    
    ref_date = date(2023, 5, 1)
    old_date = ref_date - timedelta(days=100)
    
    metrics = {
        'revenue': {'value': 1000.5, 'status': 'KNOWN'}
    }
    
    snapshot = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=old_date,
        financial_period='Q1 FY23',
        period_type='QUARTERLY',
        metrics=metrics,
        reference_date=ref_date
    )
    
    db_session.commit()
    evidence = FundamentalService.get_metric_evidence(db_session, snapshot.snapshot_id)
    assert evidence['revenue']['status'] == 'STALE'
    assert evidence['revenue']['value'] is None

def test_revision_preservation(db_session):
    stock = StockMaster(nse_symbol='REV1', company_name='Rev Co')
    db_session.add(stock)
    db_session.commit()
    
    metrics_v1 = {'revenue': {'value': 100.0, 'status': 'KNOWN'}}
    snap_v1 = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q1 FY24',
        period_type='QUARTERLY',
        metrics=metrics_v1
    )
    
    metrics_v2 = {'revenue': {'value': 120.0, 'status': 'KNOWN'}}
    snap_v2 = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q1 FY24',
        period_type='QUARTERLY',
        metrics=metrics_v2
    )
    
    db_session.commit()
    
    assert snap_v1.is_superseded is True
    assert snap_v2.is_superseded is False
    assert snap_v1.superseded_by_id == snap_v2.snapshot_id
    assert snap_v2.version == 2
    
    ev_v1 = FundamentalService.get_metric_evidence(db_session, snap_v1.snapshot_id)
    ev_v2 = FundamentalService.get_metric_evidence(db_session, snap_v2.snapshot_id)
    
    assert ev_v1['revenue']['value'] == Decimal('100.0')
    assert ev_v2['revenue']['value'] == Decimal('120.0')

def test_bank_handling(db_session):
    stock = StockMaster(nse_symbol='BANK1', company_name='Bank Co')
    db_session.add(stock)
    db_session.commit()
    
    metrics = {
        'nim': {'value': 3.5, 'status': 'KNOWN'},
        'gnpa': {'value': 1.2, 'status': 'KNOWN'},
        'inventory_turnover': {'value': None, 'status': 'NOT_APPLICABLE'}
    }
    
    snapshot = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q2 FY24',
        period_type='QUARTERLY',
        entity_type='BANK',
        metrics=metrics
    )
    
    db_session.commit()
    
    assert snapshot.entity_type == 'BANK'
    ev = FundamentalService.get_metric_evidence(db_session, snapshot.snapshot_id)
    assert ev['nim']['status'] == 'KNOWN'
    assert ev['inventory_turnover']['status'] == 'NOT_APPLICABLE'

def test_nbfc_handling(db_session):
    stock = StockMaster(nse_symbol='NBFC1', company_name='NBFC Co')
    db_session.add(stock)
    db_session.commit()
    
    metrics = {
        'nim': {'value': 4.1, 'status': 'KNOWN'},
        'capital_adequacy': {'value': 15.5, 'status': 'KNOWN'},
    }
    
    snapshot = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q2 FY24',
        period_type='QUARTERLY',
        entity_type='NBFC',
        metrics=metrics
    )
    
    db_session.commit()
    
    assert snapshot.entity_type == 'NBFC'
    ev = FundamentalService.get_metric_evidence(db_session, snapshot.snapshot_id)
    assert ev['nim']['status'] == 'KNOWN'
    assert ev['capital_adequacy']['value'] == Decimal('15.5')

def test_source_provenance(db_session):
    stock = StockMaster(nse_symbol='PROV1', company_name='Prov Co')
    db_session.add(stock)
    
    st = SourceTypeMaster(type_name='API', description='API')
    db_session.add(st)
    db_session.flush()
    
    ref = SourceReference(source_type_id=st.source_type_id, publication_name='Test Data')
    db_session.add(ref)
    db_session.commit()
    
    snapshot = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q1 FY24',
        period_type='QUARTERLY',
        source_reference_id=ref.source_reference_id
    )
    
    db_session.commit()
    
    assert snapshot.source_reference_id == ref.source_reference_id
    
def test_invalid_source_provenance(db_session):
    stock = StockMaster(nse_symbol='INVPROV1', company_name='Inv Prov Co')
    db_session.add(stock)
    db_session.commit()
    
    with pytest.raises(IntegrityError):
        snapshot = FundamentalService.create_snapshot(
            db=db_session,
            stock_id=stock.stock_id,
            as_of_date=datetime.utcnow().date(),
            financial_period='Q1 FY24',
            period_type='QUARTERLY',
            source_reference_id=9999
        )
        db_session.commit()

def test_get_latest_and_historical(db_session):
    stock = StockMaster(nse_symbol='HIST1', company_name='Hist Co')
    db_session.add(stock)
    db_session.commit()
    
    FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=date(2023, 3, 31),
        financial_period='FY23',
        period_type='ANNUAL'
    )
    
    s2 = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=date(2024, 3, 31),
        financial_period='FY24',
        period_type='ANNUAL'
    )
    db_session.commit()
    
    latest = FundamentalService.get_latest_snapshot(db_session, stock.stock_id)
    assert latest.snapshot_id == s2.snapshot_id
    
    hist = FundamentalService.get_historical_snapshots(db_session, stock.stock_id)
    assert len(hist) == 2
    assert hist[0].as_of_date == date(2024, 3, 31)

def test_no_silent_zero_and_status_consistency(db_session):
    stock = StockMaster(nse_symbol='ZERO1', company_name='Zero Co')
    db_session.add(stock)
    db_session.commit()
    
    metrics = {
        'revenue': {'value': 0.0, 'status': 'KNOWN'},
        'ebitda': {'value': 500, 'status': 'UNKNOWN'},
        'pat': {'value': 500, 'status': 'NOT_APPLICABLE'}
    }
    
    snapshot = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q1',
        period_type='QUARTERLY',
        metrics=metrics
    )
    db_session.commit()
    
    ev = FundamentalService.get_metric_evidence(db_session, snapshot.snapshot_id)
    assert ev['revenue']['value'] == Decimal('0.0')
    assert ev['ebitda']['value'] is None
    assert ev['ebitda']['status'] == 'UNKNOWN'
    assert ev['pat']['value'] is None
    assert ev['pat']['status'] == 'NOT_APPLICABLE'

def test_entity_type_validation(db_session):
    stock = StockMaster(nse_symbol='ENT1', company_name='Entity Co')
    db_session.add(stock)
    db_session.commit()
    
    with pytest.raises(ValueError, match="Invalid entity_type"):
        FundamentalService.create_snapshot(
            db=db_session,
            stock_id=stock.stock_id,
            as_of_date=datetime.utcnow().date(),
            financial_period='Q1',
            period_type='QUARTERLY',
            entity_type='INVALID_TYPE'
        )

def test_status_validation(db_session):
    stock = StockMaster(nse_symbol='STAT1', company_name='Status Co')
    db_session.add(stock)
    db_session.commit()
    
    metrics = {
        'revenue': {'value': 100, 'status': 'INVALID_STATUS'}
    }
    
    with pytest.raises(ValueError, match="Invalid status"):
        FundamentalService.create_snapshot(
            db=db_session,
            stock_id=stock.stock_id,
            as_of_date=datetime.utcnow().date(),
            financial_period='Q1',
            period_type='QUARTERLY',
            metrics=metrics
        )

def test_revision_isolation(db_session):
    stock = StockMaster(nse_symbol='ISO1', company_name='Iso Co')
    stock2 = StockMaster(nse_symbol='ISO2', company_name='Iso Co 2')
    db_session.add_all([stock, stock2])
    db_session.commit()
    
    s1 = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q1',
        period_type='QUARTERLY'
    )
    
    s2 = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q2',
        period_type='QUARTERLY'
    )
    
    s3 = FundamentalService.create_snapshot(
        db=db_session,
        stock_id=stock2.stock_id,
        as_of_date=datetime.utcnow().date(),
        financial_period='Q1',
        period_type='QUARTERLY'
    )
    
    db_session.commit()
    
    # Check that they don't supersede each other
    assert s1.is_superseded is False
    assert s2.is_superseded is False
    assert s3.is_superseded is False
    assert s1.version == 1
    assert s2.version == 1
    assert s3.version == 1
