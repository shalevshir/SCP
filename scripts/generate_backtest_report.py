#!/usr/bin/env env python3
"""Generate comprehensive backtest diagnostics report in HTML and JSON formats.

Usage:
    python scripts/generate_backtest_report.py --start 2025-11-01 --end 2025-11-30 --output reports/backtest_2025_11
"""

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
from scp_shared.common import get_logger
from scp_shared.database import DatabasePool
from scp_shared.rule_engine import load_scoring_config

logger = get_logger(__name__)


class BacktestReportGenerator:
    """Generate comprehensive backtest diagnostics reports."""

    def __init__(self, db_pool: DatabasePool):
        self.db_pool = db_pool
        self.data: dict[str, Any] = {}
        # Load scoring config for dynamic thresholds
        self.scoring_config = load_scoring_config()
        self.setup_thresholds = {
            setup: config.get("min_score", 8.0)
            for setup, config in self.scoring_config.setup_types.items()
        }
        self.global_a_plus_threshold = self.scoring_config.confidence.get("a_plus", 8.0)

    async def generate_report(
        self,
        start_date: datetime,
        end_date: datetime,
        output_path: Path,
    ) -> None:
        """Generate complete backtest report.

        Args:
            start_date: Start of backtest period
            end_date: End of backtest period
            output_path: Output directory path (without extension)
        """
        logger.info(f"Generating backtest report for {start_date} to {end_date}")

        # Collect all data
        await self._collect_metadata(start_date, end_date)
        await self._collect_trades()
        await self._collect_signal_history()
        await self._analyze_performance()
        await self._analyze_rejections()
        await self._analyze_by_setup()
        await self._analyze_by_time()
        await self._analyze_risk()
        await self._generate_recommendations()

        # Generate outputs
        json_path = Path(f"{output_path}.json")
        html_path = Path(f"{output_path}.html")

        self._write_json_report(json_path)
        self._write_html_report(html_path)

        logger.info(f"Reports generated:")
        logger.info(f"  JSON: {json_path}")
        logger.info(f"  HTML: {html_path}")

    async def _collect_metadata(self, start_date: datetime, end_date: datetime) -> None:
        """Collect backtest metadata."""
        self.data["metadata"] = {
            "backtest_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "duration_days": (end_date - start_date).days,
            },
            "generated_at": datetime.now().isoformat(),
            "report_version": "1.0.0",
        }

    async def _collect_trades(self) -> None:
        """Collect all executed trades with full context."""
        start_date = datetime.fromisoformat(self.data["metadata"]["backtest_period"]["start"])
        end_date = datetime.fromisoformat(self.data["metadata"]["backtest_period"]["end"])

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    t.id,
                    t.opened_at as timestamp,
                    'GC' as symbol,
                    t.direction,
                    t.setup_type,
                    t.entry_price,
                    t.sl_price as stop_loss,
                    t.tp_price as take_profit_1,
                    NULL as take_profit_2,
                    t.state as status,
                    t.exit_price,
                    t.closed_at as exit_timestamp,
                    t.exit_reason,
                    t.pnl_dollars as pnl_usd,
                    t.r_multiple as pnl_r,
                    NULL as signal_score,
                    NULL as htf_bias,
                    NULL as htf_score,
                    NULL as notes,
                    t.created_at,
                    t.confirmations as metadata
                FROM trades t
                WHERE t.opened_at >= $1 AND t.opened_at <= $2
                ORDER BY t.opened_at ASC
                """,
                start_date,
                end_date,
            )

            trades = []
            for row in rows:
                trade = {
                    "id": str(row["id"]),
                    "timestamp": row["timestamp"].isoformat(),
                    "symbol": row["symbol"],
                    "direction": row["direction"],
                    "setup_type": row["setup_type"],
                    "entry_price": float(row["entry_price"]),
                    "stop_loss": float(row["stop_loss"]),
                    "take_profit_1": float(row["take_profit_1"]) if row["take_profit_1"] else None,
                    "take_profit_2": float(row["take_profit_2"]) if row["take_profit_2"] else None,
                    "status": row["status"],
                    "exit_price": float(row["exit_price"]) if row["exit_price"] else None,
                    "exit_timestamp": row["exit_timestamp"].isoformat() if row["exit_timestamp"] else None,
                    "exit_reason": row["exit_reason"],
                    "pnl_usd": float(row["pnl_usd"]) if row["pnl_usd"] else None,
                    "pnl_r": float(row["pnl_r"]) if row["pnl_r"] else None,
                    "signal_score": float(row["signal_score"]) if row["signal_score"] else None,
                    "htf_bias": row["htf_bias"],
                    "htf_score": float(row["htf_score"]) if row["htf_score"] else None,
                    "notes": row["notes"],
                    "metadata": row["metadata"],
                    # Derive session from timestamp
                    "session": self._get_session(row["timestamp"]),
                    # Calculate trade duration
                    "duration_minutes": (
                        (row["exit_timestamp"] - row["timestamp"]).total_seconds() / 60
                        if row["exit_timestamp"]
                        else None
                    ),
                }
                trades.append(trade)

            self.data["trades"] = trades
            self.data["metadata"]["total_trades"] = len(trades)

    async def _collect_signal_history(self) -> None:
        """Collect all signals (approved and rejected) for rejection analysis."""
        start_date = datetime.fromisoformat(self.data["metadata"]["backtest_period"]["start"])
        end_date = datetime.fromisoformat(self.data["metadata"]["backtest_period"]["end"])

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
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
                    signal_message_id,
                    trade_id,
                    features_snapshot,
                    htf_bias_snapshot,
                    factor_scores,
                    diagnostics,
                    created_at
                FROM signal_history
                WHERE timestamp >= $1 AND timestamp <= $2
                ORDER BY timestamp ASC
                """,
                start_date,
                end_date,
            )

            signals = []
            for row in rows:
                # Parse JSONB fields (may be dict or string)
                htf_bias_snapshot = row["htf_bias_snapshot"]
                if isinstance(htf_bias_snapshot, str):
                    htf_bias_snapshot = json.loads(htf_bias_snapshot) if htf_bias_snapshot else {}

                factor_scores = row["factor_scores"]
                if isinstance(factor_scores, str):
                    factor_scores = json.loads(factor_scores) if factor_scores else {}

                diagnostics = row["diagnostics"]
                if isinstance(diagnostics, str):
                    diagnostics = json.loads(diagnostics) if diagnostics else {}

                signal = {
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
                    "signal_message_id": str(row["signal_message_id"]) if row["signal_message_id"] else None,
                    "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
                    "session": self._get_session(row["timestamp"]),
                    # Extract key data from snapshots
                    "htf_bias": htf_bias_snapshot.get("bias") if htf_bias_snapshot else None,
                    "htf_score": htf_bias_snapshot.get("score") if htf_bias_snapshot else None,
                    "factor_scores": factor_scores,
                    "diagnostics": diagnostics,
                }
                signals.append(signal)

            self.data["signals"] = signals
            self.data["metadata"]["total_signals"] = len(signals)
            self.data["metadata"]["approved_signals"] = sum(1 for s in signals if s["was_approved"])
            self.data["metadata"]["rejected_signals"] = sum(1 for s in signals if not s["was_approved"])

    async def _analyze_performance(self) -> None:
        """Analyze overall performance metrics."""
        trades = self.data["trades"]
        closed_trades = [t for t in trades if t["status"] in ("CLOSED", "closed", "stopped_out", "INVALIDATED")]

        if not closed_trades:
            self.data["performance"] = {"error": "No closed trades found"}
            return

        total_pnl_r = sum(t["pnl_r"] for t in closed_trades if t["pnl_r"] is not None)
        wins = [t for t in closed_trades if t["pnl_r"] and t["pnl_r"] > 0]
        losses = [t for t in closed_trades if t["pnl_r"] and t["pnl_r"] <= 0]

        win_rate = len(wins) / len(closed_trades) if closed_trades else 0
        avg_win = sum(t["pnl_r"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl_r"] for t in losses) / len(losses) if losses else 0
        expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        # Calculate drawdown
        cumulative_r = 0
        peak = 0
        max_drawdown = 0
        for trade in closed_trades:
            if trade["pnl_r"] is not None:
                cumulative_r += trade["pnl_r"]
                if cumulative_r > peak:
                    peak = cumulative_r
                drawdown = peak - cumulative_r
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        # Longest losing streak
        current_streak = 0
        max_losing_streak = 0
        for trade in closed_trades:
            if trade["pnl_r"] and trade["pnl_r"] <= 0:
                current_streak += 1
                max_losing_streak = max(max_losing_streak, current_streak)
            else:
                current_streak = 0

        self.data["performance"] = {
            "total_trades": len(closed_trades),
            "total_pnl_r": round(total_pnl_r, 2),
            "win_rate": round(win_rate * 100, 1),
            "total_wins": len(wins),
            "total_losses": len(losses),
            "avg_win_r": round(avg_win, 2),
            "avg_loss_r": round(avg_loss, 2),
            "expectancy_r": round(expectancy, 3),
            "max_drawdown_r": round(max_drawdown, 2),
            "longest_losing_streak": max_losing_streak,
            "profit_factor": round(abs(sum(t["pnl_r"] for t in wins) / sum(t["pnl_r"] for t in losses)), 2) if losses and sum(t["pnl_r"] for t in losses) != 0 else 0,
        }

    async def _analyze_rejections(self) -> None:
        """Analyze rejected signals to identify systematic false negatives."""
        signals = self.data["signals"]
        rejected = [s for s in signals if not s["was_approved"]]

        # Group by rejection stage
        by_stage = defaultdict(list)
        for signal in rejected:
            stage = signal["rejection_stage"] or "unknown"
            by_stage[stage].append(signal)

        # Near-miss analysis (score just below threshold)
        # Use per-setup thresholds from config
        near_misses = []
        for s in rejected:
            if s["rejection_stage"] != "confidence_filter":
                continue
            setup_type = s["setup_type"]
            threshold = self.setup_thresholds.get(setup_type, self.global_a_plus_threshold)
            # Near-miss: within 1.0 point of the setup's threshold
            if s["score"] >= (threshold - 1.0) and s["score"] < threshold:
                near_misses.append({
                    **s,
                    "threshold": threshold,
                    "distance_to_threshold": round(threshold - s["score"], 2),
                })

        rejection_analysis = {
            "total_rejected": len(rejected),
            "by_stage": {
                stage: {
                    "count": len(sigs),
                    "percentage": round(len(sigs) / len(rejected) * 100, 1) if rejected else 0,
                }
                for stage, sigs in by_stage.items()
            },
            "setup_thresholds": self.setup_thresholds,  # Include thresholds in report
            "near_misses": {
                "count": len(near_misses),
                "avg_score": round(sum(s["score"] for s in near_misses) / len(near_misses), 2) if near_misses else 0,
                "signals": [
                    {
                        "timestamp": s["timestamp"],
                        "setup_type": s["setup_type"],
                        "score": s["score"],
                        "threshold": s["threshold"],
                        "distance_to_threshold": s["distance_to_threshold"],
                    }
                    for s in near_misses[:20]  # Limit to 20 for brevity
                ],
            },
        }

        self.data["rejection_analysis"] = rejection_analysis

    async def _analyze_by_setup(self) -> None:
        """Analyze performance breakdown by setup type."""
        trades = self.data["trades"]
        closed_trades = [t for t in trades if t["status"] in ("CLOSED", "closed", "stopped_out", "INVALIDATED")]

        by_setup = defaultdict(list)
        for trade in closed_trades:
            by_setup[trade["setup_type"]].append(trade)

        setup_analysis = {}
        for setup_type, setup_trades in by_setup.items():
            wins = [t for t in setup_trades if t["pnl_r"] and t["pnl_r"] > 0]
            losses = [t for t in setup_trades if t["pnl_r"] and t["pnl_r"] <= 0]
            total_pnl = sum(t["pnl_r"] for t in setup_trades if t["pnl_r"] is not None)
            win_rate = len(wins) / len(setup_trades) if setup_trades else 0
            avg_r = total_pnl / len(setup_trades) if setup_trades else 0

            avg_duration = sum(t["duration_minutes"] for t in setup_trades if t["duration_minutes"]) / len([t for t in setup_trades if t["duration_minutes"]]) if setup_trades else 0

            setup_analysis[setup_type] = {
                "trade_count": len(setup_trades),
                "win_rate": round(win_rate * 100, 1),
                "total_pnl_r": round(total_pnl, 2),
                "avg_r": round(avg_r, 3),
                "expectancy": round(avg_r, 3),  # Same as avg_r for closed trades
                "wins": len(wins),
                "losses": len(losses),
                "avg_duration_minutes": round(avg_duration, 1),
            }

        # Sort by expectancy (descending)
        setup_analysis = dict(sorted(setup_analysis.items(), key=lambda x: x[1]["expectancy"], reverse=True))
        self.data["setup_analysis"] = setup_analysis

    async def _analyze_by_time(self) -> None:
        """Analyze performance by time periods (session, hour, day of week)."""
        trades = self.data["trades"]
        closed_trades = [t for t in trades if t["status"] in ("CLOSED", "closed", "stopped_out", "INVALIDATED")]

        # By session
        by_session = defaultdict(list)
        for trade in closed_trades:
            by_session[trade["session"]].append(trade)

        session_analysis = {}
        for session, session_trades in by_session.items():
            total_pnl = sum(t["pnl_r"] for t in session_trades if t["pnl_r"] is not None)
            wins = len([t for t in session_trades if t["pnl_r"] and t["pnl_r"] > 0])
            session_analysis[session] = {
                "trade_count": len(session_trades),
                "win_rate": round(wins / len(session_trades) * 100, 1) if session_trades else 0,
                "total_pnl_r": round(total_pnl, 2),
                "avg_r": round(total_pnl / len(session_trades), 3) if session_trades else 0,
            }

        # By hour of day
        by_hour = defaultdict(list)
        for trade in closed_trades:
            hour = datetime.fromisoformat(trade["timestamp"]).hour
            by_hour[hour].append(trade)

        hour_analysis = {}
        for hour, hour_trades in sorted(by_hour.items()):
            total_pnl = sum(t["pnl_r"] for t in hour_trades if t["pnl_r"] is not None)
            hour_analysis[hour] = {
                "trade_count": len(hour_trades),
                "total_pnl_r": round(total_pnl, 2),
                "avg_r": round(total_pnl / len(hour_trades), 3) if hour_trades else 0,
            }

        # By day of week
        by_dow = defaultdict(list)
        for trade in closed_trades:
            dow = datetime.fromisoformat(trade["timestamp"]).strftime("%A")
            by_dow[dow].append(trade)

        dow_analysis = {}
        for dow, dow_trades in by_dow.items():
            total_pnl = sum(t["pnl_r"] for t in dow_trades if t["pnl_r"] is not None)
            dow_analysis[dow] = {
                "trade_count": len(dow_trades),
                "total_pnl_r": round(total_pnl, 2),
                "avg_r": round(total_pnl / len(dow_trades), 3) if dow_trades else 0,
            }

        self.data["time_analysis"] = {
            "by_session": session_analysis,
            "by_hour": hour_analysis,
            "by_day_of_week": dow_analysis,
        }

    async def _analyze_risk(self) -> None:
        """Analyze risk metrics and drawdown characteristics."""
        trades = self.data["trades"]
        closed_trades = [t for t in trades if t["status"] in ("CLOSED", "closed", "stopped_out", "INVALIDATED")]

        if not closed_trades:
            self.data["risk_analysis"] = {"error": "No closed trades"}
            return

        # Consecutive losses
        consecutive_losses = []
        current_streak = 0
        for trade in closed_trades:
            if trade["pnl_r"] and trade["pnl_r"] <= 0:
                current_streak += 1
            else:
                if current_streak > 0:
                    consecutive_losses.append(current_streak)
                current_streak = 0
        if current_streak > 0:
            consecutive_losses.append(current_streak)

        # Recovery time analysis (simplified - time to reach new equity high)
        cumulative_r = 0
        peak = 0
        in_drawdown = False
        drawdown_start = None
        recovery_times = []

        for i, trade in enumerate(closed_trades):
            if trade["pnl_r"] is not None:
                cumulative_r += trade["pnl_r"]
                if cumulative_r > peak:
                    if in_drawdown and drawdown_start is not None:
                        # Recovered
                        recovery_times.append(i - drawdown_start)
                        in_drawdown = False
                    peak = cumulative_r
                else:
                    if not in_drawdown:
                        drawdown_start = i
                        in_drawdown = True

        self.data["risk_analysis"] = {
            "max_consecutive_losses": max(consecutive_losses) if consecutive_losses else 0,
            "avg_losing_streak": round(sum(consecutive_losses) / len(consecutive_losses), 1) if consecutive_losses else 0,
            "total_losing_streaks": len(consecutive_losses),
            "avg_recovery_trades": round(sum(recovery_times) / len(recovery_times), 1) if recovery_times else 0,
            "max_recovery_trades": max(recovery_times) if recovery_times else 0,
        }

    async def _generate_recommendations(self) -> None:
        """Generate actionable recommendations based on analysis."""
        recommendations = []

        # Check setup performance
        setup_analysis = self.data.get("setup_analysis", {})
        for setup_type, stats in setup_analysis.items():
            if stats["expectancy"] < 0:
                recommendations.append({
                    "priority": "HIGH",
                    "category": "Setup Performance",
                    "action": f"DISABLE {setup_type}",
                    "reason": f"Negative expectancy ({stats['expectancy']}R) over {stats['trade_count']} trades",
                })
            elif stats["win_rate"] < 35:
                recommendations.append({
                    "priority": "MEDIUM",
                    "category": "Setup Performance",
                    "action": f"Review {setup_type}",
                    "reason": f"Low win rate ({stats['win_rate']}%) - check if stops are too tight",
                })

        # Check time-based performance
        time_analysis = self.data.get("time_analysis", {})
        for session, stats in time_analysis.get("by_session", {}).items():
            if stats["avg_r"] < -0.2 and stats["trade_count"] >= 3:
                recommendations.append({
                    "priority": "MEDIUM",
                    "category": "Time-Based",
                    "action": f"Reduce/disable {session} session trading",
                    "reason": f"Negative expectancy ({stats['avg_r']}R) over {stats['trade_count']} trades",
                })

        # Check rejection patterns
        rejection_analysis = self.data.get("rejection_analysis", {})
        near_misses = rejection_analysis.get("near_misses", {}).get("count", 0)
        if near_misses > 10:
            # Show actual thresholds from config
            threshold_summary = ", ".join(
                f"{setup}: {thresh}" for setup, thresh in self.setup_thresholds.items()
            )
            recommendations.append({
                "priority": "LOW",
                "category": "Threshold Analysis",
                "action": "Review setup thresholds",
                "reason": f"{near_misses} signals scored just below their thresholds ({threshold_summary}) - investigate if these would have been profitable",
            })

        # Check risk metrics
        risk_analysis = self.data.get("risk_analysis", {})
        max_streak = risk_analysis.get("max_consecutive_losses", 0)
        if max_streak >= 5:
            recommendations.append({
                "priority": "HIGH",
                "category": "Risk Management",
                "action": "Review position sizing",
                "reason": f"Max consecutive losses: {max_streak} - ensure psychological survivability",
            })

        # Sort by priority
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))

        self.data["recommendations"] = recommendations

    def _get_session(self, timestamp: datetime) -> str:
        """Determine trading session from timestamp.

        Args:
            timestamp: Trade timestamp

        Returns:
            Session name (Asia, London, NY, or Off-Hours)
        """
        hour = timestamp.hour

        # Times in UTC (approximate)
        if 0 <= hour < 7:  # 8 PM - 3 AM ET
            return "Asia"
        elif 7 <= hour < 12:  # 3 AM - 8 AM ET
            return "London"
        elif 12 <= hour < 20:  # 8 AM - 4 PM ET
            return "NY"
        else:
            return "Off-Hours"

    def _write_json_report(self, output_path: Path) -> None:
        """Write JSON report."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(self.data, f, indent=2, default=str)

        logger.info(f"JSON report written to {output_path}")

    def _write_html_report(self, output_path: Path) -> None:
        """Write interactive HTML report."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html = self._generate_html()

        with open(output_path, "w") as f:
            f.write(html)

        logger.info(f"HTML report written to {output_path}")

    def _generate_html(self) -> str:
        """Generate HTML report content."""
        metadata = self.data.get("metadata", {})
        performance = self.data.get("performance", {})
        setup_analysis = self.data.get("setup_analysis", {})
        time_analysis = self.data.get("time_analysis", {})
        risk_analysis = self.data.get("risk_analysis", {})
        rejection_analysis = self.data.get("rejection_analysis", {})
        recommendations = self.data.get("recommendations", [])

        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Diagnostics Report - {metadata.get('backtest_period', {}).get('start', 'N/A')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #0a0e27;
            color: #e0e6ed;
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        h2 {{
            font-size: 1.8rem;
            margin: 2rem 0 1rem;
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 0.5rem;
        }}
        h3 {{
            font-size: 1.3rem;
            margin: 1.5rem 0 0.75rem;
            color: #a0aec0;
        }}
        .subtitle {{
            color: #a0aec0;
            font-size: 1.1rem;
            margin-bottom: 2rem;
        }}
        .section {{
            background: #161b33;
            border-radius: 12px;
            padding: 2rem;
            margin: 2rem 0;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1.5rem;
            margin: 1.5rem 0;
        }}
        .metric-card {{
            background: #1e2541;
            border-radius: 8px;
            padding: 1.5rem;
            border-left: 4px solid #667eea;
        }}
        .metric-label {{
            color: #a0aec0;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
        }}
        .metric-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #e0e6ed;
        }}
        .metric-value.positive {{ color: #48bb78; }}
        .metric-value.negative {{ color: #f56565; }}
        .metric-value.neutral {{ color: #ed8936; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1.5rem 0;
            background: #1e2541;
            border-radius: 8px;
            overflow: hidden;
        }}
        th {{
            background: #252d4a;
            color: #a0aec0;
            text-align: left;
            padding: 1rem;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }}
        td {{
            padding: 1rem;
            border-top: 1px solid #2d3748;
        }}
        tr:hover {{ background: #252d4a; }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: 600;
        }}
        .badge-high {{ background: #fc8181; color: #1a202c; }}
        .badge-medium {{ background: #f6ad55; color: #1a202c; }}
        .badge-low {{ background: #68d391; color: #1a202c; }}
        .recommendation {{
            background: #1e2541;
            border-left: 4px solid #f6ad55;
            padding: 1rem;
            margin: 1rem 0;
            border-radius: 4px;
        }}
        .recommendation.high {{ border-left-color: #fc8181; }}
        .recommendation.medium {{ border-left-color: #f6ad55; }}
        .recommendation.low {{ border-left-color: #68d391; }}
        .footer {{
            text-align: center;
            color: #718096;
            margin-top: 3rem;
            padding-top: 2rem;
            border-top: 1px solid #2d3748;
        }}
        code {{
            background: #2d3748;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 Backtest Diagnostics Report</h1>
        <p class="subtitle">
            Period: {metadata.get('backtest_period', {}).get('start', 'N/A')} → {metadata.get('backtest_period', {}).get('end', 'N/A')}
            ({metadata.get('backtest_period', {}).get('duration_days', 0)} days)
        </p>

        <!-- Executive Summary -->
        <div class="section">
            <h2>📊 Executive Summary</h2>
            <div class="grid">
                <div class="metric-card">
                    <div class="metric-label">Total Trades</div>
                    <div class="metric-value">{performance.get('total_trades', 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Expectancy (R)</div>
                    <div class="metric-value {'positive' if performance.get('expectancy_r', 0) > 0 else 'negative'}">{performance.get('expectancy_r', 0):.3f}R</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value">{performance.get('win_rate', 0):.1f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Total P&L (R)</div>
                    <div class="metric-value {'positive' if performance.get('total_pnl_r', 0) > 0 else 'negative'}">{performance.get('total_pnl_r', 0):.2f}R</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Max Drawdown (R)</div>
                    <div class="metric-value negative">{performance.get('max_drawdown_r', 0):.2f}R</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Longest Losing Streak</div>
                    <div class="metric-value neutral">{performance.get('longest_losing_streak', 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Profit Factor</div>
                    <div class="metric-value {'positive' if performance.get('profit_factor', 0) > 1 else 'negative'}">{performance.get('profit_factor', 0):.2f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg Win / Avg Loss</div>
                    <div class="metric-value">{performance.get('avg_win_r', 0):.2f}R / {performance.get('avg_loss_r', 0):.2f}R</div>
                </div>
            </div>
        </div>

        <!-- Recommendations -->
        <div class="section">
            <h2>💡 Actionable Recommendations</h2>
            {self._generate_recommendations_html(recommendations)}
        </div>

        <!-- Performance by Setup -->
        <div class="section">
            <h2>🎯 Performance by Setup Type</h2>
            <table>
                <thead>
                    <tr>
                        <th>Setup Type</th>
                        <th>Trades</th>
                        <th>Win Rate</th>
                        <th>Total P&L (R)</th>
                        <th>Expectancy (R)</th>
                        <th>Avg Duration</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_setup_table_rows(setup_analysis)}
                </tbody>
            </table>
        </div>

        <!-- Time-Based Analysis -->
        <div class="section">
            <h2>⏰ Time-Based Performance</h2>

            <h3>By Session</h3>
            <table>
                <thead>
                    <tr>
                        <th>Session</th>
                        <th>Trades</th>
                        <th>Win Rate</th>
                        <th>Total P&L (R)</th>
                        <th>Avg (R)</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_session_table_rows(time_analysis.get('by_session', {}))}
                </tbody>
            </table>

            <h3>By Hour (UTC)</h3>
            <table>
                <thead>
                    <tr>
                        <th>Hour</th>
                        <th>Trades</th>
                        <th>Total P&L (R)</th>
                        <th>Avg (R)</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_hour_table_rows(time_analysis.get('by_hour', {}))}
                </tbody>
            </table>
        </div>

        <!-- Risk Analysis -->
        <div class="section">
            <h2>⚠️ Risk & Drawdown Analysis</h2>
            <div class="grid">
                <div class="metric-card">
                    <div class="metric-label">Max Consecutive Losses</div>
                    <div class="metric-value neutral">{risk_analysis.get('max_consecutive_losses', 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg Losing Streak</div>
                    <div class="metric-value">{risk_analysis.get('avg_losing_streak', 0):.1f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Total Losing Streaks</div>
                    <div class="metric-value">{risk_analysis.get('total_losing_streaks', 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Avg Recovery Time</div>
                    <div class="metric-value">{risk_analysis.get('avg_recovery_trades', 0):.1f} trades</div>
                </div>
            </div>
        </div>

        <!-- Rejection Analysis -->
        <div class="section">
            <h2>🚫 Rejection Analysis</h2>
            <div class="grid">
                <div class="metric-card">
                    <div class="metric-label">Total Signals</div>
                    <div class="metric-value">{metadata.get('total_signals', 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Approved</div>
                    <div class="metric-value positive">{metadata.get('approved_signals', 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Rejected</div>
                    <div class="metric-value negative">{metadata.get('rejected_signals', 0)}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Approval Rate</div>
                    <div class="metric-value">{(metadata.get('approved_signals', 0) / max(metadata.get('total_signals', 0), 1) * 100):.1f}%</div>
                </div>
            </div>

            <h3>Rejections by Stage</h3>
            <table>
                <thead>
                    <tr>
                        <th>Stage</th>
                        <th>Count</th>
                        <th>Percentage</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_rejection_table_rows(rejection_analysis.get('by_stage', {}))}
                </tbody>
            </table>

            <h3>Setup Thresholds (from config)</h3>
            {self._generate_threshold_table_html(rejection_analysis.get('setup_thresholds', {}))}

            <h3>Near-Miss Analysis (within 1.0 of threshold)</h3>
            <p style="margin: 1rem 0;">
                <strong>{rejection_analysis.get('near_misses', {}).get('count', 0)}</strong> signals scored just below their setup's threshold.
                Average score: <strong>{rejection_analysis.get('near_misses', {}).get('avg_score', 0):.2f}</strong>
            </p>
            {self._generate_near_miss_table_html(rejection_analysis.get('near_misses', {}))}
            <p style="color: #a0aec0; font-size: 0.9rem; margin-top: 1rem;">
                💡 Review these signals to determine if the threshold is too strict or if they genuinely lack edge.
            </p>
        </div>

        <div class="footer">
            <p>Generated at {metadata.get('generated_at', 'N/A')}</p>
            <p>Report Version {metadata.get('report_version', '1.0.0')}</p>
        </div>
    </div>
</body>
</html>"""
        return html

    def _generate_recommendations_html(self, recommendations: list[dict]) -> str:
        """Generate HTML for recommendations section."""
        if not recommendations:
            return '<p style="color: #68d391;">✅ No critical issues detected. System performance is acceptable.</p>'

        html_parts = []
        for rec in recommendations:
            priority = rec["priority"].lower()
            html_parts.append(f"""
            <div class="recommendation {priority}">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <strong>{rec['action']}</strong>
                    <span class="badge badge-{priority}">{rec['priority']}</span>
                </div>
                <div style="color: #a0aec0; font-size: 0.9rem;">
                    <strong>{rec['category']}:</strong> {rec['reason']}
                </div>
            </div>
            """)
        return "\n".join(html_parts)

    def _generate_setup_table_rows(self, setup_analysis: dict) -> str:
        """Generate HTML table rows for setup analysis."""
        rows = []
        for setup_type, stats in setup_analysis.items():
            expectancy_class = "positive" if stats["expectancy"] > 0 else "negative"
            rows.append(f"""
            <tr>
                <td><code>{setup_type}</code></td>
                <td>{stats['trade_count']}</td>
                <td>{stats['win_rate']}%</td>
                <td class="{expectancy_class}">{stats['total_pnl_r']:.2f}R</td>
                <td class="{expectancy_class}"><strong>{stats['expectancy']:.3f}R</strong></td>
                <td>{stats['avg_duration_minutes']:.0f} min</td>
            </tr>
            """)
        return "\n".join(rows) if rows else '<tr><td colspan="6">No data</td></tr>'

    def _generate_session_table_rows(self, session_analysis: dict) -> str:
        """Generate HTML table rows for session analysis."""
        rows = []
        for session, stats in session_analysis.items():
            pnl_class = "positive" if stats["avg_r"] > 0 else "negative"
            rows.append(f"""
            <tr>
                <td><strong>{session}</strong></td>
                <td>{stats['trade_count']}</td>
                <td>{stats['win_rate']}%</td>
                <td class="{pnl_class}">{stats['total_pnl_r']:.2f}R</td>
                <td class="{pnl_class}"><strong>{stats['avg_r']:.3f}R</strong></td>
            </tr>
            """)
        return "\n".join(rows) if rows else '<tr><td colspan="5">No data</td></tr>'

    def _generate_hour_table_rows(self, hour_analysis: dict) -> str:
        """Generate HTML table rows for hourly analysis."""
        rows = []
        for hour, stats in sorted(hour_analysis.items()):
            pnl_class = "positive" if stats["avg_r"] > 0 else "negative"
            rows.append(f"""
            <tr>
                <td>{hour:02d}:00</td>
                <td>{stats['trade_count']}</td>
                <td class="{pnl_class}">{stats['total_pnl_r']:.2f}R</td>
                <td class="{pnl_class}"><strong>{stats['avg_r']:.3f}R</strong></td>
            </tr>
            """)
        return "\n".join(rows) if rows else '<tr><td colspan="4">No data</td></tr>'

    def _generate_rejection_table_rows(self, by_stage: dict) -> str:
        """Generate HTML table rows for rejection analysis."""
        rows = []
        for stage, stats in sorted(by_stage.items(), key=lambda x: x[1]["count"], reverse=True):
            rows.append(f"""
            <tr>
                <td><code>{stage}</code></td>
                <td>{stats['count']}</td>
                <td>{stats['percentage']:.1f}%</td>
            </tr>
            """)
        return "\n".join(rows) if rows else '<tr><td colspan="3">No data</td></tr>'

    def _generate_threshold_table_html(self, setup_thresholds: dict) -> str:
        """Generate HTML table showing per-setup thresholds."""
        if not setup_thresholds:
            return '<p style="color: #a0aec0; margin: 1rem 0;">No threshold data available.</p>'

        rows = []
        for setup, threshold in sorted(setup_thresholds.items()):
            rows.append(f"""
            <tr>
                <td><code>{setup}</code></td>
                <td><strong>{threshold}</strong></td>
            </tr>
            """)

        return f"""
        <table style="margin-top: 1rem; max-width: 400px;">
            <thead>
                <tr>
                    <th>Setup Type</th>
                    <th>Min Score</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
        """

    def _generate_near_miss_table_html(self, near_misses: dict) -> str:
        """Generate HTML table for near-miss signals."""
        signals = near_misses.get('signals', [])

        if not signals:
            return '<p style="color: #a0aec0; margin: 1rem 0;">No near-miss signals found.</p>'

        rows = []
        for signal in signals:
            timestamp = datetime.fromisoformat(signal['timestamp']).strftime('%Y-%m-%d %H:%M')
            score = signal['score']
            distance = signal['distance_to_threshold']
            setup = signal['setup_type']
            threshold = signal.get('threshold', 8.0)

            # Color code based on how close to threshold
            if distance <= 0.1:
                score_class = 'style="color: #f6ad55;"'  # Very close
            elif distance <= 0.3:
                score_class = 'style="color: #ed8936;"'  # Close
            else:
                score_class = 'style="color: #a0aec0;"'  # Further

            rows.append(f"""
            <tr>
                <td>{timestamp}</td>
                <td><code>{setup}</code></td>
                <td {score_class}><strong>{score:.2f}</strong></td>
                <td>{threshold}</td>
                <td>-{distance:.2f}</td>
            </tr>
            """)

        return f"""
        <table style="margin-top: 1rem;">
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Setup Type</th>
                    <th>Score</th>
                    <th>Threshold</th>
                    <th>Distance</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
        """


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate backtest diagnostics report")
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output path (without extension, e.g., 'reports/backtest_2025_11')",
    )

    args = parser.parse_args()

    start_date = datetime.fromisoformat(args.start)
    end_date = datetime.fromisoformat(args.end)
    output_path = Path(args.output)

    # Connect to database
    db_pool = DatabasePool(
        dsn="postgresql://scp:scp_dev_password@localhost:5432/scp",
        min_size=1,
        max_size=5,
    )
    await db_pool.connect()

    try:
        generator = BacktestReportGenerator(db_pool)
        await generator.generate_report(start_date, end_date, output_path)
    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
