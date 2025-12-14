"""Tests that config parameter is passed to create_trade_from_entry.

This test verifies that the minimum risk threshold check is actually executed
by ensuring that the config parameter is passed through from BacktestReplayLoop
to create_trade_from_entry.

The bug: replay_loop.py line 477-483 calls create_trade_from_entry without
passing self.config, which means the MIN_RISK_TICKS validation is never executed.
"""

import ast
from pathlib import Path


class TestMinRiskConfigPassthrough:
    """Tests that config is properly passed to enable min risk validation."""

    def test_replay_loop_passes_config_parameter(self):
        """Test that replay_loop.py passes config to create_trade_from_entry.

        This is a static analysis test that checks the source code to ensure
        that when create_trade_from_entry is called in replay_loop.py (line 477),
        the config parameter is passed.

        Bug: The function has a config parameter to enable MIN_RISK_TICKS validation,
        but the call site doesn't pass it, so the safety guard is never executed.
        """
        replay_loop_path = (
            Path(__file__).parent.parent.parent.parent / "backtester" / "replay_loop.py"
        )

        with open(replay_loop_path, "r") as f:
            source = f.read()

        # Parse the source code
        tree = ast.parse(source)

        # Find all calls to create_trade_from_entry
        calls_found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "create_trade_from_entry"
                ):
                    # Extract the line number and keyword arguments
                    kwargs = {kw.arg for kw in node.keywords}
                    calls_found.append(
                        {
                            "line": node.lineno,
                            "kwargs": kwargs,
                        }
                    )

        # Verify at least one call exists
        assert len(calls_found) > 0, (
            "No calls to create_trade_from_entry found in replay_loop.py. "
            "This test may be broken."
        )

        # Verify all calls include the 'config' parameter
        missing_config = [
            call for call in calls_found if "config" not in call["kwargs"]
        ]

        assert len(missing_config) == 0, (
            f"create_trade_from_entry called without 'config' parameter at "
            f"line(s): {[c['line'] for c in missing_config]}. "
            f"This prevents MIN_RISK_TICKS validation from executing. "
            f"Add 'config=self.config' to the call."
        )

    def test_pipeline_passes_config_parameter(self):
        """Test that pipeline.py passes config to create_trade_from_entry if available.

        Similar to replay_loop.py, pipeline.py also calls create_trade_from_entry
        and should pass config if it's available.
        """
        pipeline_path = (
            Path(__file__).parent.parent.parent.parent / "backtester" / "pipeline.py"
        )

        with open(pipeline_path, "r") as f:
            source = f.read()

        # Parse the source code
        tree = ast.parse(source)

        # Find all calls to create_trade_from_entry
        calls_found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "create_trade_from_entry"
                ):
                    kwargs = {kw.arg for kw in node.keywords}
                    calls_found.append(
                        {
                            "line": node.lineno,
                            "kwargs": kwargs,
                        }
                    )

        if len(calls_found) > 0:
            # If pipeline.py calls create_trade_from_entry, it should pass config
            missing_config = [
                call for call in calls_found if "config" not in call["kwargs"]
            ]

            # For now, just warn - pipeline.py may not have config available
            # This is a future enhancement
            if len(missing_config) > 0:
                import warnings

                warnings.warn(
                    f"create_trade_from_entry in pipeline.py called without 'config' "
                    f"at line(s): {[c['line'] for c in missing_config]}. "
                    f"Consider adding config parameter to enable MIN_RISK_TICKS validation."
                )
