import pytest
import pandas as pd
from datetime import date, timedelta
from decimal import Decimal
from app.services.technical_service import TechnicalService

class DummyStock:
    def __init__(self, symbol):
        self.nse_symbol = symbol

class DummyOriginal:
    def __init__(self, symbol):
        self.stock = DummyStock(symbol)

def generate_synthetic_ohlcv(sessions: int, start_price: float = 100.0, trend: str = 'flat') -> list:
    data = []
    current_date = date(2025, 1, 1)
    
    for i in range(sessions):
        if trend == 'rising':
            current_price = start_price + i
        elif trend == 'falling':
            current_price = start_price - i
        else:
            current_price = start_price
            
        data.append({
            'trading_date': current_date,
            'series': 'EQ',
            'open': Decimal(str(current_price - 0.5)),
            'high': Decimal(str(current_price + 1.0)),
            'low': Decimal(str(current_price - 1.0)),
            'close': Decimal(str(current_price)),
            'volume': Decimal('1000'),
            'adjustment_status': 'NO_ADJUSTMENT',
            'original': DummyOriginal('TEST')
        })
        current_date += timedelta(days=1)
        
    return data

def test_insufficient_data():
    # 19 sessions -> SMA20 unavailable
    data = generate_synthetic_ohlcv(19)
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['SMA20'] is None
    
    # 49 sessions -> SMA50 unavailable
    data = generate_synthetic_ohlcv(49)
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['SMA20'] is not None
    assert res['SMA50'] is None
    
    # 199 sessions -> SMA200 unavailable
    data = generate_synthetic_ohlcv(199)
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['SMA50'] is not None
    assert res['SMA200'] is None

def test_sma_calculations():
    # 200 sessions flat
    data = generate_synthetic_ohlcv(200, start_price=100.0, trend='flat')
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['SMA20'] == Decimal('100.00')
    assert res['SMA50'] == Decimal('100.00')
    assert res['SMA200'] == Decimal('100.00')

def test_rsi_rising_falling():
    data_rising = generate_synthetic_ohlcv(50, start_price=100.0, trend='rising')
    res = TechnicalService.calculate_technical_evidence(data_rising)
    assert res['RSI14'] > Decimal('50.00')
    
    data_falling = generate_synthetic_ohlcv(50, start_price=100.0, trend='falling')
    res = TechnicalService.calculate_technical_evidence(data_falling)
    assert res['RSI14'] < Decimal('50.00')

def test_macd():
    data = generate_synthetic_ohlcv(50, trend='rising')
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['EMA12'] is not None
    assert res['EMA26'] is not None
    assert res['MACD'] is not None
    assert res['MACD_signal'] is not None
    assert res['MACD_hist'] is not None

def test_atr():
    data = generate_synthetic_ohlcv(20, start_price=100.0)
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['ATR14'] is not None
    assert res['ATR_percent'] is not None

def test_roc20():
    # current close is 120, close 20 sessions ago is 100
    data = generate_synthetic_ohlcv(21, start_price=100.0, trend='rising')
    # Prices: 100, 101, ..., 120
    res = TechnicalService.calculate_technical_evidence(data)
    # ROC20 = (120 - 100) / 100 * 100 = 20%
    assert res['ROC20'] == Decimal('20.00')

def test_breakout20():
    data = generate_synthetic_ohlcv(21, start_price=100.0, trend='rising')
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['Breakout20_status'] == 'NEGATIVE' # high of previous is 119+1 = 120. current close is 120. 120 > 120 is False.
    
    # Make a breakout by having flat trend then sudden spike
    data2 = generate_synthetic_ohlcv(21, start_price=100.0, trend='flat')
    data2[-1]['close'] = Decimal('150.0') # Spike
    res2 = TechnicalService.calculate_technical_evidence(data2)
    assert res2['Breakout20_status'] == 'POSITIVE'

def test_sma_golden_rising():
    data = generate_synthetic_ohlcv(20, start_price=100.0, trend='rising')
    res = TechnicalService.calculate_technical_evidence(data)
    # closes 100..119; SMA20 = (100+119)*20/2 / 20 = 109.5
    assert res['SMA20'] == Decimal('109.50')


def test_support_resistance20():
    data = generate_synthetic_ohlcv(21, start_price=100.0, trend='flat')
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['Support20'] == Decimal('99.00')
    assert res['Resistance20'] == Decimal('101.00')


def test_liquidity20():
    data = generate_synthetic_ohlcv(20, start_price=100.0, trend='flat')
    res = TechnicalService.calculate_technical_evidence(data)
    assert res['Liquidity20'] == Decimal('100000.00')
