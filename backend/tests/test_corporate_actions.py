import pytest
from datetime import date, timedelta
from decimal import Decimal
from app.models import CorporateAction, DailyOhlcv
from app.services.corporate_action_service import CorporateActionService

def test_split_bonus_adjustments():
    # Synthetic data for logic testing without DB
    actions = [
        CorporateAction(action_type='SPLIT', ex_date=date(2025, 1, 10), ratio_numerator=Decimal('2'), ratio_denominator=Decimal('1')),
        CorporateAction(action_type='SPLIT', ex_date=date(2025, 1, 20), ratio_numerator=Decimal('1'), ratio_denominator=Decimal('2')),
        CorporateAction(action_type='BONUS', ex_date=date(2025, 2, 10), ratio_numerator=Decimal('1'), ratio_denominator=Decimal('1')),
        CorporateAction(action_type='BONUS', ex_date=date(2025, 2, 20), ratio_numerator=Decimal('1'), ratio_denominator=Decimal('2')),
    ]
    
    # Check ex-date boundary
    f_before_all = CorporateActionService.get_adjustment_factors(actions, date(2025, 1, 1))
    assert f_before_all['status'] == 'ADJUSTED'
    
    # 2:1 Split -> pf = 0.5, vf = 2
    # 1:2 Reverse Split -> pf = 2, vf = 0.5
    # 1:1 Bonus -> pf = 0.5, vf = 2
    # 1:2 Bonus (1 for every 2) -> pf = 2/(2+1) = 2/3, vf = 3/2
    # Total before Jan 10: 0.5 * 2 * 0.5 * (2/3) = 1/3 price factor, 2 * 0.5 * 2 * 1.5 = 3.0 volume factor
    
    assert round(f_before_all['price_factor'], 6) == round(Decimal(1) / Decimal(3), 6)
    assert round(f_before_all['volume_factor'], 6) == Decimal('3.0')
    
def test_invalid_ratio():
    with pytest.raises(ValueError):
        CorporateActionService.store_action(None, 1, 'SPLIT', date.today(), Decimal('0'), Decimal('1'))
    with pytest.raises(ValueError):
        CorporateActionService.store_action(None, 1, 'SPLIT', date.today(), Decimal('1'), Decimal('0'))
    with pytest.raises(ValueError):
        CorporateActionService.store_action(None, 1, 'SPLIT', date.today(), Decimal('-1'), Decimal('1'))
    with pytest.raises(ValueError):
        CorporateActionService.store_action(None, 1, 'BONUS', date.today(), Decimal('1'), Decimal('-1'))

def test_dividend_rights_other_no_adjust():
    actions = [
        CorporateAction(action_type='DIVIDEND', ex_date=date(2025, 1, 10), cash_amount=Decimal('5.0')),
        CorporateAction(action_type='OTHER', ex_date=date(2025, 3, 10))
    ]
    f1 = CorporateActionService.get_adjustment_factors(actions, date(2025, 1, 1))
    assert f1['price_factor'] == Decimal('1.0')
    assert f1['volume_factor'] == Decimal('1.0')
    assert f1['status'] == 'NO_ADJUSTMENT'

    actions.append(CorporateAction(action_type='RIGHTS', ex_date=date(2025, 2, 10)))
    f2 = CorporateActionService.get_adjustment_factors(actions, date(2025, 1, 1))
    assert f2['status'] == 'UNSUPPORTED/UNKNOWN'
