import importlib.util
import pathlib
import sys


def _load_test_ib_broker_module():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "test_ib_broker.py"
    spec = importlib.util.spec_from_file_location("test_ib_broker_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_close_command_defaults_price_to_2650(monkeypatch):
    module = _load_test_ib_broker_module()

    captured = {"price": None}

    def _fake_close_trade(price: float) -> None:
        captured["price"] = price

    monkeypatch.setattr(module, "close_trade", _fake_close_trade)
    monkeypatch.setattr(sys, "argv", ["test_ib_broker.py", "close"])

    module.main()

    assert captured["price"] == 2650.0
