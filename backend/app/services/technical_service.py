from typing import List, Dict, Any, Optional
from decimal import Decimal
import pandas as pd
import numpy as np

class TechnicalService:
    @staticmethod
    def calculate_technical_evidence(adjusted_ohlcv: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not adjusted_ohlcv:
            return {}
            
        df = pd.DataFrame(adjusted_ohlcv)
        if df.empty:
            return {}
            
        # Ensure chronological sorting
        df = df.sort_values(by='trading_date').reset_index(drop=True)
        
        # Convert columns to float for calculation to avoid Decimal overhead in pandas,
        # we will convert back to Decimal at the service boundary.
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['open'] = df['open'].astype(float)
        df['volume'] = df['volume'].astype(float)

        result = {
            'symbol': adjusted_ohlcv[0].get('original').stock.nse_symbol if adjusted_ohlcv[0].get('original') and hasattr(adjusted_ohlcv[0].get('original'), 'stock') else 'UNKNOWN',
            'sessions': len(df),
            'latest_trading_date': df['trading_date'].iloc[-1],
            'latest_close': Decimal(str(round(df['close'].iloc[-1], 2))),
            'SMA20': None,
            'SMA50': None,
            'SMA200': None,
            'RSI14': None,
            'EMA12': None,
            'EMA26': None,
            'MACD': None,
            'MACD_signal': None,
            'MACD_hist': None,
            'ATR14': None,
            'ATR_percent': None,
            'ROC20': None,
            'Breakout20_threshold': None,
            'Breakout20_status': None,
            'Support20': None,
            'Resistance20': None,
            'Liquidity20': None,
            'adjustment_status': adjusted_ohlcv[-1].get('adjustment_status', 'NO_ADJUSTMENT')
        }
        
        n_sessions = len(df)
        
        # SMA20, 50, 200
        if n_sessions >= 20:
            result['SMA20'] = Decimal(str(round(df['close'].rolling(window=20).mean().iloc[-1], 2)))
        if n_sessions >= 50:
            result['SMA50'] = Decimal(str(round(df['close'].rolling(window=50).mean().iloc[-1], 2)))
        if n_sessions >= 200:
            result['SMA200'] = Decimal(str(round(df['close'].rolling(window=200).mean().iloc[-1], 2)))

        # RSI 14 (Wilder Smoothing)
        if n_sessions >= 15:
            delta = df['close'].diff()
            up, down = delta.copy(), delta.copy()
            up[up < 0] = 0
            down[down > 0] = 0
            
            # Initialize with SMA for the first 14 periods, then Wilder's smoothing (alpha=1/14)
            roll_up1 = up.ewm(alpha=1/14, adjust=False).mean()
            roll_down1 = down.abs().ewm(alpha=1/14, adjust=False).mean()
            
            rs = roll_up1 / roll_down1
            rsi = 100.0 - (100.0 / (1.0 + rs))
            result['RSI14'] = Decimal(str(round(rsi.iloc[-1], 2)))

        # MACD (EMA12, EMA26, Signal 9)
        # EMA initialization: standard adjust=False which uses the first value as the seed.
        if n_sessions >= 26:
            ema12 = df['close'].ewm(span=12, adjust=False).mean()
            ema26 = df['close'].ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            result['EMA12'] = Decimal(str(round(ema12.iloc[-1], 2)))
            result['EMA26'] = Decimal(str(round(ema26.iloc[-1], 2)))
            result['MACD'] = Decimal(str(round(macd_line.iloc[-1], 2)))
            
            if n_sessions >= 34: # 26 + 9 - 1
                signal_line = macd_line.ewm(span=9, adjust=False).mean()
                macd_hist = macd_line - signal_line
                result['MACD_signal'] = Decimal(str(round(signal_line.iloc[-1], 2)))
                result['MACD_hist'] = Decimal(str(round(macd_hist.iloc[-1], 2)))

        # ATR14
        if n_sessions >= 15:
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # Wilder's smoothing for ATR
            atr = tr.ewm(alpha=1/14, adjust=False).mean()
            atr14_val = atr.iloc[-1]
            result['ATR14'] = Decimal(str(round(atr14_val, 2)))
            
            if df['close'].iloc[-1] > 0:
                result['ATR_percent'] = Decimal(str(round((atr14_val / df['close'].iloc[-1]) * 100, 2)))

        # ROC20
        if n_sessions >= 21:
            close_now = df['close'].iloc[-1]
            close_20_ago = df['close'].iloc[-21]
            if close_20_ago > 0:
                roc20 = ((close_now - close_20_ago) / close_20_ago) * 100
                result['ROC20'] = Decimal(str(round(roc20, 2)))

        # Breakout20 / Support20 / Resistance20 from prior 20 completed sessions
        if n_sessions >= 21:
            prior_20_highs = df['high'].iloc[-21:-1]
            prior_20_lows = df['low'].iloc[-21:-1]
            threshold = prior_20_highs.max()
            result['Breakout20_threshold'] = Decimal(str(round(threshold, 2)))
            result['Resistance20'] = Decimal(str(round(threshold, 2)))
            result['Support20'] = Decimal(str(round(prior_20_lows.min(), 2)))
            result['Breakout20_status'] = "POSITIVE" if df['close'].iloc[-1] > threshold else "NEGATIVE"

        # Liquidity20
        if n_sessions >= 20:
            liquidity = (df['close'] * df['volume']).rolling(window=20).mean().iloc[-1]
            result['Liquidity20'] = Decimal(str(round(liquidity, 2)))

        return result
