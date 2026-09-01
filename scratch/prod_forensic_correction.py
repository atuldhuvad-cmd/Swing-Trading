"""Production forensic correction: backup, remove synthetic OHLCV, align empty engine tables.

Does not restore an older full database. Does not touch broker_recommendation rows.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
PROD = ROOT / "data" / "swing_trading.db"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / "data" / f"swing_trading_backup_{STAMP}.db"


def counts(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in sorted(tables)}


def main():
    shutil.copy2(PROD, BACKUP)
    conn = sqlite3.connect(PROD)
    conn.execute("PRAGMA foreign_keys=ON")
    before = counts(conn)
    ohlcv_before = before.get("daily_ohlcv", 0)
    rec_before = before.get("broker_recommendation", 0)
    batch_before = before.get("data_import_batch", 0)

    synthetic = conn.execute(
        """
        SELECT COUNT(*) FROM daily_ohlcv
        WHERE trading_date GLOB '????-??-3[2-9]*'
           OR trading_date GLOB '????-??-[4-9]*'
           OR trading_date GLOB '????-??-6*'
           OR (open=100.0 AND high=105.0 AND low=95.0 AND close=102.0 AND volume=1000)
        """
    ).fetchone()[0]

    conn.execute(
        """
        DELETE FROM daily_ohlcv
        WHERE trading_date GLOB '????-??-3[2-9]*'
           OR trading_date GLOB '????-??-[4-9]*'
           OR trading_date GLOB '????-??-6*'
           OR (open=100.0 AND high=105.0 AND low=95.0 AND close=102.0 AND volume=1000)
        """
    )
    conn.execute(
        """
        UPDATE data_import_batch
        SET notes = COALESCE(notes,'') || ' [SYNTHETIC_OHLCV_REMOVED]',
            status = 'INVALIDATED_SYNTHETIC'
        WHERE original_filename LIKE '%CARYSIL-ALL-N.csv'
           OR original_filename LIKE '%ASTRAMICRO-ALL-N.csv'
           OR original_filename LIKE '%HINDALCO-ALL-N.csv'
           OR original_filename LIKE '%GLAND-ALL-N.csv'
           OR original_filename LIKE '%NRBBEARING-ALL-N.csv'
        """
    )

    # Empty incompatible engine tables -> recreate to match application models
    conn.executescript(
        """
        DROP TABLE IF EXISTS candidate_criterion_result;
        DROP TABLE IF EXISTS risk_reward_result;
        DROP TABLE IF EXISTS candidate_evaluation_run;
        DROP TABLE IF EXISTS fundamental_metric;
        DROP TABLE IF EXISTS fundamental_snapshot;
        DROP TABLE IF EXISTS corporate_action;

        CREATE TABLE corporate_action (
            corporate_action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL REFERENCES stock_master(stock_id),
            action_type VARCHAR(50) NOT NULL,
            announcement_date DATE,
            record_date DATE,
            ex_date DATE NOT NULL,
            ratio_numerator NUMERIC(20,6),
            ratio_denominator NUMERIC(20,6),
            cash_amount NUMERIC(20,6),
            source_name VARCHAR(100) NOT NULL,
            source_reference VARCHAR(255),
            notes TEXT,
            created_at DATETIME NOT NULL,
            CHECK (action_type IN ('SPLIT','BONUS','DIVIDEND','RIGHTS','OTHER'))
        );

        CREATE TABLE fundamental_snapshot (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL REFERENCES stock_master(stock_id),
            as_of_date DATE NOT NULL,
            financial_period VARCHAR(50),
            period_type VARCHAR(50),
            source_reference_id INTEGER REFERENCES source_reference(source_reference_id),
            captured_at DATETIME NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            is_superseded BOOLEAN NOT NULL DEFAULT 0,
            superseded_by_id INTEGER REFERENCES fundamental_snapshot(snapshot_id),
            entity_type VARCHAR(50) NOT NULL DEFAULT 'ORDINARY',
            CHECK (entity_type IN ('ORDINARY','BANK','NBFC'))
        );

        CREATE TABLE fundamental_metric (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL REFERENCES fundamental_snapshot(snapshot_id),
            metric_name VARCHAR(100) NOT NULL,
            metric_value NUMERIC(20,4),
            status VARCHAR(50) NOT NULL,
            CHECK (status IN ('KNOWN','UNKNOWN','NOT_APPLICABLE','STALE','UNSUPPORTED')),
            UNIQUE (snapshot_id, metric_name)
        );

        CREATE TABLE candidate_evaluation_run (
            evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL REFERENCES stock_master(stock_id),
            evaluation_date DATETIME NOT NULL,
            technical_snapshot_reference VARCHAR(255),
            fundamental_snapshot_id INTEGER REFERENCES fundamental_snapshot(snapshot_id),
            classification VARCHAR(50) NOT NULL,
            config_fingerprint VARCHAR(64) NOT NULL,
            config_snapshot TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            CHECK (classification IN ('FINAL_CANDIDATE','WATCH','REJECTED','INSUFFICIENT_DATA','RULE_CONFIGURATION_REQUIRED'))
        );

        CREATE TABLE candidate_criterion_result (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL REFERENCES candidate_evaluation_run(evaluation_id),
            criterion_identifier VARCHAR(100) NOT NULL,
            observed_value NUMERIC(20,4),
            operator VARCHAR(50),
            threshold NUMERIC(20,4),
            state VARCHAR(50) NOT NULL,
            reason TEXT,
            evidence_reference VARCHAR(255),
            CHECK (state IN ('PASS','FAIL','UNKNOWN','NOT_APPLICABLE'))
        );

        CREATE TABLE risk_reward_result (
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER NOT NULL REFERENCES candidate_evaluation_run(evaluation_id),
            support NUMERIC(20,4),
            resistance NUMERIC(20,4),
            entry_reference NUMERIC(20,4),
            stop_loss NUMERIC(20,4),
            target NUMERIC(20,4),
            risk_per_share NUMERIC(20,4),
            reward_per_share NUMERIC(20,4),
            risk_reward_ratio NUMERIC(20,4),
            config_fingerprint VARCHAR(64) NOT NULL,
            config_snapshot TEXT NOT NULL,
            created_at DATETIME NOT NULL
        );

        UPDATE alembic_version SET version_num = '6291b9bcaaa3';
        """
    )
    conn.commit()
    after = counts(conn)
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    remaining_ohlcv = conn.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0]
    remaining_synth = conn.execute(
        """
        SELECT COUNT(*) FROM daily_ohlcv
        WHERE trading_date GLOB '????-??-6*'
           OR (open=100.0 AND high=105.0 AND low=95.0 AND close=102.0 AND volume=1000)
        """
    ).fetchone()[0]
    print("BACKUP", BACKUP)
    print("synthetic_identified", synthetic)
    print("ohlcv_before", ohlcv_before, "ohlcv_after", remaining_ohlcv)
    print("rec_before", rec_before, "rec_after", after.get("broker_recommendation"))
    print("batch_before", batch_before, "batch_after", after.get("data_import_batch"))
    print("integrity", integrity)
    print("fk", fk)
    print("remaining_synth", remaining_synth)
    print("alembic", list(conn.execute("SELECT * FROM alembic_version")))
    conn.close()


if __name__ == "__main__":
    main()
