import pytest
from datetime import date, timedelta
from decimal import Decimal
from app.models import CorporateAction, DailyOhlcv
from app.services.corporate_action_service import CorporateActionService

def test_split_bonus_adjustments():
    # Synthetic data for logic testing without DB
    actions = [
        CorporateAction(action_type='SPLIT', ex_date=date(2025, 1, 10), ratio_numerator=Decimal('2'), ratio_denominator=Decimal('1')),
        CorporateAction(action_type='BONUS', ex_date=date(2025, 2, 10), ratio_numerator=Decimal('1'), ratio_denominator=Decimal('1')),
    ]
    
    # 2:1 split on Jan 10
    # Before Jan 10: price * 1/2, volume * 2
    # 1:1 bonus on Feb 10
    # Before Feb 10: price * 1/2, volume * 2
    # Combined before Jan 10: price * 1/4, volume * 4
    
    # Test date: Jan 5 (before both)
    f1 = CorporateActionService.get_adjustment_factors(actions, date(2025, 1, 5))
    assert f1['price_factor'] == Decimal('0.25')
    assert f1['volume_factor'] == Decimal('4.0')
    
    # Test date: Jan 15 (after split, before bonus)
    f2 = CorporateActionService.get_adjustment_factors(actions, date(2025, 1, 15))
    assert f2['price_factor'] == Decimal('0.5')
    assert f2['volume_factor'] == Decimal('2.0')
    
    # Test date: Feb 15 (after both)
    f3 = CorporateActionService.get_adjustment_factors(actions, date(2025, 2, 15))
    assert f3['price_factor'] == Decimal('1.0')
    assert f3['volume_factor'] == Decimal('1.0')

def test_invalid_ratio():
    with pytest.raises(ValueError):
        CorporateActionService.store_action(None, 1, 'SPLIT', date.today(), Decimal('0'), Decimal('1'))

def test_dividend_rights_other_no_adjust():
    actions = [
        CorporateAction(action_type='DIVIDEND', ex_date=date(2025, 1, 10), cash_amount=Decimal('5.0')),
        CorporateAction(action_type='RIGHTS', ex_date=date(2025, 2, 10)),
        CorporateAction(action_type='OTHER', ex_date=date(2025, 3, 10))
    ]
    f1 = CorporateActionService.get_adjustment_factors(actions, date(2025, 1, 1))
    assert f1['price_factor'] == Decimal('1.0')
    assert f1['volume_factor'] == Decimal('1.0')
