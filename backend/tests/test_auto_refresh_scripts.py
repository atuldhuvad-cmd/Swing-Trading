import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = ROOT / "scratch" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_broker_name_matching_accepts_verified_equivalents():
    mod = load_script("auto_download_broker_recs_icici.py")
    assert mod.match_confidence("Hindalco Inds.", "Hindalco Industries Limited") == 1.0
    assert mod.match_confidence("Astra Microwave", "Astra Microwave Products Limited") >= 0.8
    assert mod.match_confidence("Apollo Hospitals", "Apollo Hospitals Enterprise Limited") >= 0.8


def test_broker_name_matching_rejects_known_false_matches():
    mod = load_script("auto_download_broker_recs_icici.py")
    assert mod.match_confidence("H.G. Infra Engg.", "Hindalco Industries Limited") < 0.8
    assert mod.match_confidence("A B Real Estate", "Axis Bank Limited") < 0.8
    assert mod.match_confidence("Astral", "Astra Microwave Products Limited") < 0.8
    assert mod.match_confidence("Hind.Aeronautics", "Hindalco Industries Limited") < 0.8


def test_broker_report_link_is_preserved():
    mod = load_script("auto_download_broker_recs_icici.py")
    html = """
      <table><tr><td><a>Carysil</a></td><td>
      <a href="https://mailcontent.icicidirect.com/report.pdf">View Report</a>
      </td></tr></table>
    """
    assert mod.extract_report_links(html) == {
        "Carysil": "https://mailcontent.icicidirect.com/report.pdf"
    }


def test_ohlcv_database_path_follows_application_configuration(tmp_path, monkeypatch):
    mod = load_script("auto_download_ohlcv.py")
    target = tmp_path / "refresh.db"
    monkeypatch.setattr(mod.settings, "database_url", f"sqlite:///{target}")
    assert mod.configured_db_path() == target.resolve()


# ---------------------------------------------------------------- ICICI auto-import

from datetime import date, datetime as _dt


def _icici_env(db_session):
    from app.models import BrokerMaster, SourceTypeMaster, StockMaster, RatingNormalization
    broker = BrokerMaster(display_name="ICICI Securities", canonical_name="ICICI Securities",
                          normalized_name="ICICISECURITIES")
    db_session.add(broker)
    db_session.add(SourceTypeMaster(type_name="BROKER_WEBSITE", description="Broker official website"))
    for orig, norm in (("Buy", "BUY"), ("Hold", "HOLD"), ("Sell", "SELL")):
        if not db_session.query(RatingNormalization).filter_by(original_rating=orig).first():
            db_session.add(RatingNormalization(original_rating=orig, normalized_rating=norm))
    db_session.commit()
    return db_session.query(StockMaster).filter_by(nse_symbol="RELIANCE").one(), broker


def _row(symbol="RELIANCE", *, day="11 Aug 2026", rating="Buy", norm="BUY", conf=1.0, target=1500.0,
         entry=1400.0, **extra):
    row = {"scraped_name": "Reliance Ind", "rating": rating, "normalized_rating": norm, "cmp": 1350.5,
           "target": target, "entry": entry, "stop_loss": float("nan"), "duration": "12-18 Month",
           "date": day, "match_confidence": conf, "matched_symbol": symbol, "ambiguous": False,
           "source_reference": "https://mailcontent.icicidirect.com/x.pdf"}
    row.update(extra)
    return row


TODAY = date(2026, 9, 20)


def test_icici_import_plan_rules(db_session):
    mod = load_script("auto_download_broker_recs_icici.py")
    _icici_env(db_session)
    cases = {
        "CREATE": _row(),
        "AMBIGUOUS_MATCH": _row(ambiguous=True),
        "LOW_CONFIDENCE": _row(conf=0.8),
        "UNMAPPED_RATING": _row(norm=None),
        "BAD_DATE": _row(day="soon"),
        "FUTURE_DATE": _row(day="30 Sep 2026"),
        "STALE_CALL": _row(day="01 Jan 2025"),
        "BAD_TARGET": _row(target=0.0),
        "NOT_TRACKED": _row(symbol=None),
    }
    for expected, rec in cases.items():
        plan = mod.plan_import(db_session, [rec], today=TODAY)[0]
        assert (plan["action"], plan["reason"]) == (("CREATE", None) if expected == "CREATE" else ("SKIP", expected)), expected


def test_icici_import_creates_then_supersedes_and_never_duplicates(db_session):
    from app.models import BrokerRecommendation, RecommendationSource, SourceReference
    mod = load_script("auto_download_broker_recs_icici.py")
    stock, broker = _icici_env(db_session)

    first = _row(day="11 Aug 2026")
    plans = mod.plan_import(db_session, [first], today=TODAY)
    res = mod.apply_import(db_session, plans, {("RELIANCE", "11 Aug 2026"): first}, scraped_at="t1")
    assert [r["status"] for r in res] == ["IMPORTED"]
    rec = db_session.query(BrokerRecommendation).one()
    assert (rec.lifecycle_status, rec.normalized_rating, rec.recommended_price) == ("CURRENT", "BUY", None)
    assert (float(rec.entry_price_low), float(rec.entry_price_high), float(rec.target_price)) == (1400.0, 1400.0, 1500.0)
    assert rec.stop_loss is None and rec.time_horizon_text == "12-18 Month"
    src = db_session.query(SourceReference).join(RecommendationSource).filter(
        RecommendationSource.recommendation_id == rec.recommendation_id).one()
    assert src.verification_status == "VERIFIED_PRIMARY"
    assert src.url == "https://mailcontent.icicidirect.com/x.pdf"
    assert "not the price on the call date" in src.original_text

    # same call again: nothing to do
    again = mod.plan_import(db_session, [first], today=TODAY)[0]
    assert (again["action"], again["reason"]) == ("SKIP", "ALREADY_RECORDED")
    # an older call than the recorded one is not imported
    older = mod.plan_import(db_session, [_row(day="01 Aug 2026")], today=TODAY)[0]
    assert (older["action"], older["reason"]) == ("SKIP", "OLDER_THAN_RECORDED")

    # a newer call supersedes and keeps history
    newer = _row(day="15 Sep 2026", target=1600.0)
    plans = mod.plan_import(db_session, [newer], today=TODAY)
    assert plans[0]["action"] == "SUPERSEDE" and plans[0]["supersedes"] == rec.recommendation_id
    res = mod.apply_import(db_session, plans, {("RELIANCE", "15 Sep 2026"): newer}, scraped_at="t2")
    assert res[0]["status"] == "IMPORTED"
    db_session.expire_all()
    rows = db_session.query(BrokerRecommendation).order_by(BrokerRecommendation.recommendation_id).all()
    assert [r.lifecycle_status for r in rows] == ["SUPERSEDED", "CURRENT"]
    assert rows[0].superseded_by_id == rows[1].recommendation_id

    # forcing an exact duplicate through apply is rejected by the service, not written
    dup = mod.apply_import(db_session, [dict(plans[0], action="CREATE", supersedes=None)],
                           {("RELIANCE", "15 Sep 2026"): newer}, scraped_at="t3")
    assert dup[0]["status"] == "SKIPPED_DUPLICATE"
    assert db_session.query(BrokerRecommendation).count() == 2


def test_icici_import_refuses_broken_page_and_too_many_records(db_session, monkeypatch, tmp_path):
    mod = load_script("auto_download_broker_recs_icici.py")

    class Args:
        import_min_confidence = 0.9
        max_imports = 1

    summary, code = mod.run_import(Args, [], 5, tmp_path / "x.db", False, "s")
    assert code == 3 and "only 5 rows" in summary["refused"]

    _icici_env(db_session)
    monkeypatch.setattr(mod, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    rows = [_row(day="11 Aug 2026"), _row(symbol="RELIANCE", day="12 Aug 2026")]
    summary, code = mod.run_import(Args, rows, 100, tmp_path / "x.db", False, "s")
    # both rows target the same stock; the plan still counts two writes, over the cap
    assert code == 3 and "--max-imports" in summary["refused"]


def test_icici_import_requires_confirmation_on_production(monkeypatch):
    mod = load_script("auto_download_broker_recs_icici.py")
    monkeypatch.setattr(mod, "configured_db_path", lambda: mod.PROD_DB.resolve())
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    monkeypatch.setattr(mod.sys, "argv", ["x", "--import"])
    assert mod.main() == 3


def test_icici_numeric_cells_ignore_nan():
    mod = load_script("auto_download_broker_recs_icici.py")
    assert mod._num(float("nan")) is None and mod._num("x") is None and mod._num(None) is None
    assert mod._num("12.5") == 12.5
    assert mod.parse_call_date("11 Aug 2026") == date(2026, 8, 11) and mod.parse_call_date("bad") is None
