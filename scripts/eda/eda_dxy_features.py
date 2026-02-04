"""
Comprehensive EDA (Exploratory Data Analysis) for DXY_CONTINUATION features and constraints.

This script analyzes:
1. DXY correlation feature distributions (1m and 5m)
2. DXY structure patterns and alignment
3. Constraint failure patterns
4. BOS recency and clarity bonus distributions
5. Temporal patterns (correlation stability over time)
6. Feature correlations between DXY and Gold indicators

Usage:
    python scripts/eda/eda_dxy_features.py --start 2025-11-05 --end 2025-11-10
    python scripts/eda/eda_dxy_features.py --start 2025-11-05 --end 2025-11-10 --detect-anomalies
    make eda-dxy START=2025-11-05 END=2025-11-10
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats as scipy_stats

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.eda.utils.data_loader import (
    extract_context_values,
)
from scripts.eda.utils.plotting import (
    create_histogram_with_kde,
    create_box_plot_by_group,
    create_time_series,
    create_correlation_heatmap,
    create_bar_chart,
    create_pie_chart,
    create_threshold_optimization_curve,
    create_intraday_heatmap,
    COLORS,
)


class DXYFeatureEDA:
    """Exploratory Data Analysis for DXY_CONTINUATION features and constraints."""

    # Feature columns to analyze
    DXY_FEATURES = [
        "dxy_corr",           # 1-minute DXY correlation
        "dxy_5m_corr",        # 5-minute DXY correlation
        "dxy_structure_label", # DXY structure (HH, HL, LH, LL)
        "structure_clarity",   # Gold structure clarity
        "bos_age",            # BOS recency in bars
        "bos_direction",      # BOS direction
        "last_structure_label", # Gold structure label
        "is_chop",            # Chop detection
        "body",               # Candle body size
        "lower_wick",         # Lower wick size
        "upper_wick",         # Upper wick size
        "rsi",                # RSI
        "vwap_deviation",     # VWAP deviation
        "trend_confidence",   # Trend confidence
    ]

    # Constraints from config/setups.yaml for DXY_CONTINUATION
    DXY_CONSTRAINTS = {
        "valid_direction": {
            "fields": ["direction"],
            "type": "categorical",
        },
        "gold_structure_required": {
            "fields": ["last_structure_label"],
            "type": "categorical",
        },
        "gold_structure_long": {
            "fields": ["last_structure_label", "direction"],
            "type": "categorical",
        },
        "gold_structure_short": {
            "fields": ["last_structure_label", "direction"],
            "type": "categorical",
        },
        "no_positive_dxy_correlation": {
            "fields": ["dxy_corr", "dxy_5m_corr"],
            "type": "numeric",
            "bounds": (None, 0.1),
        },
        "no_contradicting_dxy_structure": {
            "fields": ["dxy_structure_label", "direction"],
            "type": "categorical",
        },
        "no_wick_chop": {
            "fields": ["is_chop", "body", "lower_wick", "upper_wick"],
            "type": "numeric",
            "bounds": (None, 3.0),  # wick_body_ratio
        },
        "no_contradicting_htf_bias": {
            "fields": ["htf_direction", "direction"],
            "type": "categorical",
        },
    }

    # Scoring thresholds from config
    CORRELATION_THRESHOLDS = {
        "strong": -0.5,    # Score 1.0x weight
        "moderate": -0.3,  # Score 0.6x weight
        "weak": -0.15,     # Score 0.3x weight
    }

    BOS_THRESHOLDS = {
        "fresh": 10,   # Full bonus if within 10 bars
        "recent": 20,  # Partial bonus if within 20 bars
    }

    CLARITY_THRESHOLDS = {
        "excellent": 0.7,   # Full bonus
        "good": 0.5,        # 0.7x bonus
        "acceptable": 0.3,  # 0.4x bonus
    }

    def __init__(self, db_url: str):
        """
        Initialize EDA analyzer.

        Args:
            db_url: PostgreSQL connection URL
        """
        self.db_url = db_url
        self.features_df: pd.DataFrame | None = None
        self.signal_history_df: pd.DataFrame | None = None
        self.constraint_stats: dict[str, Any] | None = None
        self.feature_stats: dict[str, Any] | None = None
        self.anomalies: pd.DataFrame | None = None

    async def load_data(
        self,
        start_date: str,
        end_date: str,
        symbol: str = "GC",
    ) -> None:
        """
        Load features and signal history data from database.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            symbol: Asset symbol (default: GC)
        """
        print(f"Loading features data for {symbol} from {start_date} to {end_date}...")
        self.features_df = await self._load_dxy_features(
            start_date,
            end_date,
            symbol=symbol,
        )
        print(f"  Loaded {len(self.features_df)} feature records")

        print(f"Loading signal history data from {start_date} to {end_date}...")
        self.signal_history_df = await self._load_dxy_signal_history(
            start_date,
            end_date,
        )
        print(f"  Loaded {len(self.signal_history_df)} signal records")

    async def _load_dxy_features(
        self,
        start_date: str,
        end_date: str,
        symbol: str = "GC",
        timeframe: str = "1m",
    ) -> pd.DataFrame:
        """Load DXY-relevant features from signal_history (features_snapshot JSONB)."""
        import asyncpg
        from dateutil import parser as date_parser

        start_dt = date_parser.parse(start_date)
        end_dt = date_parser.parse(end_date)

        # Query from signal_history which has features_snapshot with DXY features
        query = """
            SELECT
                sh.timestamp,
                sh.symbol,
                sh.direction,
                sh.setup_type,
                sh.score,
                sh.was_approved,
                -- Extract from features_snapshot JSONB
                (sh.features_snapshot->>'close')::numeric as close,
                (sh.features_snapshot->>'open')::numeric as open,
                (sh.features_snapshot->>'high')::numeric as high,
                (sh.features_snapshot->>'low')::numeric as low,
                (sh.features_snapshot->>'vwap')::numeric as vwap,
                (sh.features_snapshot->>'vwap_deviation')::numeric as vwap_deviation,
                (sh.features_snapshot->>'atr')::numeric as atr,
                (sh.features_snapshot->>'rsi')::numeric as rsi,
                sh.features_snapshot->>'structure_label' as last_structure_label,
                (sh.features_snapshot->>'structure_clarity')::numeric as structure_clarity,
                (sh.features_snapshot->>'dxy_corr')::numeric as dxy_corr,
                (sh.features_snapshot->>'dxy_5m_corr')::numeric as dxy_5m_corr,
                sh.features_snapshot->>'dxy_structure' as dxy_structure_label,
                (sh.features_snapshot->>'bos_age')::integer as bos_age,
                sh.features_snapshot->>'bos_direction' as bos_direction,
                (sh.features_snapshot->>'trend_confidence')::numeric as trend_confidence,
                (sh.features_snapshot->>'choch_detected')::boolean as choch_detected,
                sh.features_snapshot->>'choch_direction' as choch_direction,
                -- Extract from diagnostics JSONB
                (sh.diagnostics->>'is_structural_chop')::boolean as is_chop,
                sh.diagnostics->>'htf_direction' as htf_direction,
                sh.diagnostics->>'chop_severity' as chop_severity
            FROM signal_history sh
            WHERE sh.symbol = $1
              AND sh.timestamp >= $2
              AND sh.timestamp < $3
            ORDER BY sh.timestamp;
        """

        conn = await asyncpg.connect(self.db_url)
        try:
            rows = await conn.fetch(
                query,
                symbol,
                start_dt,
                end_dt,
            )

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame([dict(row) for row in rows])
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Calculate body and wick sizes
            if all(col in df.columns for col in ['open', 'close', 'high', 'low']):
                df['body'] = abs(df['close'] - df['open'])
                df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
                df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']

            # Convert Decimal columns to float
            from decimal import Decimal
            for col in df.columns:
                if df[col].dtype == object and len(df[col]) > 0:
                    first_val = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else None
                    if isinstance(first_val, Decimal):
                        df[col] = df[col].astype(float)

            return df

        finally:
            await conn.close()

    async def _load_dxy_signal_history(
        self,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Load DXY_CONTINUATION signal history including rejections."""
        import asyncpg
        from dateutil import parser as date_parser

        start_dt = date_parser.parse(start_date)
        end_dt = date_parser.parse(end_date)

        # Query all signals that might be relevant to DXY_CONTINUATION analysis
        # Including REJECTED signals that may have failed DXY-related constraints
        query = """
            SELECT
                sh.timestamp,
                sh.id,
                sh.symbol,
                sh.direction,
                sh.setup_type,
                sh.score,
                sh.confidence,
                sh.was_approved,
                sh.rejection_stage,
                -- Try to get DXY-specific constraint failures
                COALESCE(
                    sh.diagnostics->'dxy_continuation_validation'->>'failed_constraint',
                    sh.diagnostics->'vwap_reclaim_validation'->>'failed_constraint'
                ) as failed_constraint,
                COALESCE(
                    sh.diagnostics->'dxy_continuation_validation'->>'reject_reason',
                    sh.diagnostics->'vwap_reclaim_validation'->>'reject_reason'
                ) as reject_reason,
                sh.diagnostics->>'dxy_corr_1m' as diag_dxy_corr_1m,
                sh.diagnostics->>'dxy_corr_5m' as diag_dxy_corr_5m,
                sh.diagnostics->>'dxy_alignment' as diag_dxy_alignment,
                sh.diagnostics->>'structure_clarity' as diag_clarity,
                sh.diagnostics->>'bos_age' as diag_bos_age,
                sh.diagnostics->>'structure_label' as diag_structure_label
            FROM signal_history sh
            WHERE sh.timestamp >= $1
              AND sh.timestamp < $2
            ORDER BY sh.timestamp;
        """

        conn = await asyncpg.connect(self.db_url)
        try:
            rows = await conn.fetch(query, start_dt, end_dt)

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame([dict(row) for row in rows])
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Convert Decimal columns to float
            from decimal import Decimal
            for col in df.columns:
                if df[col].dtype == object and len(df[col]) > 0:
                    first_val = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else None
                    if isinstance(first_val, Decimal):
                        df[col] = df[col].astype(float)

            return df

        finally:
            await conn.close()

    def analyze_feature_distributions(self) -> dict[str, Any]:
        """
        Analyze statistical distributions for all DXY features.

        Returns:
            Dictionary with statistics for each feature
        """
        if self.features_df is None or len(self.features_df) == 0:
            return {}

        print("Analyzing feature distributions...")
        stats_dict = {}

        for feature in self.DXY_FEATURES:
            if feature not in self.features_df.columns:
                continue

            data = self.features_df[feature].dropna()
            if len(data) == 0:
                stats_dict[feature] = {"count": 0, "null_pct": 100.0}
                continue

            # Handle categorical vs numeric
            if feature in ["dxy_structure_label", "last_structure_label", "bos_direction"]:
                # Categorical stats
                value_counts = data.value_counts()
                stats_dict[feature] = {
                    "count": len(data),
                    "null_count": int(self.features_df[feature].isna().sum()),
                    "null_pct": (self.features_df[feature].isna().sum() / len(self.features_df)) * 100,
                    "unique_values": int(data.nunique()),
                    "top_value": str(value_counts.index[0]) if len(value_counts) > 0 else None,
                    "top_count": int(value_counts.iloc[0]) if len(value_counts) > 0 else 0,
                    "distribution": value_counts.to_dict(),
                }
            elif feature == "is_chop":
                # Boolean stats
                true_count = data.sum()
                stats_dict[feature] = {
                    "count": len(data),
                    "null_count": int(self.features_df[feature].isna().sum()),
                    "null_pct": (self.features_df[feature].isna().sum() / len(self.features_df)) * 100,
                    "true_count": int(true_count),
                    "true_pct": float(true_count / len(data) * 100) if len(data) > 0 else 0,
                    "false_count": int(len(data) - true_count),
                }
            else:
                # Numeric stats
                stats_dict[feature] = {
                    "count": len(data),
                    "null_count": int(self.features_df[feature].isna().sum()),
                    "null_pct": (self.features_df[feature].isna().sum() / len(self.features_df)) * 100,
                    "mean": float(data.mean()),
                    "median": float(data.median()),
                    "std": float(data.std()),
                    "min": float(data.min()),
                    "max": float(data.max()),
                    "p5": float(data.quantile(0.05)),
                    "p25": float(data.quantile(0.25)),
                    "p75": float(data.quantile(0.75)),
                    "p95": float(data.quantile(0.95)),
                    "skewness": float(data.skew()),
                    "kurtosis": float(data.kurtosis()),
                }

        self.feature_stats = stats_dict
        return stats_dict

    def analyze_correlation_quality(self) -> dict[str, Any]:
        """
        Analyze DXY correlation quality and scoring distribution.

        Returns:
            Dictionary with correlation quality metrics
        """
        if self.features_df is None or len(self.features_df) == 0:
            return {}

        print("Analyzing DXY correlation quality...")

        result = {
            "1m_correlation": {},
            "5m_correlation": {},
            "dual_correlation": {},
            "scoring_distribution": {},
        }

        # 1m correlation analysis
        if "dxy_corr" in self.features_df.columns:
            corr_1m = self.features_df["dxy_corr"].dropna()
            if len(corr_1m) > 0:
                result["1m_correlation"] = {
                    "strong_pct": float((corr_1m < self.CORRELATION_THRESHOLDS["strong"]).sum() / len(corr_1m) * 100),
                    "moderate_pct": float(((corr_1m >= self.CORRELATION_THRESHOLDS["strong"]) &
                                          (corr_1m < self.CORRELATION_THRESHOLDS["moderate"])).sum() / len(corr_1m) * 100),
                    "weak_pct": float(((corr_1m >= self.CORRELATION_THRESHOLDS["moderate"]) &
                                      (corr_1m < self.CORRELATION_THRESHOLDS["weak"])).sum() / len(corr_1m) * 100),
                    "positive_pct": float((corr_1m >= 0.1).sum() / len(corr_1m) * 100),
                    "mean": float(corr_1m.mean()),
                    "std": float(corr_1m.std()),
                }

        # 5m correlation analysis
        if "dxy_5m_corr" in self.features_df.columns:
            corr_5m = self.features_df["dxy_5m_corr"].dropna()
            if len(corr_5m) > 0:
                result["5m_correlation"] = {
                    "strong_pct": float((corr_5m < self.CORRELATION_THRESHOLDS["strong"]).sum() / len(corr_5m) * 100),
                    "moderate_pct": float(((corr_5m >= self.CORRELATION_THRESHOLDS["strong"]) &
                                          (corr_5m < self.CORRELATION_THRESHOLDS["moderate"])).sum() / len(corr_5m) * 100),
                    "weak_pct": float(((corr_5m >= self.CORRELATION_THRESHOLDS["moderate"]) &
                                      (corr_5m < self.CORRELATION_THRESHOLDS["weak"])).sum() / len(corr_5m) * 100),
                    "positive_pct": float((corr_5m >= 0.1).sum() / len(corr_5m) * 100),
                    "mean": float(corr_5m.mean()),
                    "std": float(corr_5m.std()),
                }

        # Dual correlation analysis (minimum of both)
        if "dxy_corr" in self.features_df.columns and "dxy_5m_corr" in self.features_df.columns:
            df_both = self.features_df[["dxy_corr", "dxy_5m_corr"]].dropna()
            if len(df_both) > 0:
                min_corr = df_both.max(axis=1)  # max of negatives = weakest negative
                result["dual_correlation"] = {
                    "both_strong_pct": float(((df_both["dxy_corr"] < self.CORRELATION_THRESHOLDS["strong"]) &
                                             (df_both["dxy_5m_corr"] < self.CORRELATION_THRESHOLDS["strong"])).sum() / len(df_both) * 100),
                    "both_moderate_pct": float(((df_both["dxy_corr"] < self.CORRELATION_THRESHOLDS["moderate"]) &
                                               (df_both["dxy_5m_corr"] < self.CORRELATION_THRESHOLDS["moderate"])).sum() / len(df_both) * 100),
                    "both_negative_pct": float(((df_both["dxy_corr"] < 0) &
                                               (df_both["dxy_5m_corr"] < 0)).sum() / len(df_both) * 100),
                    "any_positive_pct": float(((df_both["dxy_corr"] >= 0.1) |
                                              (df_both["dxy_5m_corr"] >= 0.1)).sum() / len(df_both) * 100),
                    "correlation_between_1m_5m": float(df_both["dxy_corr"].corr(df_both["dxy_5m_corr"])),
                }

        return result

    def analyze_structure_alignment(self) -> dict[str, Any]:
        """
        Analyze Gold-DXY structure alignment patterns.

        Returns:
            Dictionary with structure alignment statistics
        """
        if self.features_df is None or len(self.features_df) == 0:
            return {}

        print("Analyzing structure alignment...")

        result = {
            "gold_structure": {},
            "dxy_structure": {},
            "alignment_matrix": {},
        }

        # Gold structure distribution
        if "last_structure_label" in self.features_df.columns:
            gold_struct = self.features_df["last_structure_label"].dropna()
            if len(gold_struct) > 0:
                result["gold_structure"] = gold_struct.value_counts().to_dict()

        # DXY structure distribution
        if "dxy_structure_label" in self.features_df.columns:
            dxy_struct = self.features_df["dxy_structure_label"].dropna()
            if len(dxy_struct) > 0:
                result["dxy_structure"] = dxy_struct.value_counts().to_dict()

        # Alignment matrix (Gold vs DXY structure)
        if "last_structure_label" in self.features_df.columns and "dxy_structure_label" in self.features_df.columns:
            df_both = self.features_df[["last_structure_label", "dxy_structure_label"]].dropna()
            if len(df_both) > 0:
                cross_tab = pd.crosstab(
                    df_both["last_structure_label"],
                    df_both["dxy_structure_label"],
                    normalize="all"
                ) * 100  # Convert to percentage

                result["alignment_matrix"] = cross_tab.to_dict()

                # Calculate aligned percentage
                # Long alignment: Gold HH/HL with DXY LL/LH
                # Short alignment: Gold LH/LL with DXY HH/HL
                bullish_gold = df_both["last_structure_label"].isin(["HH", "HL"])
                bearish_gold = df_both["last_structure_label"].isin(["LH", "LL"])
                bearish_dxy = df_both["dxy_structure_label"].isin(["LL", "LH"])
                bullish_dxy = df_both["dxy_structure_label"].isin(["HH", "HL"])

                long_aligned = (bullish_gold & bearish_dxy).sum()
                short_aligned = (bearish_gold & bullish_dxy).sum()
                total_aligned = long_aligned + short_aligned

                result["alignment_summary"] = {
                    "long_aligned_count": int(long_aligned),
                    "short_aligned_count": int(short_aligned),
                    "total_aligned_pct": float(total_aligned / len(df_both) * 100) if len(df_both) > 0 else 0,
                    "contradicting_pct": float(100 - (total_aligned / len(df_both) * 100)) if len(df_both) > 0 else 100,
                }

        return result

    def analyze_constraint_failures(self) -> dict[str, Any]:
        """
        Analyze constraint pass/fail rates and failure patterns.

        Returns:
            Dictionary with constraint failure statistics
        """
        if self.signal_history_df is None or len(self.signal_history_df) == 0:
            return {}

        print("Analyzing constraint failures...")

        # Filter to rejections with dxy_continuation_validation diagnostics
        rejections = self.signal_history_df[
            (self.signal_history_df["setup_type"] == "REJECTED")
            & (self.signal_history_df["failed_constraint"].notna())
        ]

        if len(rejections) == 0:
            return {"total_rejections": 0, "constraints": {}}

        # Count failures per constraint
        failure_counts = rejections["failed_constraint"].value_counts().to_dict()

        # Calculate pass rates
        total_evaluated = len(self.signal_history_df)
        constraint_stats = {}

        for constraint_name, failure_count in failure_counts.items():
            pass_rate = (total_evaluated - failure_count) / total_evaluated if total_evaluated > 0 else 0

            # Get example reject reason
            example_row = rejections[rejections["failed_constraint"] == constraint_name].iloc[0]
            example_reason = example_row.get("reject_reason", "N/A")

            constraint_stats[constraint_name] = {
                "failure_count": int(failure_count),
                "pass_count": int(total_evaluated - failure_count),
                "pass_rate": float(pass_rate),
                "example_reason": str(example_reason),
            }

        self.constraint_stats = {
            "total_evaluated": int(total_evaluated),
            "total_rejections": int(len(rejections)),
            "total_approved": int(len(self.signal_history_df[self.signal_history_df["was_approved"] == True])),
            "dxy_continuation_signals": int(len(self.signal_history_df[self.signal_history_df["setup_type"] == "DXY_CONTINUATION"])),
            "constraints": constraint_stats,
        }

        return self.constraint_stats

    def analyze_scoring_factors(self) -> dict[str, Any]:
        """
        Analyze BOS recency and clarity bonus distributions.

        Returns:
            Dictionary with scoring factor distributions
        """
        if self.features_df is None or len(self.features_df) == 0:
            return {}

        print("Analyzing scoring factor distributions...")

        result = {
            "bos_recency": {},
            "clarity": {},
            "wick_chop": {},
        }

        # BOS recency distribution
        if "bos_age" in self.features_df.columns:
            bos_age = self.features_df["bos_age"].dropna()
            if len(bos_age) > 0:
                result["bos_recency"] = {
                    "fresh_pct": float((bos_age <= self.BOS_THRESHOLDS["fresh"]).sum() / len(bos_age) * 100),
                    "recent_pct": float(((bos_age > self.BOS_THRESHOLDS["fresh"]) &
                                        (bos_age <= self.BOS_THRESHOLDS["recent"])).sum() / len(bos_age) * 100),
                    "stale_pct": float((bos_age > self.BOS_THRESHOLDS["recent"]).sum() / len(bos_age) * 100),
                    "mean_age": float(bos_age.mean()),
                    "median_age": float(bos_age.median()),
                    "p95_age": float(bos_age.quantile(0.95)),
                }

        # Clarity distribution
        if "structure_clarity" in self.features_df.columns:
            clarity = self.features_df["structure_clarity"].dropna()
            if len(clarity) > 0:
                result["clarity"] = {
                    "excellent_pct": float((clarity >= self.CLARITY_THRESHOLDS["excellent"]).sum() / len(clarity) * 100),
                    "good_pct": float(((clarity >= self.CLARITY_THRESHOLDS["good"]) &
                                      (clarity < self.CLARITY_THRESHOLDS["excellent"])).sum() / len(clarity) * 100),
                    "acceptable_pct": float(((clarity >= self.CLARITY_THRESHOLDS["acceptable"]) &
                                            (clarity < self.CLARITY_THRESHOLDS["good"])).sum() / len(clarity) * 100),
                    "poor_pct": float((clarity < self.CLARITY_THRESHOLDS["acceptable"]).sum() / len(clarity) * 100),
                    "mean": float(clarity.mean()),
                    "median": float(clarity.median()),
                }

        # Wick-chop analysis
        if all(col in self.features_df.columns for col in ["body", "lower_wick", "upper_wick"]):
            df_wicks = self.features_df[["body", "lower_wick", "upper_wick"]].dropna()
            if len(df_wicks) > 0:
                # Calculate wick-body ratio
                total_wick = df_wicks["lower_wick"] + df_wicks["upper_wick"]
                body = df_wicks["body"].replace(0, 0.1)  # Avoid division by zero
                wick_ratio = total_wick / body

                result["wick_chop"] = {
                    "mean_ratio": float(wick_ratio.mean()),
                    "median_ratio": float(wick_ratio.median()),
                    "excessive_pct": float((wick_ratio > 3.0).sum() / len(wick_ratio) * 100),
                    "clean_pct": float((wick_ratio < 1.5).sum() / len(wick_ratio) * 100),
                }

        return result

    def analyze_temporal_patterns(self) -> dict[str, Any]:
        """
        Analyze temporal patterns in DXY correlation (stability over time).

        Returns:
            Dictionary with temporal pattern statistics
        """
        if self.features_df is None or len(self.features_df) == 0:
            return {}

        print("Analyzing temporal patterns...")

        df = self.features_df.copy()
        df["hour"] = df["timestamp"].dt.hour
        df["date"] = df["timestamp"].dt.date

        # Compute hourly statistics for correlation
        hourly_stats = {}
        for feature in ["dxy_corr", "dxy_5m_corr", "structure_clarity"]:
            if feature not in df.columns:
                continue

            hourly = df.groupby("hour")[feature].agg(["mean", "std", "count"])
            hourly_stats[feature] = hourly.to_dict("index")

        # Correlation stability (rolling std)
        correlation_stability = {}
        if "dxy_corr" in df.columns:
            rolling_std = df["dxy_corr"].rolling(window=60, min_periods=30).std()
            correlation_stability["1m_rolling_volatility"] = {
                "mean": float(rolling_std.mean()) if not rolling_std.isna().all() else None,
                "max": float(rolling_std.max()) if not rolling_std.isna().all() else None,
            }

        return {
            "hourly_stats": hourly_stats,
            "correlation_stability": correlation_stability,
            "total_days": int(df["date"].nunique()),
            "hours_covered": sorted(df["hour"].unique().tolist()),
        }

    def analyze_feature_correlations(self) -> pd.DataFrame:
        """
        Compute Pearson correlation matrix for DXY-related features.

        Returns:
            Correlation matrix DataFrame
        """
        if self.features_df is None or len(self.features_df) == 0:
            return pd.DataFrame()

        print("Computing feature correlations...")

        # Select numeric columns
        numeric_features = [
            "dxy_corr",
            "dxy_5m_corr",
            "structure_clarity",
            "bos_age",
            "rsi",
            "vwap_deviation",
            "trend_confidence",
            "body",
            "lower_wick",
            "upper_wick",
        ]

        numeric_cols = [
            col
            for col in numeric_features
            if col in self.features_df.columns and pd.api.types.is_numeric_dtype(self.features_df[col])
        ]

        if len(numeric_cols) < 2:
            return pd.DataFrame()

        corr_matrix = self.features_df[numeric_cols].corr(method="pearson")
        return corr_matrix

    def detect_anomalies(
        self,
        method: str = "zscore",
        threshold: float = 3.0,
    ) -> pd.DataFrame:
        """
        Detect anomalies in DXY feature values.

        Args:
            method: Detection method ('zscore' or 'iqr')
            threshold: Z-score threshold (default: 3.0)

        Returns:
            DataFrame with anomaly records
        """
        if self.features_df is None or len(self.features_df) == 0:
            return pd.DataFrame()

        print(f"Detecting anomalies using {method} method...")

        anomaly_records = []
        numeric_features = ["dxy_corr", "dxy_5m_corr", "structure_clarity", "bos_age"]

        for feature in numeric_features:
            if feature not in self.features_df.columns:
                continue

            data = self.features_df[[feature, "timestamp"]].dropna()
            if len(data) < 10:
                continue

            if method == "zscore":
                z_scores = np.abs(scipy_stats.zscore(data[feature]))
                is_anomaly = z_scores > threshold

                for idx, row in data[is_anomaly].iterrows():
                    anomaly_records.append(
                        {
                            "timestamp": row["timestamp"],
                            "feature": feature,
                            "value": row[feature],
                            "z_score": z_scores[data.index.get_loc(idx)],
                            "severity": "high" if z_scores[data.index.get_loc(idx)] > 5 else "medium",
                        }
                    )

            elif method == "iqr":
                Q1 = data[feature].quantile(0.25)
                Q3 = data[feature].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR

                is_anomaly = (data[feature] < lower_bound) | (data[feature] > upper_bound)

                for idx, row in data[is_anomaly].iterrows():
                    distance = min(abs(row[feature] - lower_bound), abs(row[feature] - upper_bound))
                    anomaly_records.append(
                        {
                            "timestamp": row["timestamp"],
                            "feature": feature,
                            "value": row[feature],
                            "distance_from_bound": distance,
                            "severity": "high" if distance > 2 * IQR else "medium",
                        }
                    )

        if len(anomaly_records) == 0:
            return pd.DataFrame()

        anomalies_df = pd.DataFrame(anomaly_records)
        anomalies_df = anomalies_df.sort_values("timestamp")
        self.anomalies = anomalies_df

        return anomalies_df

    def export_html_report(
        self,
        output_path: str,
        start_date: str,
        end_date: str,
    ) -> None:
        """
        Export complete EDA report as interactive HTML.

        Args:
            output_path: Path to save HTML report
            start_date: Analysis start date
            end_date: Analysis end date
        """
        print(f"Exporting HTML report to {output_path}...")

        # Build HTML sections
        html_parts = []

        # Header
        html_parts.append(self._generate_html_header(start_date, end_date))

        # Summary statistics
        html_parts.append(self._generate_summary_section())

        # Tab 1: Correlation Quality
        html_parts.append(self._generate_correlation_quality_tab())

        # Tab 2: Structure Alignment
        html_parts.append(self._generate_structure_alignment_tab())

        # Tab 3: Feature Distributions
        html_parts.append(self._generate_feature_distributions_tab())

        # Tab 4: Constraint Analysis
        html_parts.append(self._generate_constraint_analysis_tab())

        # Tab 5: Scoring Factors
        html_parts.append(self._generate_scoring_factors_tab())

        # Tab 6: Temporal Patterns
        html_parts.append(self._generate_temporal_patterns_tab())

        # Tab 7: Correlations
        html_parts.append(self._generate_correlations_tab())

        # Tab 8: Anomalies (if detected)
        if self.anomalies is not None and len(self.anomalies) > 0:
            html_parts.append(self._generate_anomalies_tab())

        # Recommendations
        html_parts.append(self._generate_recommendations_section())

        # Footer
        html_parts.append(self._generate_html_footer())

        # Combine and write
        full_html = "\n".join(html_parts)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(full_html)

        print(f"✓ Report saved to: {output_path}")

    def _generate_html_header(self, start_date: str, end_date: str) -> str:
        """Generate HTML header."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>DXY_CONTINUATION Feature EDA Report - {start_date} to {end_date}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #9b59b6;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }}
        h3 {{
            color: #7f8c8d;
            margin-top: 30px;
        }}
        .metric-card {{
            display: inline-block;
            background: linear-gradient(135deg, #9b59b6 0%, #8e44ad 100%);
            color: white;
            padding: 20px;
            margin: 10px;
            border-radius: 8px;
            min-width: 200px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-card.green {{
            background: linear-gradient(135deg, #2ecc71 0%, #27ae60 100%);
        }}
        .metric-card.orange {{
            background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
        }}
        .metric-value {{
            font-size: 36px;
            font-weight: bold;
        }}
        .metric-label {{
            font-size: 14px;
            opacity: 0.9;
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }}
        th {{
            background-color: #9b59b6;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        .chart-container {{
            margin: 30px 0;
        }}
        .recommendation {{
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }}
        .warning {{
            background-color: #f8d7da;
            border-left: 4px solid #dc3545;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }}
        .success {{
            background-color: #d4edda;
            border-left: 4px solid #28a745;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }}
        .info {{
            background-color: #d1ecf1;
            border-left: 4px solid #17a2b8;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 DXY_CONTINUATION Feature EDA Report</h1>
        <p><strong>Analysis Period:</strong> {start_date} to {end_date}</p>
        <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><em>Setup: Gold trades aligned with DXY inverse correlation</em></p>
"""

    def _generate_summary_section(self) -> str:
        """Generate summary statistics section."""
        if self.features_df is None:
            return "<p>No data available for summary.</p>"

        total_features = len(self.features_df)
        date_range_days = (self.features_df["timestamp"].max() - self.features_df["timestamp"].min()).days

        html = f"""
        <h2>📈 Summary Statistics</h2>
        <div class="metric-card">
            <div class="metric-value">{total_features:,}</div>
            <div class="metric-label">Total Feature Records</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{date_range_days}</div>
            <div class="metric-label">Days Analyzed</div>
        </div>
"""

        # Correlation quality metrics
        corr_quality = self.analyze_correlation_quality()
        if corr_quality.get("dual_correlation", {}):
            both_negative = corr_quality["dual_correlation"].get("both_negative_pct", 0)
            html += f"""
        <div class="metric-card green">
            <div class="metric-value">{both_negative:.1f}%</div>
            <div class="metric-label">Both Correlations Negative</div>
        </div>
"""

        if self.constraint_stats:
            dxy_signals = self.constraint_stats.get("dxy_continuation_signals", 0)
            html += f"""
        <div class="metric-card orange">
            <div class="metric-value">{dxy_signals}</div>
            <div class="metric-label">DXY_CONTINUATION Signals</div>
        </div>
"""

        return html

    def _generate_correlation_quality_tab(self) -> str:
        """Generate correlation quality analysis tab."""
        if self.features_df is None:
            return ""

        html = "<h2>🔗 DXY Correlation Quality</h2>"

        corr_quality = self.analyze_correlation_quality()

        # 1m and 5m correlation histograms
        if "dxy_corr" in self.features_df.columns:
            fig_1m = create_histogram_with_kde(
                self.features_df["dxy_corr"],
                title="1-Minute DXY Correlation Distribution",
                xlabel="Correlation Coefficient",
            )
            # Add threshold lines
            for name, threshold in self.CORRELATION_THRESHOLDS.items():
                fig_1m.add_vline(x=threshold, line_dash="dash", line_color="gray",
                               annotation_text=f"{name}: {threshold}")
            html += f'<div class="chart-container">{fig_1m.to_html(include_plotlyjs=False, div_id="hist_dxy_corr_1m")}</div>'

        if "dxy_5m_corr" in self.features_df.columns:
            fig_5m = create_histogram_with_kde(
                self.features_df["dxy_5m_corr"],
                title="5-Minute DXY Correlation Distribution",
                xlabel="Correlation Coefficient",
            )
            for name, threshold in self.CORRELATION_THRESHOLDS.items():
                fig_5m.add_vline(x=threshold, line_dash="dash", line_color="gray",
                               annotation_text=f"{name}: {threshold}")
            html += f'<div class="chart-container">{fig_5m.to_html(include_plotlyjs=False, div_id="hist_dxy_corr_5m")}</div>'

        # Correlation quality summary table
        if corr_quality:
            html += """
        <h3>Correlation Quality Summary</h3>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>1m Correlation</th>
                    <th>5m Correlation</th>
                    <th>Dual (Both)</th>
                </tr>
            </thead>
            <tbody>
"""
            metrics = [
                ("Strong (< -0.5)", "strong_pct", "both_strong_pct"),
                ("Moderate (< -0.3)", "moderate_pct", "both_moderate_pct"),
                ("Weak (< -0.15)", "weak_pct", "both_negative_pct"),
                ("Positive (>= 0.1)", "positive_pct", "any_positive_pct"),
            ]

            for label, single_key, dual_key in metrics:
                val_1m = corr_quality.get("1m_correlation", {}).get(single_key, "-")
                val_5m = corr_quality.get("5m_correlation", {}).get(single_key, "-")
                val_dual = corr_quality.get("dual_correlation", {}).get(dual_key, "-")
                html += f"""
                <tr>
                    <td>{label}</td>
                    <td>{val_1m:.1f}%</td>
                    <td>{val_5m:.1f}%</td>
                    <td>{val_dual:.1f}%</td>
                </tr>
"""

            html += """
            </tbody>
        </table>
"""

        return html

    def _generate_structure_alignment_tab(self) -> str:
        """Generate structure alignment analysis tab."""
        if self.features_df is None:
            return ""

        html = "<h2>🏗️ Gold-DXY Structure Alignment</h2>"

        alignment = self.analyze_structure_alignment()

        # Gold structure pie chart
        if alignment.get("gold_structure"):
            labels = list(alignment["gold_structure"].keys())
            values = list(alignment["gold_structure"].values())
            fig_gold = create_pie_chart(labels, values, "Gold Structure Distribution")
            html += f'<div class="chart-container">{fig_gold.to_html(include_plotlyjs=False, div_id="pie_gold_structure")}</div>'

        # DXY structure pie chart
        if alignment.get("dxy_structure"):
            labels = list(alignment["dxy_structure"].keys())
            values = list(alignment["dxy_structure"].values())
            fig_dxy = create_pie_chart(labels, values, "DXY Structure Distribution")
            html += f'<div class="chart-container">{fig_dxy.to_html(include_plotlyjs=False, div_id="pie_dxy_structure")}</div>'

        # Alignment summary
        if alignment.get("alignment_summary"):
            summary = alignment["alignment_summary"]
            html += f"""
        <div class="info">
            <strong>Alignment Summary:</strong><br>
            Long-aligned (Gold bullish + DXY bearish): {summary['long_aligned_count']} occurrences<br>
            Short-aligned (Gold bearish + DXY bullish): {summary['short_aligned_count']} occurrences<br>
            Total aligned: {summary['total_aligned_pct']:.1f}%<br>
            Contradicting: {summary['contradicting_pct']:.1f}%
        </div>
"""

        return html

    def _generate_feature_distributions_tab(self) -> str:
        """Generate feature distributions tab."""
        if self.features_df is None or self.feature_stats is None:
            return ""

        html = "<h2>📊 Feature Distributions</h2>"

        # Feature availability table
        html += """
        <h3>Feature Availability</h3>
        <table>
            <thead>
                <tr>
                    <th>Feature</th>
                    <th>Count</th>
                    <th>Null %</th>
                    <th>Mean / Top Value</th>
                    <th>Std / Distribution</th>
                </tr>
            </thead>
            <tbody>
"""

        for feature, stats in self.feature_stats.items():
            if stats["count"] == 0:
                html += f"""
                <tr>
                    <td>{feature}</td>
                    <td>0</td>
                    <td>100.0%</td>
                    <td>-</td>
                    <td>-</td>
                </tr>
"""
            elif "mean" in stats:
                html += f"""
                <tr>
                    <td>{feature}</td>
                    <td>{stats['count']:,}</td>
                    <td>{stats['null_pct']:.1f}%</td>
                    <td>{stats['mean']:.3f}</td>
                    <td>{stats['std']:.3f}</td>
                </tr>
"""
            elif "top_value" in stats:
                html += f"""
                <tr>
                    <td>{feature}</td>
                    <td>{stats['count']:,}</td>
                    <td>{stats['null_pct']:.1f}%</td>
                    <td>{stats['top_value']}</td>
                    <td>{stats['unique_values']} unique</td>
                </tr>
"""
            elif "true_pct" in stats:
                html += f"""
                <tr>
                    <td>{feature}</td>
                    <td>{stats['count']:,}</td>
                    <td>{stats['null_pct']:.1f}%</td>
                    <td>True: {stats['true_pct']:.1f}%</td>
                    <td>False: {100-stats['true_pct']:.1f}%</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
"""

        return html

    def _generate_constraint_analysis_tab(self) -> str:
        """Generate constraint analysis tab."""
        if self.constraint_stats is None or len(self.constraint_stats.get("constraints", {})) == 0:
            return "<h2>⚠️ Constraint Analysis</h2><p>No constraint failures found in the analysis period.</p>"

        html = "<h2>⚠️ Constraint Analysis</h2>"

        # Failure counts bar chart
        constraints = self.constraint_stats["constraints"]
        constraint_names = list(constraints.keys())
        failure_counts = [constraints[c]["failure_count"] for c in constraint_names]

        # Sort by failure count
        sorted_indices = np.argsort(failure_counts)[::-1]
        constraint_names = [constraint_names[i] for i in sorted_indices]
        failure_counts = [failure_counts[i] for i in sorted_indices]

        fig_bar = create_bar_chart(
            labels=constraint_names,
            values=failure_counts,
            title="DXY_CONTINUATION Constraint Failure Counts",
            xlabel="Constraint",
            ylabel="Failures",
            color=COLORS["fail"],
        )
        html += f'<div class="chart-container">{fig_bar.to_html(include_plotlyjs=False, div_id="constraint_failures")}</div>'

        # Failure table
        html += """
        <h3>Constraint Pass/Fail Rates</h3>
        <table>
            <thead>
                <tr>
                    <th>Constraint</th>
                    <th>Failures</th>
                    <th>Pass Rate</th>
                    <th>Example Reason</th>
                </tr>
            </thead>
            <tbody>
"""

        for constraint_name in constraint_names:
            stats = constraints[constraint_name]
            html += f"""
                <tr>
                    <td>{constraint_name}</td>
                    <td>{stats['failure_count']}</td>
                    <td>{stats['pass_rate']*100:.1f}%</td>
                    <td>{stats['example_reason'][:80]}...</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
"""

        return html

    def _generate_scoring_factors_tab(self) -> str:
        """Generate scoring factors analysis tab."""
        if self.features_df is None:
            return ""

        html = "<h2>🎯 Scoring Factor Analysis</h2>"

        scoring = self.analyze_scoring_factors()

        # BOS recency distribution
        if scoring.get("bos_recency"):
            bos = scoring["bos_recency"]
            html += f"""
        <h3>BOS Recency Distribution</h3>
        <div class="info">
            <strong>Scoring Impact:</strong><br>
            Fresh (≤10 bars): {bos['fresh_pct']:.1f}% → Full bonus (1.0 points)<br>
            Recent (11-20 bars): {bos['recent_pct']:.1f}% → Partial bonus (0.5 points)<br>
            Stale (>20 bars): {bos['stale_pct']:.1f}% → No bonus (0 points)<br>
            <br>
            Mean BOS age: {bos['mean_age']:.1f} bars | Median: {bos['median_age']:.1f} bars | P95: {bos['p95_age']:.1f} bars
        </div>
"""

            if "bos_age" in self.features_df.columns:
                fig_bos = create_histogram_with_kde(
                    self.features_df["bos_age"],
                    title="BOS Age Distribution",
                    xlabel="Bars Since BOS",
                )
                fig_bos.add_vline(x=10, line_dash="dash", line_color="green", annotation_text="Fresh (10)")
                fig_bos.add_vline(x=20, line_dash="dash", line_color="orange", annotation_text="Recent (20)")
                html += f'<div class="chart-container">{fig_bos.to_html(include_plotlyjs=False, div_id="hist_bos_age")}</div>'

        # Clarity distribution
        if scoring.get("clarity"):
            clarity = scoring["clarity"]
            html += f"""
        <h3>Structure Clarity Distribution</h3>
        <div class="info">
            <strong>Scoring Impact:</strong><br>
            Excellent (≥0.7): {clarity['excellent_pct']:.1f}% → Full bonus (1.0 points)<br>
            Good (0.5-0.7): {clarity['good_pct']:.1f}% → Partial bonus (0.7 points)<br>
            Acceptable (0.3-0.5): {clarity['acceptable_pct']:.1f}% → Minimal bonus (0.4 points)<br>
            Poor (<0.3): {clarity['poor_pct']:.1f}% → No bonus (0 points)<br>
            <br>
            Mean clarity: {clarity['mean']:.3f} | Median: {clarity['median']:.3f}
        </div>
"""

            if "structure_clarity" in self.features_df.columns:
                fig_clarity = create_histogram_with_kde(
                    self.features_df["structure_clarity"],
                    title="Structure Clarity Distribution",
                    xlabel="Clarity Score",
                )
                fig_clarity.add_vline(x=0.3, line_dash="dash", line_color="red", annotation_text="Acceptable (0.3)")
                fig_clarity.add_vline(x=0.5, line_dash="dash", line_color="orange", annotation_text="Good (0.5)")
                fig_clarity.add_vline(x=0.7, line_dash="dash", line_color="green", annotation_text="Excellent (0.7)")
                html += f'<div class="chart-container">{fig_clarity.to_html(include_plotlyjs=False, div_id="hist_clarity")}</div>'

        # Wick-chop analysis
        if scoring.get("wick_chop"):
            wick = scoring["wick_chop"]
            html += f"""
        <h3>Wick-Chop Analysis</h3>
        <div class="info">
            <strong>Wick-Body Ratio (total_wick / body):</strong><br>
            Clean (ratio < 1.5): {wick['clean_pct']:.1f}% → No wick-chop<br>
            Excessive (ratio > 3.0): {wick['excessive_pct']:.1f}% → HARD REJECT<br>
            <br>
            Mean ratio: {wick['mean_ratio']:.2f} | Median: {wick['median_ratio']:.2f}
        </div>
"""

        return html

    def _generate_temporal_patterns_tab(self) -> str:
        """Generate temporal patterns tab."""
        if self.features_df is None:
            return ""

        html = "<h2>⏰ Temporal Patterns</h2>"

        # Time-series for correlations
        for feature in ["dxy_corr", "dxy_5m_corr"]:
            if feature not in self.features_df.columns:
                continue

            fig_ts = create_time_series(
                self.features_df,
                timestamp_col="timestamp",
                value_col=feature,
                title=f"{feature} Over Time",
                ylabel=feature,
                session_markers=True,
            )
            html += f'<div class="chart-container">{fig_ts.to_html(include_plotlyjs=False, div_id=f"ts_{feature}")}</div>'

        # Intraday heatmap for correlation
        for feature in ["dxy_corr", "structure_clarity"]:
            if feature not in self.features_df.columns:
                continue

            fig_heatmap = create_intraday_heatmap(
                self.features_df,
                timestamp_col="timestamp",
                value_col=feature,
                title=f"{feature} Intraday Heatmap",
            )
            html += f'<div class="chart-container">{fig_heatmap.to_html(include_plotlyjs=False, div_id=f"heatmap_{feature}")}</div>'

        return html

    def _generate_correlations_tab(self) -> str:
        """Generate correlations tab."""
        corr_matrix = self.analyze_feature_correlations()

        if corr_matrix.empty:
            return ""

        html = "<h2>📈 Feature Correlations</h2>"

        fig_corr = create_correlation_heatmap(corr_matrix)
        html += f'<div class="chart-container">{fig_corr.to_html(include_plotlyjs=False, div_id="correlation_heatmap")}</div>'

        # List strong correlations
        html += "<h3>Notable Correlations (|r| > 0.4)</h3><ul>"
        for i in range(len(corr_matrix.columns)):
            for j in range(i + 1, len(corr_matrix.columns)):
                corr_value = corr_matrix.iloc[i, j]
                if abs(corr_value) > 0.4:
                    feat1 = corr_matrix.columns[i]
                    feat2 = corr_matrix.columns[j]
                    html += f"<li><strong>{feat1}</strong> vs <strong>{feat2}</strong>: r = {corr_value:.3f}</li>"
        html += "</ul>"

        return html

    def _generate_anomalies_tab(self) -> str:
        """Generate anomalies tab."""
        if self.anomalies is None or len(self.anomalies) == 0:
            return ""

        html = f"<h2>🚨 Anomalies Detected ({len(self.anomalies)} total)</h2>"

        # Anomaly timeline
        fig_anomaly = go.Figure()
        fig_anomaly.add_trace(
            go.Scatter(
                x=self.anomalies["timestamp"],
                y=self.anomalies["value"],
                mode="markers",
                marker=dict(
                    size=10,
                    color=COLORS["fail"],
                    symbol="x",
                ),
                text=self.anomalies["feature"],
                hovertemplate="<b>%{text}</b><br>Value: %{y:.3f}<br>Time: %{x}<extra></extra>",
            )
        )
        fig_anomaly.update_layout(
            title="Anomaly Timeline",
            xaxis_title="Timestamp",
            yaxis_title="Feature Value",
            template="plotly_white",
        )
        html += f'<div class="chart-container">{fig_anomaly.to_html(include_plotlyjs=False, div_id="anomaly_timeline")}</div>'

        # Anomaly table (first 50)
        html += """
        <h3>Anomaly Details (First 50)</h3>
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Feature</th>
                    <th>Value</th>
                    <th>Severity</th>
                </tr>
            </thead>
            <tbody>
"""

        for _, row in self.anomalies.head(50).iterrows():
            html += f"""
                <tr>
                    <td>{row['timestamp']}</td>
                    <td>{row['feature']}</td>
                    <td>{row['value']:.3f}</td>
                    <td>{row['severity']}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
"""

        return html

    def _generate_recommendations_section(self) -> str:
        """Generate recommendations based on analysis."""
        html = "<h2>💡 Recommendations</h2>"

        recommendations = []
        warnings = []
        successes = []

        # Check correlation quality
        corr_quality = self.analyze_correlation_quality()
        if corr_quality.get("dual_correlation", {}).get("both_negative_pct", 0) < 50:
            recommendations.append(
                "<strong>DXY Correlation:</strong> Less than 50% of observations have both correlations negative. "
                "Consider widening the correlation window or accepting weaker correlations."
            )
        elif corr_quality.get("dual_correlation", {}).get("both_strong_pct", 0) > 20:
            successes.append(
                "<strong>Strong Correlation:</strong> "
                f"{corr_quality['dual_correlation']['both_strong_pct']:.1f}% of observations have strong inverse correlation."
            )

        # Check for high failure rate constraints
        if self.constraint_stats:
            for constraint_name, stats in self.constraint_stats["constraints"].items():
                failure_rate = 1 - stats["pass_rate"]
                if failure_rate > 0.5:
                    warnings.append(
                        f"<strong>{constraint_name}</strong>: {failure_rate*100:.1f}% failure rate. "
                        f"This constraint may be too restrictive."
                    )
                elif failure_rate > 0.3:
                    recommendations.append(
                        f"<strong>{constraint_name}</strong>: {failure_rate*100:.1f}% failure rate. "
                        f"Consider reviewing threshold or logic."
                    )

        # Check scoring factor distributions
        scoring = self.analyze_scoring_factors()
        if scoring.get("bos_recency", {}).get("stale_pct", 0) > 60:
            recommendations.append(
                "<strong>BOS Recency:</strong> Most BOS signals are stale (>20 bars). "
                "Consider increasing the BOS recency threshold for partial bonus."
            )

        if scoring.get("clarity", {}).get("poor_pct", 0) > 30:
            warnings.append(
                "<strong>Structure Clarity:</strong> "
                f"{scoring['clarity']['poor_pct']:.1f}% of observations have poor clarity (<0.3). "
                "This reduces scoring potential."
            )

        # Check feature availability
        if self.feature_stats:
            for feature, stats in self.feature_stats.items():
                null_pct = stats.get("null_pct", 0)
                if null_pct > 30:
                    warnings.append(
                        f"<strong>{feature}</strong>: {null_pct:.1f}% null values. "
                        f"Check feature computation or data pipeline."
                    )

        # Render recommendations
        for warn in warnings:
            html += f'<div class="warning">{warn}</div>'

        for rec in recommendations:
            html += f'<div class="recommendation">{rec}</div>'

        for success in successes[:3]:
            html += f'<div class="success">{success}</div>'

        if not recommendations and not warnings:
            html += '<div class="success">No major issues detected. DXY correlation features look healthy!</div>'

        return html

    def _generate_html_footer(self) -> str:
        """Generate HTML footer."""
        return """
    </div>
</body>
</html>
"""

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
        import json

        print(f"Exporting JSON report to {output_path}...")

        report: dict[str, Any] = {
            "metadata": {
                "report_type": "dxy_continuation_feature_eda",
                "period": {"start": start_date, "end": end_date},
                "generated": datetime.now().isoformat(),
                "symbol": "GC",
                "setup_type": "DXY_CONTINUATION",
            },
            "summary": {},
            "correlation_quality": {},
            "structure_alignment": {},
            "feature_statistics": {},
            "constraint_analysis": {},
            "scoring_factors": {},
            "temporal_patterns": {},
            "correlations": {},
            "anomalies": [],
            "recommendations": [],
        }

        # Summary
        if self.features_df is not None:
            report["summary"] = {
                "total_records": len(self.features_df),
                "days_analyzed": int(
                    (self.features_df["timestamp"].max() - self.features_df["timestamp"].min()).days
                ),
                "date_range": {
                    "start": self.features_df["timestamp"].min().isoformat(),
                    "end": self.features_df["timestamp"].max().isoformat(),
                },
            }

            if self.constraint_stats:
                report["summary"]["dxy_continuation_signals"] = self.constraint_stats.get("dxy_continuation_signals", 0)
                report["summary"]["total_rejections"] = self.constraint_stats["total_rejections"]

        # Correlation quality
        report["correlation_quality"] = self.analyze_correlation_quality()

        # Structure alignment
        report["structure_alignment"] = self.analyze_structure_alignment()

        # Feature statistics
        if self.feature_stats:
            report["feature_statistics"] = self.feature_stats

        # Constraint analysis
        if self.constraint_stats:
            report["constraint_analysis"] = self.constraint_stats

        # Scoring factors
        report["scoring_factors"] = self.analyze_scoring_factors()

        # Temporal patterns
        report["temporal_patterns"] = self.analyze_temporal_patterns()

        # Correlations
        corr_matrix = self.analyze_feature_correlations()
        if not corr_matrix.empty:
            report["correlations"] = {
                "matrix": corr_matrix.to_dict(),
                "notable_correlations": [],
            }
            for i in range(len(corr_matrix.columns)):
                for j in range(i + 1, len(corr_matrix.columns)):
                    corr_value = corr_matrix.iloc[i, j]
                    if abs(corr_value) > 0.4:
                        report["correlations"]["notable_correlations"].append({
                            "feature_1": corr_matrix.columns[i],
                            "feature_2": corr_matrix.columns[j],
                            "correlation": float(corr_value),
                        })

        # Anomalies
        if self.anomalies is not None and len(self.anomalies) > 0:
            report["anomalies"] = [
                {
                    "timestamp": row["timestamp"].isoformat(),
                    "feature": row["feature"],
                    "value": float(row["value"]),
                    "severity": row["severity"],
                }
                for _, row in self.anomalies.iterrows()
            ]

        # Recommendations
        recommendations = []

        # Check correlation quality
        corr_quality = report["correlation_quality"]
        if corr_quality.get("dual_correlation", {}).get("both_negative_pct", 0) < 50:
            recommendations.append({
                "type": "correlation_quality",
                "metric": "both_negative_pct",
                "value": corr_quality["dual_correlation"]["both_negative_pct"],
                "suggestion": "Consider widening correlation window or accepting weaker correlations",
            })

        # Check constraint failures
        if self.constraint_stats:
            for constraint_name, stats in self.constraint_stats["constraints"].items():
                failure_rate = 1 - stats["pass_rate"]
                if failure_rate > 0.3:
                    recommendations.append({
                        "type": "constraint_tuning",
                        "constraint": constraint_name,
                        "failure_rate": float(failure_rate),
                        "suggestion": "Consider relaxing threshold or reviewing constraint logic",
                    })

        # Check feature availability
        if self.feature_stats:
            for feature, stats in self.feature_stats.items():
                null_pct = stats.get("null_pct", 0)
                if null_pct > 30:
                    recommendations.append({
                        "type": "data_quality",
                        "feature": feature,
                        "null_percentage": float(null_pct),
                        "suggestion": "Check feature computation or data pipeline",
                    })

        report["recommendations"] = recommendations

        # Write JSON
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(report, indent=2, default=str))

        print(f"✓ JSON report saved to: {output_path}")


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive EDA for DXY_CONTINUATION features and constraints"
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
        help="Output HTML path (default: reports/dxy_eda_{start}_{end}.html)",
    )
    parser.add_argument(
        "--symbol",
        default="GC",
        help="Symbol to analyze (default: GC)",
    )
    parser.add_argument(
        "--detect-anomalies",
        action="store_true",
        help="Enable anomaly detection",
    )
    parser.add_argument(
        "--anomaly-method",
        default="zscore",
        choices=["zscore", "iqr"],
        help="Anomaly detection method (default: zscore)",
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

    # Set default output path
    output_path = args.output or f"reports/dxy_eda_{args.start}_{args.end}.html"

    # Run EDA
    eda = DXYFeatureEDA(db_url)

    # Load data
    await eda.load_data(args.start, args.end, symbol=args.symbol)

    if eda.features_df is None or len(eda.features_df) == 0:
        print("No features data found for the specified date range.")
        sys.exit(1)

    # Analyze
    eda.analyze_feature_distributions()
    eda.analyze_correlation_quality()
    eda.analyze_structure_alignment()
    eda.analyze_constraint_failures()
    eda.analyze_scoring_factors()
    eda.analyze_temporal_patterns()
    eda.analyze_feature_correlations()

    if args.detect_anomalies:
        eda.detect_anomalies(method=args.anomaly_method)

    # Export reports
    json_path = output_path.replace(".html", ".json")
    export_json = args.json and not args.no_json

    if not args.json_only:
        eda.export_html_report(output_path, args.start, args.end)

    if export_json or args.json_only:
        eda.export_json_report(json_path, args.start, args.end)

    print(f"\n✅ DXY_CONTINUATION EDA complete!")
    if not args.json_only:
        print(f"   HTML report: {output_path}")
    if export_json or args.json_only:
        print(f"   JSON report: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
