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
