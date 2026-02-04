#!/usr/bin/env python3
"""Generate comprehensive diagnostic report for one or more trades.

This script produces detailed HTML and JSON reports for diagnosing trades,
including market data, features, and HTF bias context before, during, and after each trade.

Usage:
    # Single trade by ID
    python scripts/generate_trade_diagnostic.py --trade-id <uuid> --output reports/trade_diagnostic

    # Multiple trades by ID (generates separate reports for each)
    python scripts/generate_trade_diagnostic.py --trade-id <uuid1> <uuid2> <uuid3> --output reports/diagnostics

    # List recent trades to find IDs
    python scripts/generate_trade_diagnostic.py --list-trades --start 2025-01-01 --end 2025-01-31

Examples:
    # Single trade
    python scripts/generate_trade_diagnostic.py --trade-id 550e8400-e29b-41d4-a716-446655440000 --output reports/trade_diag

    # Multiple trades (creates trade_diag_001.html, trade_diag_002.html, etc.)
    python scripts/generate_trade_diagnostic.py --trade-id abc123 def456 ghi789 --output reports/trade_diag
"""

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
from scp_shared.common import get_logger
from scp_shared.database import DatabasePool

logger = get_logger(__name__)

# Constants
CONTEXT_BARS_BEFORE = 30  # Bars to fetch before entry
CONTEXT_BARS_AFTER_CLOSE = 10  # Bars to fetch after exit
POINT_VALUE = 100.0  # GC futures point value in USD


class TradeDiagnosticGenerator:
    """Generate comprehensive diagnostic reports for individual trades."""

    def __init__(self, db_pool: DatabasePool):
        self.db_pool = db_pool
        self.trade: dict[str, Any] = {}
        self.candles: list[dict[str, Any]] = []
        self.features_at_entry: dict[str, Any] = {}
        self.features_context: list[dict[str, Any]] = []
        self.htf_bias_at_entry: dict[str, Any] = {}
        self.htf_bias_context: list[dict[str, Any]] = []
        self.signal_history: dict[str, Any] = {}

    async def list_trades(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List trades within a date range for selection.

        Args:
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum number of trades to return

        Returns:
            List of trade summaries
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    opened_at,
                    closed_at,
                    direction,
                    setup_type,
                    entry_price,
                    exit_price,
                    exit_reason,
                    pnl_dollars,
                    r_multiple,
                    state
                FROM trades
                WHERE opened_at >= $1 AND opened_at <= $2
                ORDER BY opened_at DESC
                LIMIT $3
                """,
                start_date,
                end_date,
                limit,
            )

            trades = []
            for row in rows:
                pnl_r = row["r_multiple"]
                result = "WIN" if pnl_r and pnl_r > 0 else "LOSS" if pnl_r else "OPEN"
                trades.append({
                    "id": str(row["id"]),
                    "opened_at": row["opened_at"].isoformat(),
                    "closed_at": row["closed_at"].isoformat() if row["closed_at"] else None,
                    "direction": row["direction"],
                    "setup_type": row["setup_type"],
                    "entry_price": float(row["entry_price"]),
                    "exit_price": float(row["exit_price"]) if row["exit_price"] else None,
                    "exit_reason": row["exit_reason"],
                    "pnl_dollars": float(row["pnl_dollars"]) if row["pnl_dollars"] else None,
                    "pnl_r": float(pnl_r) if pnl_r else None,
                    "result": result,
                    "state": row["state"],
                })

            return trades

    async def generate_report(
        self,
        trade_id: str,
        output_path: Path,
    ) -> None:
        """Generate complete diagnostic report for a trade.

        Args:
            trade_id: UUID of the trade to diagnose
            output_path: Output path (without extension)
        """
        logger.info(f"Generating diagnostic report for trade {trade_id}")

        # Fetch all data
        await self._fetch_trade(trade_id)
        await self._fetch_signal_history()
        await self._fetch_candles()
        await self._fetch_features()
        await self._fetch_htf_bias()

        # Generate outputs
        json_path = Path(f"{output_path}.json")
        html_path = Path(f"{output_path}.html")

        self._write_json_report(json_path)
        self._write_html_report(html_path)

        logger.info(f"Reports generated:")
        logger.info(f"  JSON: {json_path}")
        logger.info(f"  HTML: {html_path}")

    async def _fetch_trade(self, trade_id: str) -> None:
        """Fetch trade details from database."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    signal_id,
                    opened_at,
                    closed_at,
                    direction,
                    setup_type,
                    entry_price,
                    sl_price,
                    tp_price,
                    quantity,
                    exit_price,
                    exit_reason,
                    pnl_points,
                    pnl_dollars,
                    r_multiple,
                    state,
                    entry_bar_idx,
                    reached_1r,
                    confirmations,
                    transition_history,
                    created_at,
                    updated_at
                FROM trades
                WHERE id = $1
                """,
                UUID(trade_id),
            )

            if not row:
                raise ValueError(f"Trade not found: {trade_id}")

            # Calculate duration
            duration_minutes = None
            if row["closed_at"] and row["opened_at"]:
                duration_minutes = (row["closed_at"] - row["opened_at"]).total_seconds() / 60

            # Calculate risk/reward metrics
            entry = float(row["entry_price"])
            sl = float(row["sl_price"])
            tp = float(row["tp_price"])
            risk_points = abs(entry - sl)
            reward_points = abs(tp - entry)
            rr_ratio = reward_points / risk_points if risk_points > 0 else 0

            self.trade = {
                "id": str(row["id"]),
                "signal_id": str(row["signal_id"]) if row["signal_id"] else None,
                "opened_at": row["opened_at"].isoformat(),
                "opened_at_dt": row["opened_at"],
                "closed_at": row["closed_at"].isoformat() if row["closed_at"] else None,
                "closed_at_dt": row["closed_at"],
                "direction": row["direction"],
                "setup_type": row["setup_type"],
                "entry_price": entry,
                "sl_price": sl,
                "tp_price": tp,
                "quantity": row["quantity"],
                "exit_price": float(row["exit_price"]) if row["exit_price"] else None,
                "exit_reason": row["exit_reason"],
                "pnl_points": float(row["pnl_points"]) if row["pnl_points"] else None,
                "pnl_dollars": float(row["pnl_dollars"]) if row["pnl_dollars"] else None,
                "r_multiple": float(row["r_multiple"]) if row["r_multiple"] else None,
                "state": row["state"],
                "entry_bar_idx": row["entry_bar_idx"],
                "reached_1r": row["reached_1r"],
                "confirmations": row["confirmations"],
                "transition_history": row["transition_history"],
                "duration_minutes": duration_minutes,
                "risk_points": risk_points,
                "reward_points": reward_points,
                "rr_ratio": round(rr_ratio, 2),
                "risk_dollars": risk_points * POINT_VALUE,
                "reward_dollars": reward_points * POINT_VALUE,
            }

    async def _fetch_signal_history(self) -> None:
        """Fetch signal history entry with full context snapshots."""
        if not self.trade.get("signal_id"):
            self.signal_history = {}
            return

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    timestamp,
                    symbol,
                    timeframe,
                    direction,
                    setup_type,
                    score,
                    confidence,
                    was_approved,
                    rejection_stage,
                    features_snapshot,
                    htf_bias_snapshot,
                    factor_scores,
                    diagnostics
                FROM signal_history
                WHERE trade_id = $1 OR id::text = $2
                LIMIT 1
                """,
                UUID(self.trade["id"]),
                self.trade.get("signal_id"),
            )

            if row:
                # Parse JSONB fields
                features_snapshot = row["features_snapshot"]
                if isinstance(features_snapshot, str):
                    features_snapshot = json.loads(features_snapshot) if features_snapshot else {}

                htf_bias_snapshot = row["htf_bias_snapshot"]
                if isinstance(htf_bias_snapshot, str):
                    htf_bias_snapshot = json.loads(htf_bias_snapshot) if htf_bias_snapshot else {}

                factor_scores = row["factor_scores"]
                if isinstance(factor_scores, str):
                    factor_scores = json.loads(factor_scores) if factor_scores else {}

                diagnostics = row["diagnostics"]
                if isinstance(diagnostics, str):
                    diagnostics = json.loads(diagnostics) if diagnostics else {}

                self.signal_history = {
                    "id": str(row["id"]),
                    "timestamp": row["timestamp"].isoformat(),
                    "symbol": row["symbol"],
                    "timeframe": row["timeframe"],
                    "direction": row["direction"],
                    "setup_type": row["setup_type"],
                    "score": float(row["score"]),
                    "confidence": row["confidence"],
                    "was_approved": row["was_approved"],
                    "rejection_stage": row["rejection_stage"],
                    "features_snapshot": features_snapshot,
                    "htf_bias_snapshot": htf_bias_snapshot,
                    "factor_scores": factor_scores,
                    "diagnostics": diagnostics,
                }
            else:
                self.signal_history = {}

    async def _fetch_candles(self) -> None:
        """Fetch candles around the trade period."""
        entry_time = self.trade["opened_at_dt"]
        exit_time = self.trade.get("closed_at_dt") or entry_time

        # Calculate time window (assuming 1m candles)
        start_time = entry_time - timedelta(minutes=CONTEXT_BARS_BEFORE)
        end_time = exit_time + timedelta(minutes=CONTEXT_BARS_AFTER_CLOSE)

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    timestamp,
                    symbol,
                    timeframe,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM candles
                WHERE symbol = 'GC'
                  AND timeframe = '1m'
                  AND timestamp >= $1
                  AND timestamp <= $2
                ORDER BY timestamp ASC
                """,
                start_time,
                end_time,
            )

            self.candles = []
            for row in rows:
                candle = {
                    "timestamp": row["timestamp"].isoformat(),
                    "timestamp_dt": row["timestamp"],
                    "symbol": row["symbol"],
                    "timeframe": row["timeframe"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]) if row["volume"] else 0,
                }

                # Mark candle position relative to trade
                ts = row["timestamp"]
                if ts < entry_time:
                    candle["position"] = "before_entry"
                elif ts == entry_time or (entry_time <= ts <= exit_time):
                    candle["position"] = "during_trade"
                else:
                    candle["position"] = "after_exit"

                self.candles.append(candle)

    async def _fetch_features(self) -> None:
        """Fetch features context around entry and exit."""
        entry_time = self.trade["opened_at_dt"]
        exit_time = self.trade.get("closed_at_dt") or entry_time

        # Fetch context around entry
        start_time = entry_time - timedelta(minutes=CONTEXT_BARS_BEFORE)
        end_time = exit_time + timedelta(minutes=CONTEXT_BARS_AFTER_CLOSE)

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM features
                WHERE symbol = 'GC'
                  AND timeframe = '1m'
                  AND timestamp >= $1
                  AND timestamp <= $2
                ORDER BY timestamp ASC
                """,
                start_time,
                end_time,
            )

            self.features_context = []
            for row in rows:
                feature = self._row_to_dict(row)
                ts = row["timestamp"]

                # Mark position relative to trade
                if ts < entry_time:
                    feature["position"] = "before_entry"
                elif ts == entry_time or (entry_time <= ts <= exit_time):
                    feature["position"] = "during_trade"
                else:
                    feature["position"] = "after_exit"

                # Capture features at exact entry time
                if ts == entry_time:
                    self.features_at_entry = feature.copy()

                self.features_context.append(feature)

            # If no exact match, use closest before entry
            if not self.features_at_entry and self.features_context:
                before_entry = [f for f in self.features_context if f["position"] == "before_entry"]
                if before_entry:
                    self.features_at_entry = before_entry[-1].copy()

    async def _fetch_htf_bias(self) -> None:
        """Fetch HTF bias context around entry and exit."""
        entry_time = self.trade["opened_at_dt"]
        exit_time = self.trade.get("closed_at_dt") or entry_time

        # HTF bias updates less frequently, so use a wider window
        start_time = entry_time - timedelta(hours=2)
        end_time = exit_time + timedelta(minutes=30)

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM htf_bias_history
                WHERE timestamp >= $1
                  AND timestamp <= $2
                ORDER BY timestamp ASC
                """,
                start_time,
                end_time,
            )

            self.htf_bias_context = []
            for row in rows:
                htf = self._row_to_dict(row)
                ts = row["timestamp"]

                # Mark position relative to trade
                if ts < entry_time:
                    htf["position"] = "before_entry"
                elif ts == entry_time or (entry_time <= ts <= exit_time):
                    htf["position"] = "during_trade"
                else:
                    htf["position"] = "after_exit"

                # Capture HTF bias closest to entry
                if ts <= entry_time:
                    self.htf_bias_at_entry = htf.copy()

                self.htf_bias_context.append(htf)

    def _row_to_dict(self, row: asyncpg.Record) -> dict[str, Any]:
        """Convert asyncpg Record to dict with proper type handling."""
        result = {}
        for key, value in dict(row).items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif hasattr(value, "__float__"):
                result[key] = float(value)
            elif value is None:
                result[key] = None
            else:
                result[key] = value
        return result

    def _write_json_report(self, output_path: Path) -> None:
        """Write comprehensive JSON report."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report_type": "trade_diagnostic",
            "trade": {k: v for k, v in self.trade.items() if not k.endswith("_dt")},
            "signal_history": self.signal_history,
            "features_at_entry": self.features_at_entry,
            "htf_bias_at_entry": self.htf_bias_at_entry,
            "market_data": {
                "candles": [{k: v for k, v in c.items() if not k.endswith("_dt")} for c in self.candles],
                "features_context": self.features_context,
                "htf_bias_context": self.htf_bias_context,
            },
            "summary": self._generate_summary(),
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"JSON report written to {output_path}")

    def _generate_summary(self) -> dict[str, Any]:
        """Generate a summary of key diagnostic information."""
        trade = self.trade
        features = self.features_at_entry
        htf = self.htf_bias_at_entry

        summary = {
            "outcome": "WIN" if trade.get("r_multiple", 0) and trade["r_multiple"] > 0 else "LOSS",
            "pnl_r": trade.get("r_multiple"),
            "pnl_dollars": trade.get("pnl_dollars"),
            "duration_minutes": trade.get("duration_minutes"),
            "exit_reason": trade.get("exit_reason"),
            "key_metrics_at_entry": {},
            "potential_issues": [],
        }

        # Extract key metrics at entry
        if features:
            summary["key_metrics_at_entry"]["vwap"] = features.get("vwap")
            summary["key_metrics_at_entry"]["vwap_deviation"] = features.get("vwap_deviation")
            summary["key_metrics_at_entry"]["vwap_deviation_normalized"] = features.get("vwap_deviation_normalized")
            summary["key_metrics_at_entry"]["rsi"] = features.get("rsi")
            summary["key_metrics_at_entry"]["atr"] = features.get("atr")
            summary["key_metrics_at_entry"]["structure_label"] = features.get("structure_label")
            summary["key_metrics_at_entry"]["bos_recent"] = features.get("bos_recent")
            summary["key_metrics_at_entry"]["structure_clarity"] = features.get("structure_clarity")

        if htf:
            summary["key_metrics_at_entry"]["htf_bias"] = htf.get("bias")
            summary["key_metrics_at_entry"]["htf_score"] = htf.get("score")
            summary["key_metrics_at_entry"]["htf_confidence"] = htf.get("confidence")
            summary["key_metrics_at_entry"]["dxy_aligned"] = htf.get("dxy_aligned")
            summary["key_metrics_at_entry"]["chop_detected"] = htf.get("chop_detected")

        # Identify potential issues
        if features:
            # Check RSI extremes
            rsi = features.get("rsi")
            if rsi and (rsi > 70 or rsi < 30):
                summary["potential_issues"].append(f"RSI at extreme: {rsi:.1f}")

            # Check structure clarity
            clarity = features.get("structure_clarity")
            if clarity and clarity < 0.5:
                summary["potential_issues"].append(f"Low structure clarity: {clarity:.2f}")

        if htf:
            # Check for chop
            if htf.get("chop_detected"):
                summary["potential_issues"].append("HTF chop detected at entry")

            # Check DXY alignment
            if not htf.get("dxy_aligned"):
                summary["potential_issues"].append("DXY not aligned at entry")

            # Check HTF confidence
            confidence = htf.get("confidence")
            if confidence and confidence not in ("A+", "A"):
                summary["potential_issues"].append(f"Low HTF confidence: {confidence}")

        return summary

    def _write_html_report(self, output_path: Path) -> None:
        """Write interactive HTML report with charts."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html = self._generate_html()

        with open(output_path, "w") as f:
            f.write(html)

        logger.info(f"HTML report written to {output_path}")

    def _generate_html(self) -> str:
        """Generate HTML report content with candlestick chart."""
        trade = self.trade
        features = self.features_at_entry
        htf = self.htf_bias_at_entry
        signal = self.signal_history
        summary = self._generate_summary()

        # Prepare chart data
        chart_data = self._prepare_chart_data()

        # Determine result styling
        is_win = trade.get("r_multiple", 0) and trade["r_multiple"] > 0
        result_class = "positive" if is_win else "negative"
        result_text = "WIN" if is_win else "LOSS"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trade Diagnostic - {trade['id'][:8]}</title>
    <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #0a0e27;
            color: #e0e6ed;
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        h2 {{
            font-size: 1.5rem;
            margin: 2rem 0 1rem;
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 0.5rem;
        }}
        h3 {{
            font-size: 1.2rem;
            margin: 1.5rem 0 0.75rem;
            color: #a0aec0;
        }}
        .subtitle {{
            color: #a0aec0;
            font-size: 1rem;
            margin-bottom: 2rem;
        }}
        .result-badge {{
            display: inline-block;
            padding: 0.5rem 1.5rem;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.2rem;
            margin-left: 1rem;
        }}
        .result-badge.positive {{ background: #48bb78; color: #1a202c; }}
        .result-badge.negative {{ background: #f56565; color: #1a202c; }}
        .section {{
            background: #161b33;
            border-radius: 12px;
            padding: 1.5rem;
            margin: 1.5rem 0;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 1rem 0;
        }}
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
        }}
        .metric-card {{
            background: #1e2541;
            border-radius: 8px;
            padding: 1rem;
            border-left: 4px solid #667eea;
        }}
        .metric-label {{
            color: #a0aec0;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.25rem;
        }}
        .metric-value {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #e0e6ed;
        }}
        .metric-value.positive {{ color: #48bb78; }}
        .metric-value.negative {{ color: #f56565; }}
        .metric-value.neutral {{ color: #ed8936; }}
        .metric-value.small {{ font-size: 1rem; }}
        #chart-container {{
            width: 100%;
            height: 500px;
            background: #1e2541;
            border-radius: 8px;
            margin: 1rem 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            background: #1e2541;
            border-radius: 8px;
            overflow: hidden;
            font-size: 0.9rem;
        }}
        th {{
            background: #252d4a;
            color: #a0aec0;
            text-align: left;
            padding: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.5px;
        }}
        td {{
            padding: 0.75rem;
            border-top: 1px solid #2d3748;
        }}
        tr:hover {{ background: #252d4a; }}
        .issue-badge {{
            display: inline-block;
            background: #f6ad55;
            color: #1a202c;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            margin: 0.25rem;
        }}
        .data-section {{
            max-height: 400px;
            overflow-y: auto;
        }}
        code {{
            background: #2d3748;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
        }}
        .expandable {{
            cursor: pointer;
        }}
        .expandable-content {{
            display: none;
            margin-top: 1rem;
        }}
        .expandable.active .expandable-content {{
            display: block;
        }}
        .expandable-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .expand-icon {{
            font-size: 1.2rem;
        }}
        pre {{
            background: #1e2541;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 0.8rem;
            max-height: 300px;
            overflow-y: auto;
        }}
        .footer {{
            text-align: center;
            color: #718096;
            margin-top: 3rem;
            padding-top: 2rem;
            border-top: 1px solid #2d3748;
        }}
        .tab-container {{
            display: flex;
            border-bottom: 2px solid #2d3748;
            margin-bottom: 1rem;
        }}
        .tab {{
            padding: 0.75rem 1.5rem;
            cursor: pointer;
            color: #a0aec0;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            transition: all 0.2s;
        }}
        .tab:hover {{
            color: #e0e6ed;
        }}
        .tab.active {{
            color: #667eea;
            border-bottom-color: #667eea;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; align-items: center; margin-bottom: 0.5rem;">
            <h1>Trade Diagnostic Report</h1>
            <span class="result-badge {result_class}">{result_text} {trade.get('r_multiple', 0):.2f}R</span>
        </div>
        <p class="subtitle">
            Trade ID: <code>{trade['id']}</code> |
            {trade['setup_type']} {trade['direction'].upper()} |
            {trade['opened_at'][:19]}
        </p>

        <!-- Trade Summary -->
        <div class="section">
            <h2>Trade Summary</h2>
            <div class="grid">
                <div class="metric-card">
                    <div class="metric-label">Setup Type</div>
                    <div class="metric-value small">{trade['setup_type']}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Direction</div>
                    <div class="metric-value small">{trade['direction'].upper()}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Entry Price</div>
                    <div class="metric-value">{trade['entry_price']:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Exit Price</div>
                    <div class="metric-value">{trade.get('exit_price', 'N/A')}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Stop Loss</div>
                    <div class="metric-value negative">{trade['sl_price']:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Take Profit</div>
                    <div class="metric-value positive">{trade['tp_price']:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Risk/Reward</div>
                    <div class="metric-value">{trade['rr_ratio']}:1</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Risk ($)</div>
                    <div class="metric-value small">${trade['risk_dollars']:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">P&L ($)</div>
                    <div class="metric-value {result_class}">${trade.get('pnl_dollars', 0) or 0:.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Duration</div>
                    <div class="metric-value small">{trade.get('duration_minutes', 0) or 0:.0f} min</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Exit Reason</div>
                    <div class="metric-value small">{trade.get('exit_reason', 'N/A')}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Reached +1R</div>
                    <div class="metric-value small">{'Yes' if trade.get('reached_1r') else 'No'}</div>
                </div>
            </div>
        </div>

        <!-- Price Chart -->
        <div class="section">
            <h2>Price Action</h2>
            <div id="chart-container"></div>
            <p style="color: #a0aec0; font-size: 0.85rem; margin-top: 0.5rem;">
                Entry marked in blue | Stop Loss in red | Take Profit in green | Exit marked with vertical line
            </p>
        </div>

        <!-- Potential Issues -->
        {self._generate_issues_html(summary)}

        <!-- Context at Entry -->
        <div class="section">
            <h2>Context at Entry</h2>
            <div class="grid-2">
                <div>
                    <h3>Features (1m)</h3>
                    {self._generate_features_table_html(features)}
                </div>
                <div>
                    <h3>HTF Bias</h3>
                    {self._generate_htf_table_html(htf)}
                </div>
            </div>
        </div>

        <!-- Signal Scoring -->
        {self._generate_signal_section_html(signal)}

        <!-- Detailed Data (Tabbed) -->
        <div class="section">
            <h2>Detailed Market Data</h2>
            <div class="tab-container">
                <div class="tab active" onclick="switchTab(event, 'candles-tab')">Candles</div>
                <div class="tab" onclick="switchTab(event, 'features-tab')">Features Context</div>
                <div class="tab" onclick="switchTab(event, 'htf-tab')">HTF Bias Context</div>
            </div>

            <div id="candles-tab" class="tab-content active">
                <div class="data-section">
                    {self._generate_candles_table_html()}
                </div>
            </div>

            <div id="features-tab" class="tab-content">
                <div class="data-section">
                    {self._generate_features_context_table_html()}
                </div>
            </div>

            <div id="htf-tab" class="tab-content">
                <div class="data-section">
                    {self._generate_htf_context_table_html()}
                </div>
            </div>
        </div>

        <!-- Raw Data (Expandable) -->
        <div class="section expandable" onclick="this.classList.toggle('active')">
            <div class="expandable-header">
                <h2 style="margin: 0; border: none; padding: 0;">Raw Data (JSON)</h2>
                <span class="expand-icon">▼</span>
            </div>
            <div class="expandable-content">
                <pre>{json.dumps({
                    "trade": {k: v for k, v in trade.items() if not k.endswith("_dt")},
                    "signal_history": signal,
                    "features_at_entry": features,
                    "htf_bias_at_entry": htf,
                }, indent=2, default=str)}</pre>
            </div>
        </div>

        <div class="footer">
            <p>Generated at {datetime.now(timezone.utc).isoformat()[:19]}Z</p>
            <p>SCP Trade Diagnostic Report v1.0</p>
        </div>
    </div>

    <script>
        // Chart data
        const chartData = {json.dumps(chart_data)};
        const trade = {json.dumps({
            "entry_price": trade["entry_price"],
            "sl_price": trade["sl_price"],
            "tp_price": trade["tp_price"],
            "exit_price": trade.get("exit_price"),
            "direction": trade["direction"],
            "opened_at": trade["opened_at"],
            "closed_at": trade.get("closed_at"),
        })};

        // Initialize chart
        const chartContainer = document.getElementById('chart-container');
        const chart = LightweightCharts.createChart(chartContainer, {{
            layout: {{
                background: {{ type: 'solid', color: '#1e2541' }},
                textColor: '#a0aec0',
            }},
            grid: {{
                vertLines: {{ color: '#2d3748' }},
                horzLines: {{ color: '#2d3748' }},
            }},
            timeScale: {{
                timeVisible: true,
                secondsVisible: false,
            }},
            crosshair: {{
                mode: LightweightCharts.CrosshairMode.Normal,
            }},
        }});

        // Add candlestick series
        const candleSeries = chart.addCandlestickSeries({{
            upColor: '#48bb78',
            downColor: '#f56565',
            borderUpColor: '#48bb78',
            borderDownColor: '#f56565',
            wickUpColor: '#48bb78',
            wickDownColor: '#f56565',
        }});

        candleSeries.setData(chartData.candles);

        // Add price lines for entry, SL, TP
        candleSeries.createPriceLine({{
            price: trade.entry_price,
            color: '#667eea',
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: 'Entry',
        }});

        candleSeries.createPriceLine({{
            price: trade.sl_price,
            color: '#f56565',
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'SL',
        }});

        candleSeries.createPriceLine({{
            price: trade.tp_price,
            color: '#48bb78',
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'TP',
        }});

        // Add exit price line if exists
        if (trade.exit_price) {{
            candleSeries.createPriceLine({{
                price: trade.exit_price,
                color: '#ed8936',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: 'Exit',
            }});
        }}

        // Add volume if available
        if (chartData.candles.some(c => c.volume > 0)) {{
            const volumeSeries = chart.addHistogramSeries({{
                color: '#667eea',
                priceFormat: {{ type: 'volume' }},
                priceScaleId: '',
            }});
            volumeSeries.priceScale().applyOptions({{
                scaleMargins: {{ top: 0.8, bottom: 0 }},
            }});
            volumeSeries.setData(chartData.candles.map(c => ({{
                time: c.time,
                value: c.volume || 0,
                color: c.close >= c.open ? '#48bb78' : '#f56565',
            }})));
        }}

        // Add markers for entry and exit
        const markers = [];
        if (chartData.entryTime) {{
            markers.push({{
                time: chartData.entryTime,
                position: trade.direction === 'long' ? 'belowBar' : 'aboveBar',
                color: '#667eea',
                shape: trade.direction === 'long' ? 'arrowUp' : 'arrowDown',
                text: 'ENTRY',
            }});
        }}
        if (chartData.exitTime) {{
            markers.push({{
                time: chartData.exitTime,
                position: trade.direction === 'long' ? 'aboveBar' : 'belowBar',
                color: '#ed8936',
                shape: 'circle',
                text: 'EXIT',
            }});
        }}
        candleSeries.setMarkers(markers);

        chart.timeScale().fitContent();

        // Tab switching
        function switchTab(event, tabId) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }}
    </script>
</body>
</html>"""
        return html

    def _prepare_chart_data(self) -> dict[str, Any]:
        """Prepare data for the candlestick chart."""
        candles_data = []
        entry_time = None
        exit_time = None

        for candle in self.candles:
            # Convert timestamp to Unix timestamp for chart
            ts = candle["timestamp_dt"]
            unix_ts = int(ts.timestamp())

            candles_data.append({
                "time": unix_ts,
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle.get("volume", 0),
            })

            # Track entry and exit times
            entry_dt = self.trade["opened_at_dt"]
            exit_dt = self.trade.get("closed_at_dt")

            if ts == entry_dt or (entry_time is None and ts >= entry_dt):
                entry_time = unix_ts

            if exit_dt and (ts == exit_dt or (exit_time is None and ts >= exit_dt)):
                exit_time = unix_ts

        return {
            "candles": candles_data,
            "entryTime": entry_time,
            "exitTime": exit_time,
        }

    def _generate_issues_html(self, summary: dict[str, Any]) -> str:
        """Generate HTML for potential issues section."""
        issues = summary.get("potential_issues", [])
        if not issues:
            return ""

        issues_html = "".join(f'<span class="issue-badge">{issue}</span>' for issue in issues)
        return f"""
        <div class="section" style="border-left: 4px solid #f6ad55;">
            <h2 style="color: #f6ad55;">⚠️ Potential Issues Detected</h2>
            <div style="margin-top: 1rem;">
                {issues_html}
            </div>
        </div>
        """

    def _generate_features_table_html(self, features: dict[str, Any]) -> str:
        """Generate HTML table for features at entry."""
        if not features:
            return '<p style="color: #a0aec0;">No features data available</p>'

        key_features = [
            ("close", "Close Price"),
            ("vwap", "VWAP"),
            ("vwap_deviation", "VWAP Deviation %"),
            ("vwap_deviation_normalized", "VWAP Dev (ATR-norm)"),
            ("atr", "ATR"),
            ("rsi", "RSI"),
            ("ema_9", "EMA 9"),
            ("ema_20", "EMA 20"),
            ("ema_50", "EMA 50"),
            ("structure_label", "Structure Label"),
            ("structure_clarity", "Structure Clarity"),
            ("bos_direction", "BOS Direction"),
            ("bos_recent", "BOS Recent"),
            ("bos_age", "BOS Age"),
            ("choch_detected", "CHoCH Detected"),
            ("liquidity_sweep", "Liquidity Sweep"),
            ("bars_near_vwap", "Bars Near VWAP"),
            ("expansion_detected", "Expansion Detected"),
        ]

        rows = []
        for key, label in key_features:
            value = features.get(key)
            if value is not None:
                if isinstance(value, float):
                    value_str = f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"
                elif isinstance(value, bool):
                    value_str = "Yes" if value else "No"
                else:
                    value_str = str(value)
                rows.append(f"<tr><td>{label}</td><td><code>{value_str}</code></td></tr>")

        return f"""
        <table>
            <thead><tr><th>Metric</th><th>Value</th></tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
        """

    def _generate_htf_table_html(self, htf: dict[str, Any]) -> str:
        """Generate HTML table for HTF bias at entry."""
        if not htf:
            return '<p style="color: #a0aec0;">No HTF bias data available</p>'

        key_fields = [
            ("bias", "Bias"),
            ("score", "Score"),
            ("confidence", "Confidence"),
            ("structure_15m", "Structure 15m"),
            ("structure_1h", "Structure 1h"),
            ("dxy_aligned", "DXY Aligned"),
            ("chop_detected", "Chop Detected"),
            ("conflict_detected", "Conflict Detected"),
            ("bos_detected", "BOS Detected"),
            ("bars_since_bos", "Bars Since BOS"),
            ("structure_clarity", "Structure Clarity"),
            ("seasonality_adjustment", "Seasonality Adj"),
            ("seasonality_period", "Seasonality Period"),
            ("vwap_trend_confirmed", "VWAP Trend Confirmed"),
            ("dxy_corr_1h", "DXY Corr 1H"),
            ("dxy_corr_15m", "DXY Corr 15m"),
            ("dxy_structure", "DXY Structure"),
        ]

        rows = []
        for key, label in key_fields:
            value = htf.get(key)
            if value is not None:
                if isinstance(value, float):
                    value_str = f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"
                elif isinstance(value, bool):
                    value_str = "Yes" if value else "No"
                else:
                    value_str = str(value)
                rows.append(f"<tr><td>{label}</td><td><code>{value_str}</code></td></tr>")

        return f"""
        <table>
            <thead><tr><th>Metric</th><th>Value</th></tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
        """

    def _generate_signal_section_html(self, signal: dict[str, Any]) -> str:
        """Generate HTML for signal scoring section."""
        if not signal:
            return ""

        factor_scores = signal.get("factor_scores", {})
        diagnostics = signal.get("diagnostics", {})

        factor_rows = ""
        if factor_scores:
            for factor, score in sorted(factor_scores.items()):
                score_class = "positive" if score > 0 else "negative" if score < 0 else ""
                factor_rows += f"<tr><td>{factor}</td><td class='{score_class}'><code>{score}</code></td></tr>"

        diag_html = ""
        if diagnostics:
            diag_html = f"<pre>{json.dumps(diagnostics, indent=2)}</pre>"

        return f"""
        <div class="section">
            <h2>Signal Scoring</h2>
            <div class="grid">
                <div class="metric-card">
                    <div class="metric-label">Total Score</div>
                    <div class="metric-value">{signal.get('score', 'N/A')}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Confidence</div>
                    <div class="metric-value">{signal.get('confidence', 'N/A')}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Was Approved</div>
                    <div class="metric-value small">{'Yes' if signal.get('was_approved') else 'No'}</div>
                </div>
            </div>

            <h3>Factor Scores</h3>
            <table>
                <thead><tr><th>Factor</th><th>Score</th></tr></thead>
                <tbody>{factor_rows if factor_rows else '<tr><td colspan="2">No factor scores available</td></tr>'}</tbody>
            </table>

            {f'<h3>Diagnostics</h3>{diag_html}' if diag_html else ''}
        </div>
        """

    def _generate_candles_table_html(self) -> str:
        """Generate HTML table for all candles."""
        if not self.candles:
            return '<p style="color: #a0aec0;">No candle data available</p>'

        rows = []
        for candle in self.candles:
            position_class = ""
            if candle["position"] == "during_trade":
                position_class = 'style="background: #252d4a;"'

            rows.append(f"""
            <tr {position_class}>
                <td>{candle['timestamp'][:19]}</td>
                <td>{candle['position']}</td>
                <td>{candle['open']:.2f}</td>
                <td>{candle['high']:.2f}</td>
                <td>{candle['low']:.2f}</td>
                <td>{candle['close']:.2f}</td>
                <td>{candle.get('volume', 0):.0f}</td>
            </tr>
            """)

        return f"""
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Position</th>
                    <th>Open</th>
                    <th>High</th>
                    <th>Low</th>
                    <th>Close</th>
                    <th>Volume</th>
                </tr>
            </thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
        """

    def _generate_features_context_table_html(self) -> str:
        """Generate HTML table for features context."""
        if not self.features_context:
            return '<p style="color: #a0aec0;">No features context available</p>'

        # Show key columns only
        key_cols = ["timestamp", "position", "close", "vwap", "vwap_deviation_normalized", "rsi", "structure_label", "bos_recent"]

        rows = []
        for feat in self.features_context:
            position_class = ""
            if feat.get("position") == "during_trade":
                position_class = 'style="background: #252d4a;"'

            cells = []
            for col in key_cols:
                val = feat.get(col)
                if val is None:
                    cells.append("<td>-</td>")
                elif isinstance(val, float):
                    cells.append(f"<td>{val:.4f}</td>")
                elif col == "timestamp":
                    cells.append(f"<td>{str(val)[:19]}</td>")
                else:
                    cells.append(f"<td>{val}</td>")

            rows.append(f"<tr {position_class}>{''.join(cells)}</tr>")

        headers = "".join(f"<th>{col}</th>" for col in key_cols)
        return f"""
        <table>
            <thead><tr>{headers}</tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
        """

    def _generate_htf_context_table_html(self) -> str:
        """Generate HTML table for HTF bias context."""
        if not self.htf_bias_context:
            return '<p style="color: #a0aec0;">No HTF bias context available</p>'

        key_cols = ["timestamp", "position", "bias", "score", "confidence", "dxy_aligned", "chop_detected"]

        rows = []
        for htf in self.htf_bias_context:
            position_class = ""
            if htf.get("position") == "during_trade":
                position_class = 'style="background: #252d4a;"'

            cells = []
            for col in key_cols:
                val = htf.get(col)
                if val is None:
                    cells.append("<td>-</td>")
                elif isinstance(val, float):
                    cells.append(f"<td>{val:.2f}</td>")
                elif isinstance(val, bool):
                    cells.append(f"<td>{'Yes' if val else 'No'}</td>")
                elif col == "timestamp":
                    cells.append(f"<td>{str(val)[:19]}</td>")
                else:
                    cells.append(f"<td>{val}</td>")

            rows.append(f"<tr {position_class}>{''.join(cells)}</tr>")

        headers = "".join(f"<th>{col}</th>" for col in key_cols)
        return f"""
        <table>
            <thead><tr>{headers}</tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
        """


def print_trades_table(trades: list[dict[str, Any]]) -> None:
    """Print trades in a formatted table."""
    if not trades:
        print("No trades found in the specified date range.")
        return

    print("\n" + "=" * 120)
    print(f"{'ID':<40} {'Opened At':<20} {'Setup':<18} {'Dir':<6} {'Result':<6} {'P&L (R)':<10} {'Exit Reason':<15}")
    print("=" * 120)

    for t in trades:
        result_color = "\033[92m" if t["result"] == "WIN" else "\033[91m" if t["result"] == "LOSS" else "\033[93m"
        reset = "\033[0m"
        pnl_r = f"{t['pnl_r']:.2f}" if t["pnl_r"] else "N/A"
        print(
            f"{t['id']:<40} "
            f"{t['opened_at'][:19]:<20} "
            f"{t['setup_type']:<18} "
            f"{t['direction']:<6} "
            f"{result_color}{t['result']:<6}{reset} "
            f"{pnl_r:<10} "
            f"{t['exit_reason'] or 'N/A':<15}"
        )

    print("=" * 120)
    print(f"\nTotal: {len(trades)} trades")
    print("\nTo generate a diagnostic report, run:")
    print("  python scripts/generate_trade_diagnostic.py --trade-id <ID> --output reports/trade_diagnostic\n")


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate trade diagnostic report")
    parser.add_argument(
        "--trade-id",
        type=str,
        nargs="*",
        help="Trade UUID(s) to diagnose (space-separated for multiple)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output path (without extension). For multiple trades, files are numbered: output_001.html, etc.",
    )
    parser.add_argument(
        "--list-trades",
        action="store_true",
        help="List trades in date range",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD) for listing trades",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD) for listing trades",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum trades to list (default: 50)",
    )

    args = parser.parse_args()

    # Connect to database
    db_pool = DatabasePool(
        dsn="postgresql://scp:scp_dev_password@localhost:5432/scp",
        min_size=1,
        max_size=5,
    )
    await db_pool.connect()

    try:
        generator = TradeDiagnosticGenerator(db_pool)

        if args.list_trades:
            # List trades mode
            if not args.start or not args.end:
                print("Error: --start and --end dates required for --list-trades")
                return

            start_date = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
            end_date = datetime.fromisoformat(args.end).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

            trades = await generator.list_trades(start_date, end_date, args.limit)
            print_trades_table(trades)

        elif args.trade_id:
            # Generate report mode
            if not args.output:
                print("Error: --output path required for report generation")
                return

            trade_ids = args.trade_id
            total = len(trade_ids)

            if total == 1:
                # Single trade - use output path directly
                await generator.generate_report(trade_ids[0], Path(args.output))
            else:
                # Multiple trades - number the output files
                print(f"\nGenerating reports for {total} trades...\n")
                success_count = 0
                failed_ids = []

                for i, trade_id in enumerate(trade_ids, 1):
                    output_path = Path(f"{args.output}_{i:03d}")
                    try:
                        print(f"[{i}/{total}] Processing trade {trade_id[:8]}...")
                        # Reset generator state for each trade
                        generator.trade = {}
                        generator.candles = []
                        generator.features_at_entry = {}
                        generator.features_context = []
                        generator.htf_bias_at_entry = {}
                        generator.htf_bias_context = []
                        generator.signal_history = {}

                        await generator.generate_report(trade_id, output_path)
                        success_count += 1
                    except Exception as e:
                        print(f"  ERROR: {e}")
                        failed_ids.append(trade_id)

                print(f"\n{'=' * 60}")
                print(f"Completed: {success_count}/{total} reports generated")
                if failed_ids:
                    print(f"Failed trades: {', '.join(failed_ids)}")
                print(f"Output directory: {Path(args.output).parent}")

        else:
            parser.print_help()

    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
