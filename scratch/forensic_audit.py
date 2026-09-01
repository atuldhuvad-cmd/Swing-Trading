"""Read-only forensic comparison of production SQLite vs backups."""
import hashlib
import sqlite3
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DATA = ROOT / "data"
PROD = DATA / "swing_trading.db"

BACKUP_CANDIDATES = [
    DATA / "swing_trading_backup_20260814_111817.db",
    DATA / "swing_trading_copy.db",
    DATA / "swing_trading.pre_stage8.bak",
    DATA / "temp_test.db",
]
BACKUP_CANDIDATES += sorted((DATA / "backups").glob("*.db"))
BACKUP_CANDIDATES += sorted((DATA / "backups").glob("*.bak"))


def file_meta(p: Path):
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {
        "path": str(p),
        "size": p.stat().st_size,
        "mtime": p.stat().st_mtime,
        "sha256": h.hexdigest(),
    }


def tables(conn):
    return [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")]


def count(conn, table):
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error as e:
        return f"ERR:{e}"


def ohlcv_summary(conn):
    if "daily_ohlcv" not in tables(conn):
        return {"present": False}
    cols = [r[1] for r in conn.execute("PRAGMA table_info(daily_ohlcv)")]
    n = conn.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0]
    dups = conn.execute(
        """SELECT COUNT(*) FROM (
             SELECT stock_id, trading_date, series, COUNT(*) c
             FROM daily_ohlcv GROUP BY 1,2,3 HAVING c>1
           )"""
    ).fetchone()[0]
    date_min = conn.execute("SELECT MIN(trading_date) FROM daily_ohlcv").fetchone()[0]
    date_max = conn.execute("SELECT MAX(trading_date) FROM daily_ohlcv").fetchone()[0]
    stocks = conn.execute("SELECT COUNT(DISTINCT stock_id) FROM daily_ohlcv").fetchone()[0]
    by_stock = list(conn.execute(
        "SELECT stock_id, COUNT(*) n, MIN(trading_date), MAX(trading_date) FROM daily_ohlcv GROUP BY stock_id ORDER BY stock_id"
    ))
    sample = list(conn.execute(
        "SELECT daily_ohlcv_id, stock_id, trading_date, series, open, high, low, close, volume, source_name, import_batch_id FROM daily_ohlcv ORDER BY daily_ohlcv_id LIMIT 20"
    ))
    # sequential calendar-day heuristic
    seq_hits = []
    for stock_id, in conn.execute("SELECT DISTINCT stock_id FROM daily_ohlcv"):
        dates = [r[0] for r in conn.execute(
            "SELECT date(trading_date) FROM daily_ohlcv WHERE stock_id=? ORDER BY trading_date", (stock_id,)
        )]
        consecutive = 0
        for a, b in zip(dates, dates[1:]):
            try:
                from datetime import datetime
                da = datetime.strptime(a[:10], "%Y-%m-%d")
                db = datetime.strptime(b[:10], "%Y-%m-%d")
                gap = (db - da).days
                if gap == 1:
                    consecutive += 1
                else:
                    consecutive = 0
                if consecutive >= 10:
                    seq_hits.append(stock_id)
                    break
            except Exception:
                pass
    return {
        "present": True,
        "columns": cols,
        "n": n,
        "dups": dups,
        "date_min": date_min,
        "date_max": date_max,
        "stocks": stocks,
        "by_stock": by_stock,
        "sample": sample,
        "sequential_calendar_streak_stocks": seq_hits,
    }


def compare_ohlcv(prod, bak):
    if "daily_ohlcv" not in tables(prod) or "daily_ohlcv" not in tables(bak):
        return {"comparable": False}
    p = {(r[0], r[1], r[2]): r[3:] for r in prod.execute(
        "SELECT stock_id, trading_date, series, open, high, low, close, volume, source_name, import_batch_id FROM daily_ohlcv"
    )}
    b = {(r[0], r[1], r[2]): r[3:] for r in bak.execute(
        "SELECT stock_id, trading_date, series, open, high, low, close, volume, source_name, import_batch_id FROM daily_ohlcv"
    )}
    only_prod = sorted(set(p) - set(b))
    only_bak = sorted(set(b) - set(p))
    common = set(p) & set(b)
    value_diff = []
    for k in sorted(common):
        if p[k][:5] != b[k][:5]:  # ohlcv
            value_diff.append((k, b[k], p[k]))
            if len(value_diff) >= 20:
                break
    date_shift = []
    # same ids?
    try:
        pid = {r[0]: r[1:] for r in prod.execute(
            "SELECT daily_ohlcv_id, stock_id, trading_date, open, high, low, close, volume FROM daily_ohlcv"
        )}
        bid = {r[0]: r[1:] for r in bak.execute(
            "SELECT daily_ohlcv_id, stock_id, trading_date, open, high, low, close, volume FROM daily_ohlcv"
        )}
        for i in sorted(set(pid) & set(bid)):
            if pid[i][1] != bid[i][1] or pid[i][2:] != bid[i][2:]:
                date_shift.append((i, bid[i], pid[i]))
                if len(date_shift) >= 20:
                    break
    except sqlite3.Error:
        pass
    return {
        "comparable": True,
        "only_prod": len(only_prod),
        "only_bak": len(only_bak),
        "only_prod_sample": only_prod[:10],
        "only_bak_sample": only_bak[:10],
        "value_diff_count_capped": len(value_diff),
        "value_diff_sample": value_diff[:5],
        "id_row_change_sample": date_shift[:5],
        "id_row_change_capped": len(date_shift),
    }


def rec_summary(conn):
    out = {}
    for t in ["broker_recommendation", "data_import_batch", "import_batch", "candidate_evaluation_run", "risk_reward_result", "fundamental_snapshot"]:
        if t in tables(conn):
            out[t] = count(conn, t)
    return out


print("=== FILE META ===")
print("PROD", file_meta(PROD))
seen = set()
for p in BACKUP_CANDIDATES:
    if str(p) in seen:
        continue
    seen.add(str(p))
    m = file_meta(p)
    if m:
        print("BAK", m["size"], m["sha256"][:16], p.name, p)

prod = sqlite3.connect(f"file:{PROD}?mode=ro", uri=True)
print("\n=== PROD TABLES ===", tables(prod))
print("integrity", prod.execute("PRAGMA integrity_check").fetchone())
print("fk", prod.execute("PRAGMA foreign_key_check").fetchall()[:20])
print("counts", {t: count(prod, t) for t in tables(prod)})
print("ohlcv", ohlcv_summary(prod))
print("recs", rec_summary(prod))

print("\n=== COMPARE ===")
for p in BACKUP_CANDIDATES:
    if not p.exists() or p.stat().st_size == 0:
        continue
    bak = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    print("\n---", p.name, "---")
    print("integrity", bak.execute("PRAGMA integrity_check").fetchone())
    print("tables", tables(bak))
    print("counts", {t: count(bak, t) for t in tables(bak) if t in ("daily_ohlcv", "broker_recommendation", "data_import_batch", "import_batch")})
    print("ohlcv", ohlcv_summary(bak))
    print("diff", compare_ohlcv(prod, bak))
    bak.close()
prod.close()
