import importlib.util
import pathlib
import types


def _import_package_from(path: pathlib.Path, alias: str) -> types.ModuleType:
    init_file = path / "__init__.py"
    assert init_file.exists(), f"Missing __init__.py in {path}"
    spec = importlib.util.spec_from_file_location(alias, init_file)
    assert spec and spec.loader, f"Cannot create spec for {alias}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_packages_import():
    root = pathlib.Path(__file__).resolve().parents[1]
    _import_package_from(root / "data-layer", "data_layer")
    _import_package_from(root / "feature-engine", "feature_engine")
    _import_package_from(root / "rule-engine", "rule_engine")
    _import_package_from(root / "backtester", "backtester")
    _import_package_from(root / "common", "common")

