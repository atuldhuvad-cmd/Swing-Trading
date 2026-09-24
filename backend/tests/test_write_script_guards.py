"""Every script that can write a database calls the schema-readiness guard first.

Scripts are executed with every write primitive replaced by a tripwire and the
guard replaced by a sentinel, so no database, backup or network is ever touched
(several scripts hard-code the Windows production path). A script passes only if
the guard is reached before any tripwire.
"""
import ast
import os
import re
import runpy
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

import app.database
import app.schema_readiness

ROOT = Path(__file__).resolve().parents[2]

# Scripts that write a database: script -> source expressions passed to guard_script_write.
GUARDED = {
    "scratch/batch_a_production_import.py": {"PROD", "SessionLocal"},
    "scratch/batch_b_production_import.py": {"PROD", "SessionLocal"},
    "scratch/batch_a_post_import_eval.py": {"ROOT / 'data' / 'swing_trading.db'", "SessionLocal"},
    "scratch/batch_a_phase5_reeval.py": {"DB", "SessionLocal"},
    "scratch/batch_b_phase5_reeval.py": {"DB", "SessionLocal"},
    "scratch/batch_a_candidate_reeval.py": {"DB", "SessionLocal"},
    "scratch/adanient_rerun_genuine.py": {"SessionLocal"},
    "scratch/prod_forensic_correction.py": {"PROD"},
    "scratch/apply_insurance_migration.py": {"DB"},
    "scratch/end_to_end_proof.py": {"SessionLocal"},
    "backend/scripts/seed_expanded_brokers.py": {"SessionLocal"},
    "backend/scripts/stage6_migrate_prod.py": {"DB_PATH"},
    "backend/scripts/fix_stock_metadata.py": {"DB_PATH"},
    # Disposable-copy writers: the guard checks the copy's real migration state.
    "scratch/batch_a_copy_import_proof.py": {"COPY"},
    "scratch/personal_trade_workflow_validate.py": {"COPY"},
    "scratch/ohlcv_catchup_acceptance.py": {"resolved"},
}
# Scheduled writers use schema_readiness.write_refusal (tests/test_schema_readiness.py).
SCHEDULED = {"scratch/auto_download_ohlcv.py", "scratch/auto_download_broker_recs_icici.py"}
# Not production-capable: they build their own throw-away database from the models.
EXEMPT = {
    "backend/scripts/smoke_workflow.py": "writes only ./data/temp_smoke_test.db created with create_all",
    "backend/scripts/stage5_smoke_test.py": "writes only stage5_smoke_temp.db created with create_all",
}
WRITE_PATTERN = re.compile(r"\.commit\(\)|INSERT INTO|UPDATE [a-z_]+ SET|DELETE FROM|confirm_import|"
                           r"create_recommendation|evaluate_candidate|import_ohlcv_bytes|db\.add\(")


def _scripts():
    return sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                  for d in ("scratch", "backend/scripts") for p in (ROOT / d).glob("*.py"))


def test_every_database_writer_is_classified():
    writers = {s for s in _scripts() if WRITE_PATTERN.search((ROOT / s).read_text(encoding="utf-8", errors="replace"))}
    unclassified = writers - set(GUARDED) - SCHEDULED - set(EXEMPT)
    assert not unclassified, f"database-writing scripts without a readiness guard: {sorted(unclassified)}"
    assert set(GUARDED) | SCHEDULED | set(EXEMPT) <= set(_scripts())


@pytest.mark.parametrize("script", sorted(GUARDED))
def test_writer_guards_every_database_it_writes(script):
    tree = ast.parse((ROOT / script).read_text(encoding="utf-8"))
    args = {ast.unparse(node.args[0]) for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "guard_script_write"}
    assert args == GUARDED[script]


class GuardReached(Exception):
    pass


class Tripwire(Exception):
    pass


@pytest.fixture
def tripwires(monkeypatch):
    """Replace every write primitive; record guard calls and stop at the first one."""
    events = []

    def guard(target):
        events.append(("guard", target))
        raise GuardReached(target)

    def trip(name):
        def _t(*a, **k):
            events.append(("write", name))
            raise Tripwire(name)
        return _t

    real_connect = sqlite3.connect

    def connect(database, *a, **k):
        if "mode=ro" in str(database):
            return real_connect(database, *a, **k)  # read-only access cannot write
        return trip("sqlite3.connect")()

    monkeypatch.setattr(app.schema_readiness, "guard_script_write", guard)
    monkeypatch.setattr(app.database, "SessionLocal", trip("SessionLocal"))
    monkeypatch.setattr(app.database, "engine", None)
    monkeypatch.setattr(sqlite3, "connect", connect)
    for name in ("copy2", "copy", "copyfile", "move", "rmtree"):
        monkeypatch.setattr(shutil, name, trip(f"shutil.{name}"))
    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, trip(f"subprocess.{name}"))
    for name in ("write_text", "write_bytes", "unlink", "mkdir", "rename", "replace"):
        monkeypatch.setattr(Path, name, trip(f"Path.{name}"))
    for name in ("remove", "unlink", "rename", "replace", "makedirs"):
        monkeypatch.setattr(os, name, trip(f"os.{name}"))
    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, "create_engine", trip("create_engine"))
    try:
        import requests
        for name in ("get", "post", "put", "patch", "delete", "Session"):
            monkeypatch.setattr(requests, name, trip(f"requests.{name}"))
    except ImportError:
        pass
    monkeypatch.setenv("DATABASE_URL", os.environ.get("DATABASE_URL", "sqlite:///:memory:"))  # restored afterwards
    return events


def _assert_guard_first(events, expected_target_name):
    assert events, "the script finished without reaching the readiness guard"
    kind, target = events[0]
    assert kind == "guard", f"write before the readiness guard: {events[0]}"
    if expected_target_name == "SessionLocal":
        assert callable(target)
    else:
        assert str(target).endswith(".db") or isinstance(target, (str, Path))


RUN_AS_MAIN = sorted(set(GUARDED) - {"scratch/personal_trade_workflow_validate.py", "scratch/ohlcv_catchup_acceptance.py",
                                     "scratch/batch_a_copy_import_proof.py"})


@pytest.mark.parametrize("script", RUN_AS_MAIN)
def test_guard_runs_before_the_first_write(tripwires, script):
    with pytest.raises((GuardReached, Tripwire, SystemExit)):
        runpy.run_path(str(ROOT / script), run_name="__main__")
    first_target = next(iter(sorted(GUARDED[script], key=lambda t: t == "SessionLocal")))
    _assert_guard_first(tripwires, first_target)


@pytest.mark.parametrize("script", ["scratch/batch_a_copy_import_proof.py", "scratch/personal_trade_workflow_validate.py"])
def test_disposable_copy_is_guarded_right_after_it_is_made(tmp_path, tripwires, monkeypatch, script):
    module = runpy.run_path(str(ROOT / script), run_name="guard_probe")
    prod, copy = tmp_path / "prod.db", tmp_path / "copy.db"
    main = module.get("main")
    globals_ = main.__globals__
    monkeypatch.setitem(globals_, "PROD", prod)
    monkeypatch.setitem(globals_, "COPY", copy)
    copies = []
    monkeypatch.setattr(shutil, "copy2", lambda src, dst: copies.append((src, dst)))  # allowed: creates the copy
    monkeypatch.setitem(globals_, "record_counts", lambda p: {"trade_journal": 0})
    monkeypatch.setattr(Path, "exists", lambda self: True)
    with pytest.raises(GuardReached):
        main()
    assert copies == [(prod, copy)]
    assert tripwires[0] == ("guard", copy)


def test_catchup_acceptance_guards_the_disposable_database(tmp_path, tripwires, monkeypatch):
    module = runpy.run_path(str(ROOT / "scratch/ohlcv_catchup_acceptance.py"), run_name="guard_probe")
    fn = module["require_disposable"]
    disposable = tmp_path / "disposable.db"
    monkeypatch.setitem(fn.__globals__, "resolved_app_db", lambda: disposable)
    with pytest.raises(GuardReached):
        fn(str(disposable))
    assert tripwires == [("guard", disposable)]
    tree = ast.parse((ROOT / "scratch/ohlcv_catchup_acceptance.py").read_text(encoding="utf-8"))
    for command in ("cmd_replay", "cmd_technical"):  # the only commands that write
        first = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == command][0].body[0]
        assert "require_disposable" in ast.unparse(first)


def test_the_real_guard_refuses_a_stale_file_without_touching_it(tmp_path, capsys):
    from app.schema_readiness import guard_script_write
    db = tmp_path / "stale.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        c.execute("INSERT INTO alembic_version VALUES ('f2a7c9d41b3e')")
    before = db.read_bytes()
    with pytest.raises(SystemExit) as exc:
        guard_script_write(db)
    out = capsys.readouterr().out
    assert exc.value.code == 3 and "BEHIND" in out and str(tmp_path) not in out
    assert db.read_bytes() == before
    missing = tmp_path / "missing.db"
    with pytest.raises(SystemExit):
        guard_script_write(missing)
    assert not missing.exists()  # a missing database is never created
