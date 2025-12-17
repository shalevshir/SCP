"""Backtest results I/O - save and load BacktestResults to/from JSON.

This module provides functions to persist BacktestResults objects to disk
for later analysis and visualization.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from common.logger import get_logger

from backtester.replay_loop import BacktestResults
from backtester.trade import from_dict as trade_from_dict
from backtester.trade import to_dict as trade_to_dict

logger = get_logger(__name__)


def convert_numpy_types(obj: Any) -> Any:
    """Recursively convert numpy types to native Python types for JSON serialization.

    Args:
        obj: Any Python object that may contain numpy types

    Returns:
        The same object structure with numpy types converted to native Python types

    Example:
        >>> import numpy as np
        >>> data = {"bool": np.bool_(True), "int": np.int64(42)}
        >>> convert_numpy_types(data)
        {"bool": True, "int": 42}
    """
    if isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj


def save_results(results: BacktestResults, filepath: str | Path) -> None:
    """Save BacktestResults to JSON file.

    Serializes all trades, executions, and metrics to a JSON file that can
    be loaded later for analysis or visualization.

    Args:
        results: BacktestResults object to save
        filepath: Path to output JSON file (will be created if doesn't exist)

    Example:
        >>> results = loop.run()
        >>> save_results(results, "output/backtest_20250701.json")
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Serialize trades
    trades_data = [trade_to_dict(trade) for trade in results.trades]

    # Serialize executions (EntryExecution objects)
    executions_data = []
    for execution in results.executions:
        # Extract chop context from validation flags
        # Note: validation_flags contains "chop_severity" and "chop_ok", not "chop_detected"
        # Derive chop_detected from chop_severity (same as replay_loop.py does)
        validation_flags = execution.signal.validation_flags
        chop_severity = validation_flags.get("chop_severity", "none")
        chop_detected = chop_severity != "none"  # Correctly derive from severity
        
        # Check if rejection was chop-related
        rejection_reason = execution.rejection_reason or ""
        is_chop_rejection = "chop" in rejection_reason.lower()
        
        exec_dict = {
            "signal_timestamp": execution.signal_timestamp.isoformat(),
            "entry_timestamp": execution.entry_timestamp.isoformat(),
            "entry_price": execution.entry_price,
            "executed": execution.executed,
            "rejection_reason": execution.rejection_reason,
            "chop_context": {
                "chop_detected": chop_detected,
                "chop_severity": chop_severity,
                "chop_rejection": is_chop_rejection,
            },
            "signal": {
                "timestamp": execution.signal.timestamp.isoformat(),
                "symbol": execution.signal.symbol,
                "timeframe": execution.signal.timeframe,
                "direction": execution.signal.direction,
                "setup_type": execution.signal.setup_type,
                "htf_bias": execution.signal.htf_bias,
                "score": execution.signal.score,
                "confidence": execution.signal.confidence,
                "factors": execution.signal.factors,
                "rationale": execution.signal.rationale,
                "validation_flags": execution.signal.validation_flags,
                "enforcer_tier": execution.signal.enforcer_tier,
                "diagnostics": execution.signal.diagnostics,
            },
        }
        executions_data.append(exec_dict)

    # Build complete results dict
    results_dict = {
        "metadata": {
            "saved_at": datetime.now().isoformat(),
            "total_trades": results.total_trades,
            "win_rate": results.win_rate,
            "total_pnl": results.total_pnl,
            "total_pnl_dollars": results.total_pnl_dollars,
        },
        "metrics": {
            "total_pnl": results.total_pnl,
            "total_pnl_dollars": results.total_pnl_dollars,
            "win_rate": results.win_rate,
            "total_trades": results.total_trades,
            "winning_trades": results.winning_trades,
            "losing_trades": results.losing_trades,
            "average_r": results.average_r,
            "max_consecutive_losses": results.max_consecutive_losses,
            "pdll_hits": results.pdll_hits,
            "session_resets": results.session_resets,
            "setup_candidates": results.setup_candidates,
            "rejected_at_scoring": results.rejected_at_scoring,
            "rejected_at_execution": results.rejected_at_execution,
            "executed_trades": results.executed_trades,
        },
        "trades": trades_data,
        "executions": executions_data,
    }

    # Convert numpy types to native Python types for JSON serialization
    results_dict = convert_numpy_types(results_dict)

    # Write to file
    with open(filepath, "w") as f:
        json.dump(results_dict, f, indent=2)

    logger.info(f"Saved backtest results to {filepath} ({len(results.trades)} trades)")


def load_results(filepath: str | Path) -> BacktestResults:
    """Load BacktestResults from JSON file.

    Deserializes trades, executions, and metrics from a JSON file created
    by save_results().

    Args:
        filepath: Path to JSON file

    Returns:
        Reconstructed BacktestResults object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid

    Example:
        >>> results = load_results("output/backtest_20250701.json")
        >>> print(f"Win rate: {results.win_rate:.1f}%")
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Results file not found: {filepath}")

    with open(filepath) as f:
        data = json.load(f)

    # Deserialize trades
    trades = [trade_from_dict(trade_data) for trade_data in data.get("trades", [])]

    # Deserialize executions
    from rule_engine.signal import Signal

    from backtester.entry_model import EntryExecution

    executions = []
    for exec_data in data.get("executions", []):
        signal_data = exec_data["signal"]
        signal = Signal(
            timestamp=datetime.fromisoformat(signal_data["timestamp"]),
            symbol=signal_data["symbol"],
            timeframe=signal_data["timeframe"],
            direction=signal_data["direction"],
            setup_type=signal_data["setup_type"],
            htf_bias=signal_data["htf_bias"],
            score=signal_data["score"],
            confidence=signal_data["confidence"],
            factors=signal_data["factors"],
            rationale=signal_data["rationale"],
            validation_flags=signal_data["validation_flags"],
            enforcer_tier=signal_data["enforcer_tier"],
            diagnostics=signal_data.get("diagnostics", {}),
        )

        execution = EntryExecution(
            signal_timestamp=datetime.fromisoformat(exec_data["signal_timestamp"]),
            entry_timestamp=datetime.fromisoformat(exec_data["entry_timestamp"]),
            entry_price=exec_data["entry_price"],
            signal=signal,
            executed=exec_data["executed"],
            rejection_reason=exec_data.get("rejection_reason"),
        )
        executions.append(execution)

    # Reconstruct BacktestResults
    metrics = data.get("metrics", {})
    results = BacktestResults(
        trades=trades,
        executions=executions,
        total_pnl=metrics.get("total_pnl", 0.0),
        total_pnl_dollars=metrics.get("total_pnl_dollars"),
        win_rate=metrics.get("win_rate", 0.0),
        total_trades=metrics.get("total_trades", 0),
        winning_trades=metrics.get("winning_trades", 0),
        losing_trades=metrics.get("losing_trades", 0),
        average_r=metrics.get("average_r", 0.0),
        max_consecutive_losses=metrics.get("max_consecutive_losses", 0),
        pdll_hits=metrics.get("pdll_hits", 0),
        session_resets=metrics.get("session_resets", 0),
    )

    logger.info(
        f"Loaded backtest results from {filepath} ({len(trades)} trades, "
        f"win_rate={results.win_rate:.1f}%)"
    )

    return results
