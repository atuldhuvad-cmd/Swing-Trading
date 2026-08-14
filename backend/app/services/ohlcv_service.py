import csv
import io
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
import json

from app.models import StockMaster, DailyOhlcv, DataImportBatch
from app.schemas.ohlcv import OhlcvPreviewRow, OhlcvPreviewResponse, OhlcvConfirmRequest

class OhlcvService:
    @staticmethod
    def _parse_indian_number(val: str) -> float | None:
        if not val: return None
        try:
            return float(val.replace(',', '').strip())
        except ValueError:
            return None

    @staticmethod
    def parse_historical_file(db: Session, file_content: bytes, filename: str) -> OhlcvPreviewResponse:
        try:
            text = file_content.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = file_content.decode('latin-1')
            
        reader = csv.DictReader(io.StringIO(text))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        reader.fieldnames = headers
        
        is_udiff = 'TckrSymb' in headers
        
        preview_rows = []
        rows_received = 0
        rows_accepted = 0
        rows_rejected = 0
        rows_unmapped = 0
        
        stock_cache = {}
        def get_stock_id(symbol: str) -> int | None:
            if symbol not in stock_cache:
                s = db.query(StockMaster).filter(StockMaster.nse_symbol == symbol).first()
                stock_cache[symbol] = s.stock_id if s else None
            return stock_cache[symbol]

        for row in reader:
            if not any(row.values()): continue
            rows_received += 1
            
            if is_udiff:
                sym = row.get('TckrSymb', '').strip()
                ser = row.get('SctySrs', '').strip()
                date_str = row.get('TradDt', '').strip()
                o = OhlcvService._parse_indian_number(row.get('OpnPric', ''))
                h = OhlcvService._parse_indian_number(row.get('HghPric', ''))
                l = OhlcvService._parse_indian_number(row.get('LwPric', ''))
                c = OhlcvService._parse_indian_number(row.get('ClsPric', ''))
                v = OhlcvService._parse_indian_number(row.get('TtlTradgVol', ''))
            else:
                sym_col = next((c for c in headers if 'Symbol' in c), None)
                ser_col = next((c for c in headers if 'Series' in c), None)
                date_col = next((c for c in headers if 'Date' in c), None)
                o_col = next((c for c in headers if c in ('Open Price', 'Open')), None)
                h_col = next((c for c in headers if c in ('High Price', 'High')), None)
                l_col = next((c for c in headers if c in ('Low Price', 'Low')), None)
                c_col = next((c for c in headers if c in ('Close Price', 'Close/Last')), None)
                v_col = next((c for c in headers if c in ('Total Traded Quantity', 'Volume')), None)
                
                sym = row.get(sym_col, '').strip().strip('"') if sym_col else ''
                ser = row.get(ser_col, '').strip().strip('"') if ser_col else ''
                date_str = row.get(date_col, '').strip().strip('"') if date_col else ''
                
                o = OhlcvService._parse_indian_number(row.get(o_col, '')) if o_col else None
                h = OhlcvService._parse_indian_number(row.get(h_col, '')) if h_col else None
                l = OhlcvService._parse_indian_number(row.get(l_col, '')) if l_col else None
                c = OhlcvService._parse_indian_number(row.get(c_col, '')) if c_col else None
                v = int(OhlcvService._parse_indian_number(row.get(v_col, ''))) if v_col and OhlcvService._parse_indian_number(row.get(v_col, '')) is not None else None

            if ser != 'EQ':
                rows_rejected += 1
                continue
                
            status = "ACCEPTED"
            msg = None
            
            if None in (o, h, l, c, v):
                status = "REJECTED"
                msg = "Missing OHLCV data"
            elif o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0:
                status = "REJECTED"
                msg = "Invalid negative/zero OHLCV"
            elif not (l <= o <= h and l <= c <= h):
                status = "REJECTED"
                msg = "Invalid OHLC bounds"
            else:
                stock_id = get_stock_id(sym)
                if not stock_id:
                    status = "UNMAPPED"
                    msg = f"Stock symbol {sym} not found in master"
                
            if status == "ACCEPTED":
                rows_accepted += 1
            elif status == "UNMAPPED":
                rows_unmapped += 1
            else:
                rows_rejected += 1
                
            preview_rows.append(OhlcvPreviewRow(
                trading_date=date_str,
                symbol=sym,
                series=ser,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                status=status,
                message=msg
            ))
            
        sha = hashlib.sha256(file_content).hexdigest()
        
        # Format dates reliably for preview display
        for r in preview_rows:
            try:
                if '-' in r.trading_date and len(r.trading_date) == 11:
                    dt = datetime.strptime(r.trading_date, '%d-%b-%Y')
                elif '-' in r.trading_date:
                    dt = datetime.strptime(r.trading_date, '%Y-%m-%d')
                else:
                    dt = datetime.strptime(r.trading_date, '%d-%b-%Y')
                r.trading_date = dt.strftime('%Y-%m-%d')
            except Exception:
                pass
                
        return OhlcvPreviewResponse(
            file_sha256=sha,
            original_filename=filename,
            rows_received=rows_received,
            rows_accepted=rows_accepted,
            rows_rejected=rows_rejected,
            rows_unmapped=rows_unmapped,
            preview_rows=preview_rows
        )

    @staticmethod
    def confirm_import(db: Session, req: OhlcvConfirmRequest, file_content: bytes) -> Dict[str, Any]:
        preview = OhlcvService.parse_historical_file(db, file_content, req.original_filename)
        
        batch = DataImportBatch(
            import_type="OHLCV_HISTORICAL",
            source_name=req.source_name,
            original_filename=req.original_filename,
            status="COMPLETED",
            rows_received=preview.rows_received,
            rows_accepted=0,
            rows_rejected=preview.rows_rejected + preview.rows_unmapped
        )
        db.add(batch)
        db.flush()
        
        stock_cache = {}
        for r in preview.preview_rows:
            if r.status != "ACCEPTED":
                continue
                
            if r.symbol not in stock_cache:
                stock_cache[r.symbol] = db.query(StockMaster).filter(StockMaster.nse_symbol == r.symbol).first().stock_id
            stock_id = stock_cache[r.symbol]
            
            try:
                dt = datetime.strptime(r.trading_date, '%Y-%m-%d').date()
            except ValueError:
                batch.rejected_rows += 1
                continue
            
            # Check for existing
            existing = db.query(DailyOhlcv).filter(
                DailyOhlcv.stock_id == stock_id,
                DailyOhlcv.trading_date == dt,
                DailyOhlcv.series == r.series
            ).first()
            
            if existing:
                if (existing.open == r.open and existing.high == r.high and 
                    existing.low == r.low and existing.close == r.close and 
                    existing.volume == r.volume):
                    pass # Just skip duplicate
                else:
                    batch.rows_rejected += 1
                continue
                
            ohlcv = DailyOhlcv(
                stock_id=stock_id,
                trading_date=dt,
                series=r.series,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                source_name=req.source_name,
                import_batch_id=batch.import_batch_id
            )
            db.add(ohlcv)
            batch.rows_accepted += 1
            
        db.commit()
        return {
            "import_batch_id": batch.import_batch_id,
            "status": batch.status,
            "rows_accepted": batch.rows_accepted,
            "rows_rejected": batch.rows_rejected
        }
