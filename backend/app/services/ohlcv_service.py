import csv
import io
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models import StockMaster, DailyOhlcv, DataImportBatch
from app.schemas.ohlcv import OhlcvPreviewRow, OhlcvPreviewResponse, OhlcvConfirmRequest


class OhlcvService:
    SLB_FILENAME_MARKERS = ("quote-slb", "quoteslb")
    SLB_HEADER_MARKERS = ("settlement date", "settlement_date")

    @staticmethod
    def _parse_indian_number(val: str) -> float | None:
        if not val:
            return None
        try:
            return float(val.replace(",", "").strip())
        except ValueError:
            return None

    @staticmethod
    def _is_quote_slb(filename: str, headers: list[str]) -> bool:
        name = (filename or "").lower().replace(" ", "")
        if any(m.replace("-", "") in name.replace("-", "") for m in ("quote-slb", "quoteslb")):
            return True
        lowered = [h.lower() for h in headers]
        return any(m in h for h in lowered for m in OhlcvService.SLB_HEADER_MARKERS)

    @staticmethod
    def _parse_trading_date(date_str: str) -> Optional[datetime]:
        raw = (date_str or "").strip().strip('"')
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def parse_historical_file(db: Session, file_content: bytes, filename: str) -> OhlcvPreviewResponse:
        try:
            text = file_content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_content.decode("latin-1")

        reader = csv.DictReader(io.StringIO(text))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        reader.fieldnames = headers

        if OhlcvService._is_quote_slb(filename, headers):
            raise ValueError("Quote-SLB files are not equity OHLCV and must not be imported")

        is_udiff = "TckrSymb" in headers

        preview_rows = []
        rows_received = 0
        rows_accepted = 0
        rows_rejected = 0
        rows_unmapped = 0
        rows_ignored = 0
        rows_duplicates = 0
        rows_conflicts = 0
        eq_rows_count = 0

        stock_cache: Dict[str, Optional[int]] = {}

        def get_stock_id(symbol: str) -> int | None:
            if symbol not in stock_cache:
                s = db.query(StockMaster).filter(StockMaster.nse_symbol == symbol).first()
                stock_cache[symbol] = s.stock_id if s else None
            return stock_cache[symbol]

        existing_cache: Dict[tuple, DailyOhlcv] = {}
        seen_in_file: set[tuple] = set()

        def existing_row(stock_id: int, dt: datetime, series: str) -> DailyOhlcv | None:
            key = (stock_id, dt.strftime("%Y-%m-%d"), series)
            if key not in existing_cache:
                existing_cache[key] = db.query(DailyOhlcv).filter(
                    DailyOhlcv.stock_id == stock_id,
                    DailyOhlcv.trading_date == dt,
                    DailyOhlcv.series == series,
                ).first()
            return existing_cache[key]

        for row in reader:
            if not any(row.values()):
                continue
            rows_received += 1

            if is_udiff:
                sym = (row.get("TckrSymb") or "").strip()
                ser = (row.get("SctySrs") or "").strip()
                date_str = (row.get("TradDt") or "").strip()
                o = OhlcvService._parse_indian_number(row.get("OpnPric") or "")
                h = OhlcvService._parse_indian_number(row.get("HghPric") or "")
                l = OhlcvService._parse_indian_number(row.get("LwPric") or "")
                c = OhlcvService._parse_indian_number(row.get("ClsPric") or "")
                v_raw = OhlcvService._parse_indian_number(row.get("TtlTradgVol") or "")
                v = int(v_raw) if v_raw is not None else None
            else:
                def col(*names):
                    for n in names:
                        if n in headers:
                            return n
                    return None

                sym_col = col("Symbol") or next((c for c in headers if "Symbol" in c), None)
                ser_col = col("Series") or next((c for c in headers if "Series" in c), None)
                date_col = col("Date") or next((c for c in headers if "Date" in c), None)
                o_col = col("Open Price", "Open")
                h_col = col("High Price", "High")
                l_col = col("Low Price", "Low")
                c_col = col("Close Price", "Close/Last", "Close")
                v_col = col("Total Traded Quantity", "Volume")

                sym = (row.get(sym_col) or "").strip().strip('"') if sym_col else ""
                ser = (row.get(ser_col) or "").strip().strip('"') if ser_col else ""
                date_str = (row.get(date_col) or "").strip().strip('"') if date_col else ""
                o = OhlcvService._parse_indian_number(row.get(o_col) or "") if o_col else None
                h = OhlcvService._parse_indian_number(row.get(h_col) or "") if h_col else None
                l = OhlcvService._parse_indian_number(row.get(l_col) or "") if l_col else None
                c = OhlcvService._parse_indian_number(row.get(c_col) or "") if c_col else None
                v_num = OhlcvService._parse_indian_number(row.get(v_col) or "") if v_col else None
                v = int(v_num) if v_num is not None else None

            if ser != "EQ":
                rows_ignored += 1
                continue

            eq_rows_count += 1
            status = "ACCEPTED"
            msg = None
            parsed_dt = OhlcvService._parse_trading_date(date_str)
            iso_date = parsed_dt.strftime("%Y-%m-%d") if parsed_dt else date_str

            if parsed_dt is None:
                status = "REJECTED"
                msg = "Invalid trading date"
            elif None in (o, h, l, c, v):
                status = "REJECTED"
                msg = "Missing OHLCV data"
            elif o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0:
                status = "REJECTED"
                msg = "Invalid negative/zero OHLCV"
            elif not (l <= o <= h and l <= c <= h):
                status = "REJECTED"
                msg = "Invalid OHLC bounds"
            else:
                file_key = (sym, iso_date, ser)
                if file_key in seen_in_file:
                    status = "DUPLICATE"
                    msg = "Duplicate canonical key in file"
                else:
                    seen_in_file.add(file_key)
                    stock_id = get_stock_id(sym)
                    if not stock_id:
                        status = "UNMAPPED"
                        msg = f"Stock symbol {sym} not found in master"
                    else:
                        existing = existing_row(stock_id, parsed_dt, ser)
                        if existing:
                            same = (
                                float(existing.open) == float(o)
                                and float(existing.high) == float(h)
                                and float(existing.low) == float(l)
                                and float(existing.close) == float(c)
                                and int(existing.volume) == int(v)
                            )
                            if same:
                                status = "DUPLICATE"
                                msg = "Identical existing row (idempotent skip)"
                            else:
                                status = "CONFLICT"
                                msg = "Canonical key exists with different OHLCV"

            if status == "ACCEPTED":
                rows_accepted += 1
            elif status == "UNMAPPED":
                rows_unmapped += 1
            elif status == "DUPLICATE":
                rows_duplicates += 1
            elif status == "CONFLICT":
                rows_conflicts += 1
            else:
                rows_rejected += 1

            preview_rows.append(OhlcvPreviewRow(
                trading_date=iso_date,
                symbol=sym,
                series=ser,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                status=status,
                message=msg,
            ))

        if eq_rows_count == 0:
            raise ValueError("No EQ series rows found in file")

        sha = hashlib.sha256(file_content).hexdigest()
        return OhlcvPreviewResponse(
            file_sha256=sha,
            original_filename=filename,
            rows_received=rows_received,
            rows_accepted=rows_accepted,
            rows_rejected=rows_rejected,
            rows_unmapped=rows_unmapped,
            rows_ignored=rows_ignored,
            rows_duplicates=rows_duplicates,
            rows_conflicts=rows_conflicts,
            preview_rows=preview_rows,
        )

    @staticmethod
    def confirm_import(db: Session, req: OhlcvConfirmRequest, file_content: bytes) -> Dict[str, Any]:
        preview = OhlcvService.parse_historical_file(db, file_content, req.original_filename)
        computed = hashlib.sha256(file_content).hexdigest()
        if req.file_sha256 and req.file_sha256 not in ("dummy",) and req.file_sha256 != computed:
            raise ValueError("file_sha256 does not match uploaded content")

        batch = DataImportBatch(
            import_type="OHLCV_HISTORICAL",
            source_name=req.source_name,
            source_reference=req.source_reference,
            original_filename=req.original_filename,
            file_sha256=computed,
            status="COMPLETED",
            rows_received=preview.rows_received,
            rows_accepted=0,
            rows_rejected=preview.rows_rejected + preview.rows_unmapped + preview.rows_conflicts,
        )
        db.add(batch)
        db.flush()

        stock_cache = {}
        inserted = 0
        duplicates = 0
        conflicts = 0
        for r in preview.preview_rows:
            if r.status == "DUPLICATE":
                duplicates += 1
                continue
            if r.status == "CONFLICT":
                conflicts += 1
                continue
            if r.status != "ACCEPTED":
                continue

            if r.symbol not in stock_cache:
                stock_cache[r.symbol] = db.query(StockMaster).filter(StockMaster.nse_symbol == r.symbol).first().stock_id
            stock_id = stock_cache[r.symbol]

            try:
                dt = datetime.strptime(r.trading_date, "%Y-%m-%d")
            except ValueError:
                batch.rows_rejected += 1
                continue

            existing = db.query(DailyOhlcv).filter(
                DailyOhlcv.stock_id == stock_id,
                DailyOhlcv.trading_date == dt,
                DailyOhlcv.series == r.series,
            ).first()

            if existing:
                if (
                    float(existing.open) == float(r.open)
                    and float(existing.high) == float(r.high)
                    and float(existing.low) == float(r.low)
                    and float(existing.close) == float(r.close)
                    and int(existing.volume) == int(r.volume)
                ):
                    duplicates += 1
                else:
                    conflicts += 1
                    batch.rows_rejected += 1
                continue

            db.add(DailyOhlcv(
                stock_id=stock_id,
                trading_date=dt,
                series=r.series,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                source_name=req.source_name,
                import_batch_id=batch.import_batch_id,
            ))
            inserted += 1
            batch.rows_accepted += 1

        db.commit()
        return {
            "import_batch_id": batch.import_batch_id,
            "status": batch.status,
            "file_sha256": computed,
            "rows_accepted": batch.rows_accepted,
            "rows_rejected": batch.rows_rejected,
            "rows_duplicates": duplicates,
            "rows_conflicts": conflicts,
            "inserted": inserted,
        }
