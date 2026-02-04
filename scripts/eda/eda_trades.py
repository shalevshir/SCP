#!/usr/bin/env python3
"""
Trades EDA (Exploratory Data Analysis) Script

Comprehensive analysis of executed trades including:
- Trade outcomes (win/loss patterns)
- Market state at entry/exit
- Timing analysis (entry quality, duration, exit type)
- Decision validation (was the bot's decision correct?)

Usage:
    python scripts/eda/eda_trades.py --start 2025-11-01 --end 2025-11-30

Outputs:
    - HTML report with visualizations
    - JSON report for LLM analysis (default)
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import numpy as np
import pandas as pd


class TradesEDA:
    """Exploratory Data Analysis for executed trades."""

    def __init__(self, db_url: str):
        """
        Initialize the Trades EDA analyzer.

        Args:
            db_url: PostgreSQL connection URL
        """
        self.db_url = db_url
        self.trades_df: pd.DataFrame | None = None
        self.features_df: pd.DataFrame | None = None
        self.candles_df: pd.DataFrame | None = None
        self.trade_stats: dict[str, Any] = {}
        self.market_state_analysis: dict[str, Any] = {}
        self.decision_analysis: dict[str, Any] = {}
        self.factor_analysis: dict[str, Any] = {}

    async def load_data(self, start_date: str, end_date: str) -> None:
        """
        Load trades and related market data from database.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        from dateutil import parser

        start_dt = parser.parse(start_date)
        end_dt = parser.parse(end_date)

        print(f"Loading trades from {start_date} to {end_date}...")

        conn = await asyncpg.connect(self.db_url)
        try:
            # Load trades with signal diagnostics joined
            trades_query = """
                SELECT
                    t.id,
                    t.signal_id,
                    t.direction,
                    t.setup_type,
                    t.entry_price,
                    t.sl_price,
                    t.tp_price,
                    t.quantity,
                    t.opened_at,
                    t.closed_at,
                    t.exit_price,
                    t.exit_reason,
                    t.pnl_points,
                    t.r_multiple,
                    t.state,
                    t.confirmations,
                    t.transition_history,
                    t.entry_bar_idx,
                    t.reached_1r,
                    t.created_at,
                    t.updated_at,
                    -- Signal diagnostics (joined from signal_history)
                    sh.score as signal_score,
                    sh.confidence as signal_confidence,
                    sh.features_snapshot,
                    sh.htf_bias_snapshot,
                    sh.factor_scores,
                    sh.diagnostics as signal_diagnostics
                FROM trades t
                LEFT JOIN signal_history sh ON sh.signal_message_id = t.signal_id
                WHERE t.opened_at >= $1 AND t.opened_at < $2
                ORDER BY t.opened_at;
            """
            trades_rows = await conn.fetch(trades_query, start_dt, end_dt)

            if not trades_rows:
                print("No trades found in the specified date range.")
                self.trades_df = pd.DataFrame()
                return

            self.trades_df = pd.DataFrame([dict(row) for row in trades_rows])
            self.trades_df["opened_at"] = pd.to_datetime(self.trades_df["opened_at"])
            if "closed_at" in self.trades_df.columns:
                self.trades_df["closed_at"] = pd.to_datetime(
                    self.trades_df["closed_at"]
                )

            # Convert Decimal columns to float
            for col in self.trades_df.columns:
                if self.trades_df[col].dtype == object and len(self.trades_df[col]) > 0:
                    first_val = (
                        self.trades_df[col].dropna().iloc[0]
                        if len(self.trades_df[col].dropna()) > 0
                        else None
                    )
                    if isinstance(first_val, Decimal):
                        self.trades_df[col] = self.trades_df[col].astype(float)

            print(f"  Loaded {len(self.trades_df)} trades")

            # Get the full date range needed for market context
            # (extend range to include time before first trade and after last trade)
            min_trade_time = self.trades_df["opened_at"].min() - timedelta(hours=2)
            max_trade_time = (
                self.trades_df["closed_at"].max()
                if self.trades_df["closed_at"].notna().any()
                else self.trades_df["opened_at"].max()
            ) + timedelta(hours=2)

            # Load features around trade times for market state context
            features_query = """
                SELECT
                    f.timestamp,
                    f.close,
                    f.vwap,
                    f.vwap_deviation,
                    f.vwap_deviation_normalized,
                    f.atr,
                    f.rsi,
                    f.structure_label,
                    f.ema_9,
                    f.ema_20,
                    f.ema_50,
                    f.near_vwap_count_last_20,
                    f.bars_near_vwap,
                    f.bars_since_last_vwap_touch
                FROM features f
                WHERE f.symbol = 'GC'
                  AND f.timeframe = '1m'
                  AND f.timestamp >= $1
                  AND f.timestamp < $2
                ORDER BY f.timestamp;
            """
            features_rows = await conn.fetch(features_query, min_trade_time, max_trade_time)

            if features_rows:
                self.features_df = pd.DataFrame([dict(row) for row in features_rows])
                self.features_df["timestamp"] = pd.to_datetime(
                    self.features_df["timestamp"]
                )
                # Convert Decimal columns
                for col in self.features_df.columns:
                    if (
                        self.features_df[col].dtype == object
                        and len(self.features_df[col]) > 0
                    ):
                        first_val = (
                            self.features_df[col].dropna().iloc[0]
                            if len(self.features_df[col].dropna()) > 0
                            else None
                        )
                        if isinstance(first_val, Decimal):
                            self.features_df[col] = self.features_df[col].astype(float)
                print(f"  Loaded {len(self.features_df)} feature records for context")
            else:
                self.features_df = pd.DataFrame()

            # Load candles for price action context
            candles_query = """
                SELECT
                    c.timestamp,
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume
                FROM candles c
                WHERE c.symbol = 'GC'
                  AND c.timeframe = '1m'
                  AND c.timestamp >= $1
                  AND c.timestamp < $2
                ORDER BY c.timestamp;
            """
            candles_rows = await conn.fetch(candles_query, min_trade_time, max_trade_time)

            if candles_rows:
                self.candles_df = pd.DataFrame([dict(row) for row in candles_rows])
                self.candles_df["timestamp"] = pd.to_datetime(
                    self.candles_df["timestamp"]
                )
                # Convert Decimal columns
                for col in self.candles_df.columns:
                    if (
                        self.candles_df[col].dtype == object
                        and len(self.candles_df[col]) > 0
                    ):
                        first_val = (
                            self.candles_df[col].dropna().iloc[0]
                            if len(self.candles_df[col].dropna()) > 0
                            else None
                        )
                        if isinstance(first_val, Decimal):
                            self.candles_df[col] = self.candles_df[col].astype(float)
                print(f"  Loaded {len(self.candles_df)} candles for price context")
            else:
                self.candles_df = pd.DataFrame()

            # Load signal history for entry context
            signal_query = """
                SELECT
                    sh.id,
                    sh.timestamp,
                    sh.direction,
                    sh.setup_type,
                    sh.score,
                    sh.confidence,
                    sh.features_snapshot,
                    sh.htf_bias_snapshot,
                    sh.factor_scores,
                    sh.diagnostics,
                    sh.signal_message_id,
                    sh.trade_id
                FROM signal_history sh
                WHERE sh.was_approved = TRUE
                  AND sh.timestamp >= $1
                  AND sh.timestamp < $2
                ORDER BY sh.timestamp;
            """
            signal_rows = await conn.fetch(signal_query, start_dt, end_dt)

            if signal_rows:
                self.signals_df = pd.DataFrame([dict(row) for row in signal_rows])
                self.signals_df["timestamp"] = pd.to_datetime(
                    self.signals_df["timestamp"]
                )
                print(f"  Loaded {len(self.signals_df)} approved signals")
            else:
                self.signals_df = pd.DataFrame()

        finally:
            await conn.close()

    def get_detailed_trade_records(self) -> list[dict[str, Any]]:
        """
        Get detailed trade records with signal diagnostics for comprehensive analysis.

        Returns:
            List of trade records with full signal context
        """
        if self.trades_df is None or self.trades_df.empty:
            return []

        print("Extracting detailed trade records with signal diagnostics...")

        detailed_records = []

        for _, trade in self.trades_df.iterrows():
            record = {
                # Trade basics
                "trade_id": str(trade["id"]),
                "signal_id": str(trade["signal_id"]) if trade["signal_id"] else None,
                "direction": trade["direction"],
                "setup_type": trade["setup_type"],
                "opened_at": trade["opened_at"].isoformat() if pd.notna(trade["opened_at"]) else None,
                "closed_at": trade["closed_at"].isoformat() if pd.notna(trade["closed_at"]) else None,
                "state": trade["state"],
                # Prices
                "entry_price": float(trade["entry_price"]) if pd.notna(trade["entry_price"]) else None,
                "sl_price": float(trade["sl_price"]) if pd.notna(trade["sl_price"]) else None,
                "tp_price": float(trade["tp_price"]) if pd.notna(trade["tp_price"]) else None,
                "exit_price": float(trade["exit_price"]) if pd.notna(trade["exit_price"]) else None,
                "exit_reason": trade["exit_reason"],
                # P&L
                "pnl_points": float(trade["pnl_points"]) if pd.notna(trade["pnl_points"]) else None,
                "r_multiple": float(trade["r_multiple"]) if pd.notna(trade["r_multiple"]) else None,
                "reached_1r": bool(trade["reached_1r"]) if pd.notna(trade["reached_1r"]) else None,
                # Outcome classification
                "outcome": (
                    "win" if pd.notna(trade["pnl_points"]) and trade["pnl_points"] > 0
                    else ("loss" if pd.notna(trade["pnl_points"]) and trade["pnl_points"] < 0 else "breakeven/open")
                ),
            }

            # Signal diagnostics (if available from join)
            if "signal_score" in trade and pd.notna(trade["signal_score"]):
                record["signal_score"] = float(trade["signal_score"])
            if "signal_confidence" in trade and trade["signal_confidence"]:
                record["signal_confidence"] = trade["signal_confidence"]

            # Features snapshot at entry
            if "features_snapshot" in trade and trade["features_snapshot"]:
                features = trade["features_snapshot"]
                if isinstance(features, dict):
                    record["features_at_entry"] = {
                        "rsi": features.get("rsi"),
                        "vwap_deviation": features.get("vwap_deviation"),
                        "vwap_deviation_normalized": features.get("vwap_deviation_normalized"),
                        "near_vwap_count_last_20": features.get("near_vwap_count_last_20"),
                        "bars_near_vwap": features.get("bars_near_vwap"),
                        "bars_since_last_vwap_touch": features.get("bars_since_last_vwap_touch"),
                        "structure_label": features.get("structure_label"),
                        "structure_clarity": features.get("structure_clarity"),
                        "trend_confidence": features.get("trend_confidence"),
                        "bos_direction": features.get("bos_direction"),
                        "bos_age": features.get("bos_age"),
                        "choch_detected": features.get("choch_detected"),
                        "atr": features.get("atr"),
                        "ema_9": features.get("ema_9"),
                        "ema_20": features.get("ema_20"),
                        "ema_50": features.get("ema_50"),
                        "max_abs_deviation_last_20": features.get("max_abs_deviation_last_20"),
                        "min_abs_deviation_last_20": features.get("min_abs_deviation_last_20"),
                    }

            # HTF bias snapshot
            if "htf_bias_snapshot" in trade and trade["htf_bias_snapshot"]:
                htf = trade["htf_bias_snapshot"]
                if isinstance(htf, dict):
                    record["htf_bias_at_entry"] = {
                        "bias": htf.get("bias"),
                        "score": htf.get("score"),
                        "confidence": htf.get("confidence"),
                        "structure_1h": htf.get("structure_1h"),
                        "structure_15m": htf.get("structure_15m"),
                        "dxy_aligned": htf.get("dxy_aligned"),
                        "chop_detected": htf.get("chop_detected"),
                        "conflict_detected": htf.get("conflict_detected"),
                        "conflict_reason": htf.get("conflict_reason"),
                    }

            # Factor scores (scoring breakdown)
            if "factor_scores" in trade and trade["factor_scores"]:
                factor_scores = trade["factor_scores"]
                if isinstance(factor_scores, dict):
                    record["factor_scores"] = factor_scores

            # Signal diagnostics (constraint checks, etc.)
            if "signal_diagnostics" in trade and trade["signal_diagnostics"]:
                diagnostics = trade["signal_diagnostics"]
                if isinstance(diagnostics, dict):
                    # Extract key diagnostic info
                    record["signal_diagnostics"] = {
                        "vwap_reclaim_validation": diagnostics.get("vwap_reclaim_validation"),
                        "constraint_results": diagnostics.get("constraint_results"),
                        "rejection_analysis": diagnostics.get("rejection_analysis"),
                    }

            detailed_records.append(record)

        print(f"  Extracted {len(detailed_records)} detailed trade records")
        return detailed_records

    def analyze_trade_outcomes(self) -> dict[str, Any]:
        """
        Analyze trade outcomes: wins, losses, breakeven.

        Returns:
            Dictionary with outcome statistics
        """
        if self.trades_df is None or self.trades_df.empty:
            return {}

        print("Analyzing trade outcomes...")

        closed_trades = self.trades_df[self.trades_df["state"] == "CLOSED"].copy()
        open_trades = self.trades_df[self.trades_df["state"] == "OPEN"]
        invalidated_trades = self.trades_df[self.trades_df["state"] == "INVALIDATED"]

        outcomes = {
            "total_trades": len(self.trades_df),
            "closed_trades": len(closed_trades),
            "open_trades": len(open_trades),
            "invalidated_trades": len(invalidated_trades),
        }

        if len(closed_trades) > 0:
            # Win/Loss classification using pnl_points (handle None values)
            closed_trades["outcome"] = closed_trades["pnl_points"].apply(
                lambda x: "win" if x is not None and x > 0 else ("loss" if x is not None and x < 0 else "breakeven")
            )

            wins = closed_trades[closed_trades["outcome"] == "win"]
            losses = closed_trades[closed_trades["outcome"] == "loss"]
            breakevens = closed_trades[closed_trades["outcome"] == "breakeven"]

            outcomes["wins"] = len(wins)
            outcomes["losses"] = len(losses)
            outcomes["breakevens"] = len(breakevens)
            outcomes["win_rate"] = (
                len(wins) / len(closed_trades) if len(closed_trades) > 0 else 0
            )

            # P&L statistics (points)
            outcomes["total_pnl_points"] = float(closed_trades["pnl_points"].dropna().sum())
            outcomes["avg_pnl_points"] = float(closed_trades["pnl_points"].dropna().mean()) if closed_trades["pnl_points"].notna().any() else 0
            outcomes["max_win_points"] = float(closed_trades["pnl_points"].dropna().max()) if closed_trades["pnl_points"].notna().any() else 0
            outcomes["max_loss_points"] = float(closed_trades["pnl_points"].dropna().min()) if closed_trades["pnl_points"].notna().any() else 0

            if len(wins) > 0 and wins["pnl_points"].notna().any():
                outcomes["avg_win_points"] = float(wins["pnl_points"].dropna().mean())
            if len(losses) > 0 and losses["pnl_points"].notna().any():
                outcomes["avg_loss_points"] = float(losses["pnl_points"].dropna().mean())

            # R-multiple statistics
            if closed_trades["r_multiple"].notna().any():
                outcomes["avg_r_multiple"] = float(
                    closed_trades["r_multiple"].dropna().mean()
                )
                outcomes["max_r_multiple"] = float(
                    closed_trades["r_multiple"].dropna().max()
                )
                outcomes["min_r_multiple"] = float(
                    closed_trades["r_multiple"].dropna().min()
                )

            # Exit reason breakdown
            exit_reasons = closed_trades["exit_reason"].value_counts().to_dict()
            outcomes["exit_reasons"] = {str(k): int(v) for k, v in exit_reasons.items()}

            # Setup type breakdown
            setup_types = self.trades_df["setup_type"].value_counts().to_dict()
            outcomes["setup_types"] = {str(k): int(v) for k, v in setup_types.items()}

            # Direction breakdown
            direction_stats = {}
            for direction in ["long", "short"]:
                dir_trades = closed_trades[closed_trades["direction"] == direction]
                if len(dir_trades) > 0:
                    dir_wins = dir_trades[dir_trades["outcome"] == "win"]
                    direction_stats[direction] = {
                        "total": len(dir_trades),
                        "wins": len(dir_wins),
                        "win_rate": len(dir_wins) / len(dir_trades),
                        "total_pnl": float(dir_trades["pnl_points"].dropna().sum()) if dir_trades["pnl_points"].notna().any() else 0,
                        "avg_pnl": float(dir_trades["pnl_points"].dropna().mean()) if dir_trades["pnl_points"].notna().any() else 0,
                    }
            outcomes["by_direction"] = direction_stats

        self.trade_stats = outcomes
        return outcomes

    def analyze_factor_scores(self) -> dict[str, Any]:
        """
        Analyze factor scores across trades to identify patterns.

        Returns:
            Dictionary with factor score analysis by outcome
        """
        if self.trades_df is None or self.trades_df.empty:
            return {}

        if "factor_scores" not in self.trades_df.columns:
            return {"error": "No factor_scores data available"}

        print("Analyzing factor scores...")

        # Extract factor scores from trades that have them
        factor_data = []
        for _, trade in self.trades_df.iterrows():
            if trade["factor_scores"] and isinstance(trade["factor_scores"], dict):
                outcome = (
                    "win" if pd.notna(trade["pnl_points"]) and trade["pnl_points"] > 0
                    else ("loss" if pd.notna(trade["pnl_points"]) and trade["pnl_points"] < 0 else "other")
                )
                record = {"outcome": outcome}
                record.update(trade["factor_scores"])
                factor_data.append(record)

        if not factor_data:
            return {"error": "No factor scores found in trades"}

        factor_df = pd.DataFrame(factor_data)

        # Get all factor columns (exclude 'outcome')
        factor_cols = [c for c in factor_df.columns if c != "outcome"]

        analysis = {
            "total_trades_with_scores": len(factor_df),
            "by_outcome": {},
            "factor_comparison": [],
        }

        # Analyze by outcome
        for outcome in ["win", "loss"]:
            outcome_df = factor_df[factor_df["outcome"] == outcome]
            if len(outcome_df) > 0:
                outcome_stats = {"count": len(outcome_df), "factor_averages": {}}
                for col in factor_cols:
                    if outcome_df[col].notna().any():
                        outcome_stats["factor_averages"][col] = float(outcome_df[col].dropna().mean())
                analysis["by_outcome"][outcome] = outcome_stats

        # Compare factors between wins and losses
        if "win" in analysis["by_outcome"] and "loss" in analysis["by_outcome"]:
            win_avgs = analysis["by_outcome"]["win"]["factor_averages"]
            loss_avgs = analysis["by_outcome"]["loss"]["factor_averages"]

            for factor in factor_cols:
                if factor in win_avgs and factor in loss_avgs:
                    diff = win_avgs[factor] - loss_avgs[factor]
                    if abs(diff) > 0.2:  # Meaningful difference threshold
                        analysis["factor_comparison"].append({
                            "factor": factor,
                            "win_avg": win_avgs[factor],
                            "loss_avg": loss_avgs[factor],
                            "difference": diff,
                            "insight": f"{'Higher' if diff > 0 else 'Lower'} {factor} correlates with wins",
                        })

            # Sort by absolute difference
            analysis["factor_comparison"].sort(key=lambda x: abs(x["difference"]), reverse=True)

        self.factor_analysis = analysis
        return analysis

    def analyze_market_state_at_entry(self) -> dict[str, Any]:
        """
        Analyze market state when trades were entered.

        Returns:
            Dictionary with market state analysis at entry
        """
        if (
            self.trades_df is None
            or self.trades_df.empty
            or self.features_df is None
            or self.features_df.empty
        ):
            return {}

        print("Analyzing market state at entry...")

        market_states = []

        for _, trade in self.trades_df.iterrows():
            entry_time = trade["opened_at"]

            # Find nearest features record
            time_diffs = abs(self.features_df["timestamp"] - entry_time)
            nearest_idx = time_diffs.idxmin()
            features = self.features_df.loc[nearest_idx]

            state = {
                "trade_id": str(trade["id"]),
                "direction": trade["direction"],
                "setup_type": trade["setup_type"],
                "entry_time": entry_time.isoformat(),
                "outcome": (
                    "win"
                    if trade["pnl_points"] is not None and trade["pnl_points"] > 0
                    else (
                        "loss"
                        if trade["pnl_points"] is not None and trade["pnl_points"] < 0
                        else "open"
                    )
                ),
                "pnl_points": (
                    float(trade["pnl_points"])
                    if trade["pnl_points"] is not None
                    else None
                ),
                # Market state features
                "rsi_at_entry": (
                    float(features["rsi"]) if pd.notna(features["rsi"]) else None
                ),
                "vwap_deviation_at_entry": (
                    float(features["vwap_deviation"])
                    if pd.notna(features["vwap_deviation"])
                    else None
                ),
                "vwap_deviation_normalized_at_entry": (
                    float(features["vwap_deviation_normalized"])
                    if pd.notna(features["vwap_deviation_normalized"])
                    else None
                ),
                "structure_label_at_entry": features["structure_label"],
                "atr_at_entry": (
                    float(features["atr"]) if pd.notna(features["atr"]) else None
                ),
                "near_vwap_count_at_entry": (
                    int(features["near_vwap_count_last_20"])
                    if pd.notna(features["near_vwap_count_last_20"])
                    else None
                ),
                "bars_since_vwap_touch_at_entry": (
                    int(features["bars_since_last_vwap_touch"])
                    if pd.notna(features["bars_since_last_vwap_touch"])
                    else None
                ),
                # EMA alignment
                "ema_alignment": self._classify_ema_alignment(features),
            }

            market_states.append(state)

        market_states_df = pd.DataFrame(market_states)

        # Aggregate statistics by outcome
        analysis = {
            "entry_states": market_states,
            "aggregate_by_outcome": {},
        }

        for outcome in ["win", "loss"]:
            outcome_states = market_states_df[market_states_df["outcome"] == outcome]
            if len(outcome_states) > 0:
                analysis["aggregate_by_outcome"][outcome] = {
                    "count": len(outcome_states),
                    "avg_rsi": (
                        float(outcome_states["rsi_at_entry"].dropna().mean())
                        if outcome_states["rsi_at_entry"].notna().any()
                        else None
                    ),
                    "avg_vwap_deviation_normalized": (
                        float(
                            outcome_states[
                                "vwap_deviation_normalized_at_entry"
                            ].dropna().mean()
                        )
                        if outcome_states[
                            "vwap_deviation_normalized_at_entry"
                        ].notna().any()
                        else None
                    ),
                    "avg_near_vwap_count": (
                        float(outcome_states["near_vwap_count_at_entry"].dropna().mean())
                        if outcome_states["near_vwap_count_at_entry"].notna().any()
                        else None
                    ),
                    "structure_labels": (
                        outcome_states["structure_label_at_entry"]
                        .value_counts()
                        .to_dict()
                    ),
                    "ema_alignments": (
                        outcome_states["ema_alignment"].value_counts().to_dict()
                    ),
                }

        # Find patterns that distinguish wins from losses
        if (
            "win" in analysis["aggregate_by_outcome"]
            and "loss" in analysis["aggregate_by_outcome"]
        ):
            win_stats = analysis["aggregate_by_outcome"]["win"]
            loss_stats = analysis["aggregate_by_outcome"]["loss"]

            patterns = []

            # RSI pattern
            if win_stats.get("avg_rsi") and loss_stats.get("avg_rsi"):
                rsi_diff = win_stats["avg_rsi"] - loss_stats["avg_rsi"]
                if abs(rsi_diff) > 5:
                    patterns.append(
                        {
                            "feature": "rsi",
                            "observation": f"Winning trades had RSI {'higher' if rsi_diff > 0 else 'lower'} by {abs(rsi_diff):.1f} on average",
                            "win_avg": win_stats["avg_rsi"],
                            "loss_avg": loss_stats["avg_rsi"],
                        }
                    )

            # VWAP deviation pattern
            if win_stats.get("avg_vwap_deviation_normalized") and loss_stats.get(
                "avg_vwap_deviation_normalized"
            ):
                vwap_diff = (
                    win_stats["avg_vwap_deviation_normalized"]
                    - loss_stats["avg_vwap_deviation_normalized"]
                )
                if abs(vwap_diff) > 0.5:
                    patterns.append(
                        {
                            "feature": "vwap_deviation_normalized",
                            "observation": f"Winning trades had VWAP deviation {'higher' if vwap_diff > 0 else 'lower'} by {abs(vwap_diff):.2f} ATR on average",
                            "win_avg": win_stats["avg_vwap_deviation_normalized"],
                            "loss_avg": loss_stats["avg_vwap_deviation_normalized"],
                        }
                    )

            analysis["distinguishing_patterns"] = patterns

        self.market_state_analysis = analysis
        return analysis

    def _classify_ema_alignment(self, features: pd.Series) -> str:
        """Classify EMA alignment (bullish, bearish, mixed)."""
        ema_9 = features.get("ema_9")
        ema_20 = features.get("ema_20")
        ema_50 = features.get("ema_50")

        if pd.isna(ema_9) or pd.isna(ema_20) or pd.isna(ema_50):
            return "unknown"

        if ema_9 > ema_20 > ema_50:
            return "bullish_stack"
        elif ema_9 < ema_20 < ema_50:
            return "bearish_stack"
        else:
            return "mixed"

    def analyze_timing(self) -> dict[str, Any]:
        """
        Analyze trade timing: duration, time of day, day of week.

        Returns:
            Dictionary with timing analysis
        """
        if self.trades_df is None or self.trades_df.empty:
            return {}

        print("Analyzing trade timing...")

        closed_trades = self.trades_df[
            (self.trades_df["state"] == "CLOSED")
            & (self.trades_df["closed_at"].notna())
        ].copy()

        timing = {
            "duration_analysis": {},
            "time_of_day_analysis": {},
            "day_of_week_analysis": {},
        }

        if len(closed_trades) > 0:
            # Duration analysis
            closed_trades["duration_minutes"] = (
                closed_trades["closed_at"] - closed_trades["opened_at"]
            ).dt.total_seconds() / 60

            closed_trades["outcome"] = closed_trades["pnl_points"].apply(
                lambda x: "win" if x is not None and x > 0 else ("loss" if x is not None and x < 0 else "breakeven")
            )

            timing["duration_analysis"] = {
                "avg_duration_minutes": float(closed_trades["duration_minutes"].mean()),
                "median_duration_minutes": float(
                    closed_trades["duration_minutes"].median()
                ),
                "min_duration_minutes": float(closed_trades["duration_minutes"].min()),
                "max_duration_minutes": float(closed_trades["duration_minutes"].max()),
            }

            # Duration by outcome
            for outcome in ["win", "loss"]:
                outcome_trades = closed_trades[closed_trades["outcome"] == outcome]
                if len(outcome_trades) > 0:
                    timing["duration_analysis"][f"avg_duration_{outcome}_minutes"] = (
                        float(outcome_trades["duration_minutes"].mean())
                    )

            # Time of day analysis (hour of entry)
            self.trades_df["entry_hour"] = self.trades_df["opened_at"].dt.hour

            hour_stats = []
            for hour in range(24):
                hour_trades = self.trades_df[self.trades_df["entry_hour"] == hour]
                if len(hour_trades) > 0:
                    closed_hour = hour_trades[hour_trades["state"] == "CLOSED"]
                    wins = (
                        len(closed_hour[(closed_hour["pnl_points"].notna()) & (closed_hour["pnl_points"] > 0)])
                        if len(closed_hour) > 0
                        else 0
                    )
                    hour_stats.append(
                        {
                            "hour": hour,
                            "total_trades": len(hour_trades),
                            "closed_trades": len(closed_hour),
                            "wins": wins,
                            "win_rate": (
                                wins / len(closed_hour) if len(closed_hour) > 0 else 0
                            ),
                            "total_pnl": (
                                float(closed_hour["pnl_points"].dropna().sum())
                                if len(closed_hour) > 0 and closed_hour["pnl_points"].notna().any()
                                else 0
                            ),
                        }
                    )

            timing["time_of_day_analysis"]["by_hour"] = hour_stats

            # Find best/worst hours
            if hour_stats:
                best_hour = max(hour_stats, key=lambda x: x["total_pnl"])
                worst_hour = min(hour_stats, key=lambda x: x["total_pnl"])
                timing["time_of_day_analysis"]["best_hour"] = best_hour
                timing["time_of_day_analysis"]["worst_hour"] = worst_hour

            # Day of week analysis
            self.trades_df["day_of_week"] = self.trades_df["opened_at"].dt.day_name()

            day_stats = []
            for day in [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]:
                day_trades = self.trades_df[self.trades_df["day_of_week"] == day]
                if len(day_trades) > 0:
                    closed_day = day_trades[day_trades["state"] == "CLOSED"]
                    wins = (
                        len(closed_day[(closed_day["pnl_points"].notna()) & (closed_day["pnl_points"] > 0)])
                        if len(closed_day) > 0
                        else 0
                    )
                    day_stats.append(
                        {
                            "day": day,
                            "total_trades": len(day_trades),
                            "closed_trades": len(closed_day),
                            "wins": wins,
                            "win_rate": (
                                wins / len(closed_day) if len(closed_day) > 0 else 0
                            ),
                            "total_pnl": (
                                float(closed_day["pnl_points"].dropna().sum())
                                if len(closed_day) > 0 and closed_day["pnl_points"].notna().any()
                                else 0
                            ),
                        }
                    )

            timing["day_of_week_analysis"]["by_day"] = day_stats

        return timing

    def analyze_decision_quality(self) -> dict[str, Any]:
        """
        Analyze the quality of bot decisions.

        For each trade, evaluate:
        - Was entry timing correct?
        - Did price action validate the setup?
        - Were stops/targets appropriate?

        Returns:
            Dictionary with decision quality analysis
        """
        if (
            self.trades_df is None
            or self.trades_df.empty
            or self.candles_df is None
            or self.candles_df.empty
        ):
            return {}

        print("Analyzing decision quality...")

        decision_analysis = []

        for _, trade in self.trades_df.iterrows():
            entry_time = trade["opened_at"]
            entry_price = float(trade["entry_price"])
            sl_price = float(trade["sl_price"])
            tp_price = float(trade["tp_price"])
            direction = trade["direction"]

            # Get candles after entry
            post_entry_candles = self.candles_df[
                self.candles_df["timestamp"] > entry_time
            ].head(60)  # Look at next 60 minutes

            if len(post_entry_candles) == 0:
                continue

            # Calculate key metrics
            analysis_record = {
                "trade_id": str(trade["id"]),
                "direction": direction,
                "entry_price": entry_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "exit_reason": trade["exit_reason"],
                "pnl_points": (
                    float(trade["pnl_points"])
                    if trade["pnl_points"] is not None
                    else None
                ),
            }

            # Maximum Favorable Excursion (MFE) - how far did price go in our favor?
            if direction == "long":
                mfe = float(post_entry_candles["high"].max()) - entry_price
                mae = entry_price - float(post_entry_candles["low"].min())
            else:
                mfe = entry_price - float(post_entry_candles["low"].min())
                mae = float(post_entry_candles["high"].max()) - entry_price

            # Risk (distance to stop)
            risk = abs(entry_price - sl_price)

            analysis_record["mfe_points"] = mfe
            analysis_record["mae_points"] = mae
            analysis_record["risk_points"] = risk
            analysis_record["mfe_r_multiple"] = mfe / risk if risk > 0 else 0
            analysis_record["mae_r_multiple"] = mae / risk if risk > 0 else 0

            # Entry quality assessment
            # Good entry = MFE > MAE (price went more in our favor than against)
            analysis_record["entry_quality"] = "good" if mfe > mae else "poor"

            # Target assessment
            # Did price reach target potential?
            target_distance = abs(tp_price - entry_price)
            analysis_record["reached_target_potential"] = mfe >= target_distance * 0.8

            # Stop assessment
            # Was stop hit before potential target?
            analysis_record["stop_hit_prematurely"] = (
                trade["exit_reason"] == "stop_loss" and mfe > risk
            )

            decision_analysis.append(analysis_record)

        analysis_df = pd.DataFrame(decision_analysis)

        result = {
            "trade_decisions": decision_analysis,
            "summary": {},
        }

        if len(analysis_df) > 0:
            result["summary"] = {
                "total_analyzed": len(analysis_df),
                "good_entries": int(
                    (analysis_df["entry_quality"] == "good").sum()
                ),
                "poor_entries": int(
                    (analysis_df["entry_quality"] == "poor").sum()
                ),
                "entry_quality_rate": float(
                    (analysis_df["entry_quality"] == "good").mean()
                ),
                "avg_mfe_r": float(analysis_df["mfe_r_multiple"].mean()),
                "avg_mae_r": float(analysis_df["mae_r_multiple"].mean()),
                "reached_target_potential": int(
                    analysis_df["reached_target_potential"].sum()
                ),
                "stops_hit_prematurely": int(
                    analysis_df["stop_hit_prematurely"].sum()
                ),
            }

            # Entry quality by outcome
            if "pnl_points" in analysis_df.columns:
                wins = analysis_df[
                    (analysis_df["pnl_points"].notna())
                    & (analysis_df["pnl_points"] > 0)
                ]
                losses = analysis_df[
                    (analysis_df["pnl_points"].notna())
                    & (analysis_df["pnl_points"] < 0)
                ]

                if len(wins) > 0:
                    result["summary"]["wins_with_good_entry"] = int(
                        (wins["entry_quality"] == "good").sum()
                    )
                    result["summary"]["wins_avg_mfe_r"] = float(
                        wins["mfe_r_multiple"].mean()
                    )

                if len(losses) > 0:
                    result["summary"]["losses_with_good_entry"] = int(
                        (losses["entry_quality"] == "good").sum()
                    )
                    result["summary"]["losses_avg_mfe_r"] = float(
                        losses["mfe_r_multiple"].mean()
                    )
                    # Losses with good MFE suggest stop placement or exit timing issues
                    result["summary"]["losses_with_mfe_above_1r"] = int(
                        (losses["mfe_r_multiple"] > 1).sum()
                    )

        self.decision_analysis = result
        return result

    def analyze_price_action_post_trade(self) -> dict[str, Any]:
        """
        Analyze what happened to price after trade closed.

        Helps identify:
        - Trades closed too early (price continued in direction)
        - Trades that should have been held longer
        - Patterns in post-trade price movement

        Returns:
            Dictionary with post-trade price action analysis
        """
        if (
            self.trades_df is None
            or self.trades_df.empty
            or self.candles_df is None
            or self.candles_df.empty
        ):
            return {}

        print("Analyzing post-trade price action...")

        post_trade_analysis = []

        closed_trades = self.trades_df[
            (self.trades_df["state"] == "CLOSED")
            & (self.trades_df["closed_at"].notna())
        ]

        for _, trade in closed_trades.iterrows():
            close_time = trade["closed_at"]
            exit_price = float(trade["exit_price"]) if trade["exit_price"] else None
            direction = trade["direction"]
            tp_price = float(trade["tp_price"])

            if exit_price is None:
                continue

            # Get candles after exit (next 30 minutes)
            post_exit_candles = self.candles_df[
                self.candles_df["timestamp"] > close_time
            ].head(30)

            if len(post_exit_candles) == 0:
                continue

            record = {
                "trade_id": str(trade["id"]),
                "direction": direction,
                "exit_price": exit_price,
                "tp_price": tp_price,
                "exit_reason": trade["exit_reason"],
                "pnl_points": (
                    float(trade["pnl_points"])
                    if trade["pnl_points"] is not None
                    else None
                ),
            }

            # How far did price go in original direction after exit?
            if direction == "long":
                max_price_after = float(post_exit_candles["high"].max())
                continuation = max_price_after - exit_price
                would_have_hit_tp = max_price_after >= tp_price
            else:
                min_price_after = float(post_exit_candles["low"].min())
                continuation = exit_price - min_price_after
                would_have_hit_tp = min_price_after <= tp_price

            record["continuation_points"] = continuation
            record["would_have_hit_tp"] = would_have_hit_tp
            record["left_on_table_points"] = (
                continuation if continuation > 0 else 0
            )

            # Classify exit
            if trade["exit_reason"] == "take_profit":
                record["exit_assessment"] = "correct_tp"
            elif would_have_hit_tp and trade["pnl_points"] is not None and trade["pnl_points"] < 0:
                record["exit_assessment"] = "premature_exit_loss"
            elif would_have_hit_tp:
                record["exit_assessment"] = "premature_exit"
            else:
                record["exit_assessment"] = "correct_exit"

            post_trade_analysis.append(record)

        result = {
            "post_trade_records": post_trade_analysis,
            "summary": {},
        }

        if post_trade_analysis:
            analysis_df = pd.DataFrame(post_trade_analysis)

            premature_exits = analysis_df[
                analysis_df["exit_assessment"].isin(
                    ["premature_exit", "premature_exit_loss"]
                )
            ]

            result["summary"] = {
                "total_analyzed": len(analysis_df),
                "premature_exits": len(premature_exits),
                "premature_exit_rate": (
                    len(premature_exits) / len(analysis_df) if len(analysis_df) > 0 else 0
                ),
                "avg_continuation_points": float(
                    analysis_df["continuation_points"].mean()
                ),
                "total_left_on_table_points": float(
                    analysis_df["left_on_table_points"].sum()
                ),
                "exit_assessment_breakdown": (
                    analysis_df["exit_assessment"].value_counts().to_dict()
                ),
            }

        return result

    def export_json_report(
        self,
        output_path: str,
        start_date: str,
        end_date: str,
    ) -> None:
        """
        Export EDA report as JSON for LLM analysis.

        Args:
            output_path: Path to save JSON report
            start_date: Analysis start date
            end_date: Analysis end date
        """
        print(f"Exporting JSON report to {output_path}...")

        # Get detailed trade records with signal diagnostics
        detailed_trades = self.get_detailed_trade_records()

        # Analyze factor scores
        factor_analysis = self.analyze_factor_scores()

        report: dict[str, Any] = {
            "metadata": {
                "report_type": "trades_eda",
                "period": {"start": start_date, "end": end_date},
                "generated": datetime.now().isoformat(),
                "symbol": "GC",
            },
            "trade_outcomes": self.trade_stats,
            "detailed_trades": detailed_trades,  # Full trade records with signal diagnostics
            "factor_score_analysis": factor_analysis,  # Factor score patterns by outcome
            "market_state_at_entry": self.market_state_analysis,
            "timing_analysis": self.analyze_timing(),
            "decision_quality": self.decision_analysis,
            "post_trade_analysis": self.analyze_price_action_post_trade(),
            "recommendations": [],
        }

        # Generate recommendations based on analysis
        recommendations = []

        # Check win rate
        if self.trade_stats.get("win_rate", 0) < 0.5:
            recommendations.append(
                {
                    "type": "win_rate",
                    "observation": f"Win rate is {self.trade_stats.get('win_rate', 0):.1%}, below 50%",
                    "suggestion": "Review entry criteria and constraint thresholds",
                }
            )

        # Check for pattern differences between wins and losses
        if self.market_state_analysis.get("distinguishing_patterns"):
            for pattern in self.market_state_analysis["distinguishing_patterns"]:
                recommendations.append(
                    {
                        "type": "pattern_insight",
                        "feature": pattern["feature"],
                        "observation": pattern["observation"],
                        "suggestion": f"Consider adjusting {pattern['feature']} thresholds",
                    }
                )

        # Check decision quality
        if self.decision_analysis.get("summary", {}).get("losses_with_mfe_above_1r", 0) > 0:
            recommendations.append(
                {
                    "type": "stop_management",
                    "observation": f"{self.decision_analysis['summary']['losses_with_mfe_above_1r']} losses had MFE > 1R",
                    "suggestion": "Consider implementing trailing stops or better profit protection",
                }
            )

        # Check factor score differences
        if factor_analysis.get("factor_comparison"):
            for factor_comp in factor_analysis["factor_comparison"][:3]:  # Top 3 differences
                recommendations.append(
                    {
                        "type": "factor_insight",
                        "factor": factor_comp["factor"],
                        "observation": factor_comp["insight"],
                        "win_avg": factor_comp["win_avg"],
                        "loss_avg": factor_comp["loss_avg"],
                        "suggestion": f"Investigate {factor_comp['factor']} scoring weight or requirements",
                    }
                )

        report["recommendations"] = recommendations

        # Write JSON
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(report, indent=2, default=str))

        print(f"✓ JSON report saved to: {output_path}")

    def export_html_report(
        self,
        output_path: str,
        start_date: str,
        end_date: str,
    ) -> None:
        """
        Export EDA report as HTML with visualizations.

        Args:
            output_path: Path to save HTML report
            start_date: Analysis start date
            end_date: Analysis end date
        """
        print(f"Exporting HTML report to {output_path}...")

        html_parts = [self._generate_html_header(start_date, end_date)]

        # Summary section
        html_parts.append(self._generate_summary_section())

        # Trade outcomes section
        html_parts.append(self._generate_outcomes_section())

        # Market state section
        html_parts.append(self._generate_market_state_section())

        # Timing section
        html_parts.append(self._generate_timing_section())

        # Decision quality section
        html_parts.append(self._generate_decision_quality_section())

        # Recommendations section
        html_parts.append(self._generate_recommendations_section())

        html_parts.append(self._generate_html_footer())

        # Write HTML
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("\n".join(html_parts))

        print(f"✓ HTML report saved to: {output_path}")

    def _generate_html_header(self, start_date: str, end_date: str) -> str:
        """Generate HTML header with styles."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trades EDA Report - {start_date} to {end_date}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }}
        h1, h2, h3 {{ color: #1a1a2e; }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #1a1a2e;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .win {{ color: #28a745; }}
        .loss {{ color: #dc3545; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        .recommendation {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 10px 0;
            border-radius: 0 8px 8px 0;
        }}
        .insight {{
            background: #d4edda;
            border-left: 4px solid #28a745;
            padding: 15px;
            margin: 10px 0;
            border-radius: 0 8px 8px 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Trades EDA Report</h1>
        <p>Period: {start_date} to {end_date}</p>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
"""

    def _generate_summary_section(self) -> str:
        """Generate summary section."""
        stats = self.trade_stats

        if not stats:
            return '<div class="section"><h2>Summary</h2><p>No trade data available.</p></div>'

        win_rate = stats.get("win_rate", 0)
        total_pnl = stats.get("total_pnl_points", 0)
        pnl_class = "win" if total_pnl >= 0 else "loss"

        return f"""
    <div class="section">
        <h2>📈 Summary</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-value">{stats.get('total_trades', 0)}</div>
                <div class="metric-label">Total Trades</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{stats.get('wins', 0)} / {stats.get('losses', 0)}</div>
                <div class="metric-label">Wins / Losses</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{win_rate:.1%}</div>
                <div class="metric-label">Win Rate</div>
            </div>
            <div class="metric-card">
                <div class="metric-value {pnl_class}">{total_pnl:,.2f} pts</div>
                <div class="metric-label">Total P&L (points)</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{stats.get('avg_r_multiple', 0):.2f}R</div>
                <div class="metric-label">Avg R-Multiple</div>
            </div>
        </div>
    </div>
"""

    def _generate_outcomes_section(self) -> str:
        """Generate trade outcomes section."""
        stats = self.trade_stats

        if not stats:
            return ""

        exit_reasons = stats.get("exit_reasons", {})
        direction_stats = stats.get("by_direction", {})

        exit_rows = "\n".join(
            f"<tr><td>{reason}</td><td>{count}</td></tr>"
            for reason, count in exit_reasons.items()
        )

        direction_rows = ""
        for direction, d_stats in direction_stats.items():
            direction_rows += f"""
            <tr>
                <td>{direction.title()}</td>
                <td>{d_stats['total']}</td>
                <td>{d_stats['wins']}</td>
                <td>{d_stats['win_rate']:.1%}</td>
                <td class="{'win' if d_stats['total_pnl'] >= 0 else 'loss'}">${d_stats['total_pnl']:,.2f}</td>
            </tr>
            """

        return f"""
    <div class="section">
        <h2>🎯 Trade Outcomes</h2>

        <h3>Exit Reasons</h3>
        <table>
            <tr><th>Exit Reason</th><th>Count</th></tr>
            {exit_rows}
        </table>

        <h3>Performance by Direction</h3>
        <table>
            <tr><th>Direction</th><th>Total</th><th>Wins</th><th>Win Rate</th><th>P&L</th></tr>
            {direction_rows}
        </table>
    </div>
"""

    def _generate_market_state_section(self) -> str:
        """Generate market state analysis section."""
        analysis = self.market_state_analysis

        if not analysis:
            return ""

        patterns_html = ""
        if analysis.get("distinguishing_patterns"):
            for pattern in analysis["distinguishing_patterns"]:
                patterns_html += f"""
                <div class="insight">
                    <strong>{pattern['feature']}</strong>: {pattern['observation']}
                </div>
                """

        aggregate = analysis.get("aggregate_by_outcome", {})
        aggregate_rows = ""
        for outcome, stats in aggregate.items():
            avg_rsi = stats.get('avg_rsi')
            avg_vwap_dev = stats.get('avg_vwap_deviation_normalized')
            avg_near_vwap = stats.get('avg_near_vwap_count')
            aggregate_rows += f"""
            <tr>
                <td>{outcome.title()}</td>
                <td>{stats['count']}</td>
                <td>{f'{avg_rsi:.1f}' if avg_rsi is not None else 'N/A'}</td>
                <td>{f'{avg_vwap_dev:.2f}' if avg_vwap_dev is not None else 'N/A'}</td>
                <td>{f'{avg_near_vwap:.1f}' if avg_near_vwap is not None else 'N/A'}</td>
            </tr>
            """

        return f"""
    <div class="section">
        <h2>🌡️ Market State at Entry</h2>

        <h3>Distinguishing Patterns</h3>
        {patterns_html if patterns_html else '<p>No significant patterns found.</p>'}

        <h3>Aggregate by Outcome</h3>
        <table>
            <tr>
                <th>Outcome</th>
                <th>Count</th>
                <th>Avg RSI</th>
                <th>Avg VWAP Dev (ATR)</th>
                <th>Avg Near VWAP Count</th>
            </tr>
            {aggregate_rows}
        </table>
    </div>
"""

    def _generate_timing_section(self) -> str:
        """Generate timing analysis section."""
        timing = self.analyze_timing()

        if not timing:
            return ""

        duration = timing.get("duration_analysis", {})

        time_of_day = timing.get("time_of_day_analysis", {})
        best_hour = time_of_day.get("best_hour", {})
        worst_hour = time_of_day.get("worst_hour", {})

        return f"""
    <div class="section">
        <h2>⏱️ Timing Analysis</h2>

        <h3>Trade Duration</h3>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-value">{duration.get('avg_duration_minutes', 0):.1f}</div>
                <div class="metric-label">Avg Duration (min)</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{duration.get('median_duration_minutes', 0):.1f}</div>
                <div class="metric-label">Median Duration (min)</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{duration.get('avg_duration_win_minutes', 0):.1f}</div>
                <div class="metric-label">Avg Win Duration</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{duration.get('avg_duration_loss_minutes', 0):.1f}</div>
                <div class="metric-label">Avg Loss Duration</div>
            </div>
        </div>

        <h3>Time of Day Performance</h3>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-value win">{best_hour.get('hour', 'N/A')}:00</div>
                <div class="metric-label">Best Hour (${best_hour.get('total_pnl', 0):,.0f})</div>
            </div>
            <div class="metric-card">
                <div class="metric-value loss">{worst_hour.get('hour', 'N/A')}:00</div>
                <div class="metric-label">Worst Hour (${worst_hour.get('total_pnl', 0):,.0f})</div>
            </div>
        </div>
    </div>
"""

    def _generate_decision_quality_section(self) -> str:
        """Generate decision quality section."""
        quality = self.decision_analysis

        if not quality or not quality.get("summary"):
            return ""

        summary = quality["summary"]

        return f"""
    <div class="section">
        <h2>🧠 Decision Quality</h2>

        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-value">{summary.get('entry_quality_rate', 0):.1%}</div>
                <div class="metric-label">Good Entry Rate</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{summary.get('avg_mfe_r', 0):.2f}R</div>
                <div class="metric-label">Avg MFE</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{summary.get('avg_mae_r', 0):.2f}R</div>
                <div class="metric-label">Avg MAE</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{summary.get('losses_with_mfe_above_1r', 0)}</div>
                <div class="metric-label">Losses with MFE > 1R</div>
            </div>
        </div>

        <p><strong>MFE</strong> = Maximum Favorable Excursion (how far price went in your favor)</p>
        <p><strong>MAE</strong> = Maximum Adverse Excursion (how far price went against you)</p>

        {f'<div class="recommendation"><strong>⚠️ {summary.get("losses_with_mfe_above_1r", 0)} losing trades had MFE > 1R</strong> - These trades went in your favor but ended as losses. Consider implementing trailing stops or profit protection.</div>' if summary.get('losses_with_mfe_above_1r', 0) > 0 else ''}
    </div>
"""

    def _generate_recommendations_section(self) -> str:
        """Generate recommendations section."""
        recommendations = []

        # Check win rate
        if self.trade_stats.get("win_rate", 0) < 0.5:
            recommendations.append(
                f"Win rate ({self.trade_stats.get('win_rate', 0):.1%}) is below 50%. Review entry criteria."
            )

        # Check for losses with good MFE
        if self.decision_analysis.get("summary", {}).get("losses_with_mfe_above_1r", 0) > 0:
            count = self.decision_analysis["summary"]["losses_with_mfe_above_1r"]
            recommendations.append(
                f"{count} losses had MFE > 1R. Implement trailing stops or better profit protection."
            )

        # Check patterns
        if self.market_state_analysis.get("distinguishing_patterns"):
            for pattern in self.market_state_analysis["distinguishing_patterns"]:
                recommendations.append(
                    f"Consider {pattern['feature']}: {pattern['observation']}"
                )

        if not recommendations:
            return ""

        recs_html = "\n".join(
            f'<div class="recommendation">{rec}</div>' for rec in recommendations
        )

        return f"""
    <div class="section">
        <h2>💡 Recommendations</h2>
        {recs_html}
    </div>
"""

    def _generate_html_footer(self) -> str:
        """Generate HTML footer."""
        return """
</body>
</html>
"""


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive EDA for executed trades"
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: reports/trades_eda_<start>_<end>.html)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL (default: from DATABASE_URL env var)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Export JSON report for LLM analysis (default: True)",
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="Disable JSON report export",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Export only JSON report (no HTML)",
    )

    args = parser.parse_args()

    # Get database URL
    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: Database URL not provided. Set DATABASE_URL env var or use --db-url")
        sys.exit(1)

    # Set output path
    output_path = args.output or f"reports/trades_eda_{args.start}_{args.end}.html"

    # Initialize EDA
    eda = TradesEDA(db_url)

    # Load data
    await eda.load_data(args.start, args.end)

    if eda.trades_df is None or eda.trades_df.empty:
        print("No trades found. Exiting.")
        sys.exit(0)

    # Run analyses
    eda.analyze_trade_outcomes()
    eda.analyze_market_state_at_entry()
    eda.analyze_timing()
    eda.analyze_decision_quality()
    eda.analyze_price_action_post_trade()

    # Export reports
    json_path = output_path.replace(".html", ".json")
    export_json = args.json and not args.no_json

    if not args.json_only:
        eda.export_html_report(output_path, args.start, args.end)

    if export_json or args.json_only:
        eda.export_json_report(json_path, args.start, args.end)

    print(f"\n✅ Trades EDA complete!")
    if not args.json_only:
        print(f"   HTML report: {output_path}")
    if export_json or args.json_only:
        print(f"   JSON report: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
