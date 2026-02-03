"""
Comprehensive EDA (Exploratory Data Analysis) for VWAP_RECLAIM features and constraints.

This script analyzes:
1. Feature distributions and statistics
2. Constraint failure patterns
3. Threshold optimization
4. Temporal patterns
5. Anomaly detection
6. Feature correlations

Usage:
    python scripts/eda/eda_vwap_features.py --start 2025-11-05 --end 2025-11-10
    python scripts/eda/eda_vwap_features.py --start 2025-11-05 --end 2025-11-10 --detect-anomalies
    make eda-vwap START=2025-11-05 END=2025-11-10
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
    load_features,
    load_signal_history,
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


class VWAPFeatureEDA:
    """Exploratory Data Analysis for VWAP_RECLAIM features and constraints."""

    # Feature columns to analyze
    VWAP_FEATURES = [
        "vwap_deviation",
        "vwap_deviation_normalized",
        "max_abs_deviation_last_20",
        "min_abs_deviation_last_20",
        "bars_near_vwap",
        "near_vwap_count_last_20",  # Rolling VWAP acceptance count
        "bars_since_last_vwap_touch",
        "atr",
        "vwap_slope",
    ]

    # Constraints from config/setups.yaml
    VWAP_CONSTRAINTS = {
        "structure_1h_available": {
            "fields": ["structure_1h"],
            "type": "categorical",
        },
        "htf_structure_integrity": {
            "fields": ["structure_1h", "direction"],
            "type": "categorical",
        },
        "structure_label_available": {
            "fields": ["structure_label"],
            "type": "categorical",
        },
        "vwap_reclaim_distance": {
            "fields": ["max_abs_deviation_last_20"],
            "type": "numeric",
            "bounds": (0.5, 8.0),
        },
        "vwap_reclaim_current_distance": {
            "fields": ["vwap_deviation_normalized"],
            "type": "numeric",
            "bounds": (None, 2.0),
        },
        "no_late_reclaim": {
            "fields": ["bos_recent", "bos_age"],
            "type": "categorical",
        },
        "bos_reclaim_gate": {
            "fields": ["bos_direction", "bos_age", "direction"],
            "type": "categorical",
        },
        "direction_bos_alignment": {
            "fields": ["bos_direction", "bos_age", "direction", "choch_detected", "choch_direction"],
            "type": "categorical",
        },
        "no_structure_conflict": {
            "fields": ["conflict_detected"],
            "type": "categorical",
        },
        "min_vwap_acceptance": {
            "fields": ["near_vwap_count_last_20"],
            "type": "numeric",
            "bounds": (3, None),
        },
        "reclaim_timing_gate": {
            "fields": ["bars_since_last_vwap_touch"],
            "type": "numeric",
            "bounds": (None, 30),
        },
        "structure_label_direction_long": {
            "fields": ["structure_label", "direction"],
            "type": "categorical",
        },
        "structure_label_direction_short": {
            "fields": ["structure_label", "direction"],
            "type": "categorical",
        },
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
        self.features_df = await load_features(
            self.db_url,
            start_date,
            end_date,
            symbol=symbol,
        )
        print(f"  Loaded {len(self.features_df)} feature records")

        print(f"Loading signal history data from {start_date} to {end_date}...")
        self.signal_history_df = await load_signal_history(
            self.db_url,
            start_date,
            end_date,
        )
        print(f"  Loaded {len(self.signal_history_df)} signal records")

    def analyze_feature_distributions(self) -> dict[str, Any]:
        """
        Analyze statistical distributions for all VWAP features.

        Returns:
            Dictionary with statistics for each feature
        """
        if self.features_df is None or len(self.features_df) == 0:
            return {}

        print("Analyzing feature distributions...")
        stats_dict = {}

        for feature in self.VWAP_FEATURES:
            if feature not in self.features_df.columns:
                continue

            data = self.features_df[feature].dropna()
            if len(data) == 0:
                stats_dict[feature] = {"count": 0, "null_pct": 100.0}
                continue

            stats_dict[feature] = {
                "count": len(data),
                "null_count": self.features_df[feature].isna().sum(),
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

    def analyze_constraint_failures(self) -> dict[str, Any]:
        """
        Analyze constraint pass/fail rates and failure patterns.

        Returns:
            Dictionary with constraint failure statistics
        """
        if self.signal_history_df is None or len(self.signal_history_df) == 0:
            return {}

        print("Analyzing constraint failures...")

        # Filter to rejections with vwap_reclaim_validation diagnostics
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
            "constraints": constraint_stats,
        }

        return self.constraint_stats

    def analyze_threshold_optimization(
        self,
        constraint_name: str,
    ) -> dict[str, Any]:
        """
        Simulate different threshold values to find optimal pass rates.

        Args:
            constraint_name: Name of constraint to optimize

        Returns:
            Dictionary with threshold optimization results
        """
        if self.features_df is None or len(self.features_df) == 0:
            return {}

        if constraint_name not in self.VWAP_CONSTRAINTS:
            return {}

        constraint_info = self.VWAP_CONSTRAINTS[constraint_name]
        if constraint_info["type"] != "numeric":
            return {}

        print(f"Optimizing thresholds for {constraint_name}...")

        field = constraint_info["fields"][0]
        if field not in self.features_df.columns:
            return {}

        data = self.features_df[field].dropna()
        if len(data) == 0:
            return {}

        bounds = constraint_info["bounds"]
        lower_bound, upper_bound = bounds

        # Determine threshold range to test
        if constraint_name == "vwap_reclaim_distance":
            # Test upper bound variations (0.5 to 12.0 ATR)
            thresholds = np.arange(0.5, 12.5, 0.5)
            pass_rates = []
            for threshold in thresholds:
                if lower_bound is not None:
                    passed = ((data >= lower_bound) & (data <= threshold)).sum()
                else:
                    passed = (data <= threshold).sum()
                pass_rates.append(passed / len(data))

            current_threshold = 8.0

        elif constraint_name == "vwap_reclaim_current_distance":
            # Test upper bound variations (0.5 to 5.0 ATR)
            thresholds = np.arange(0.5, 5.5, 0.25)
            pass_rates = []
            for threshold in thresholds:
                passed = (np.abs(data) <= threshold).sum()
                pass_rates.append(passed / len(data))

            current_threshold = 2.0

        elif constraint_name == "min_vwap_acceptance":
            # Test lower bound variations (1 to 10 bars)
            thresholds = np.arange(1, 11, 1)
            pass_rates = []
            for threshold in thresholds:
                passed = (data >= threshold).sum()
                pass_rates.append(passed / len(data))

            current_threshold = 3

        elif constraint_name == "reclaim_timing_gate":
            # Test upper bound variations (5 to 20 bars)
            thresholds = np.arange(5, 21, 1)
            pass_rates = []
            for threshold in thresholds:
                passed = (data <= threshold).sum()
                pass_rates.append(passed / len(data))

            current_threshold = 10

        else:
            return {}

        return {
            "constraint_name": constraint_name,
            "field": field,
            "thresholds": thresholds.tolist(),
            "pass_rates": [float(pr) for pr in pass_rates],
            "current_threshold": float(current_threshold),
            "current_pass_rate": float(pass_rates[np.argmin(np.abs(thresholds - current_threshold))]),
        }

    def analyze_temporal_patterns(self) -> dict[str, Any]:
        """
        Analyze temporal patterns in features (intraday, multi-day).

        Returns:
            Dictionary with temporal pattern statistics
        """
        if self.features_df is None or len(self.features_df) == 0:
            return {}

        print("Analyzing temporal patterns...")

        df = self.features_df.copy()
        df["hour"] = df["timestamp"].dt.hour
        df["date"] = df["timestamp"].dt.date

        # Compute hourly statistics for key features
        hourly_stats = {}
        for feature in ["vwap_deviation_normalized", "bars_near_vwap", "atr"]:
            if feature not in df.columns:
                continue

            hourly = df.groupby("hour")[feature].agg(["mean", "std", "count"])
            hourly_stats[feature] = hourly.to_dict("index")

        return {
            "hourly_stats": hourly_stats,
            "total_days": int(df["date"].nunique()),
            "hours_covered": sorted(df["hour"].unique().tolist()),
        }

    def analyze_feature_correlations(self) -> pd.DataFrame:
        """
        Compute Pearson correlation matrix for numeric features.

        Returns:
            Correlation matrix DataFrame
        """
        if self.features_df is None or len(self.features_df) == 0:
            return pd.DataFrame()

        print("Computing feature correlations...")

        # Select numeric columns
        numeric_cols = [
            col
            for col in self.VWAP_FEATURES
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
        Detect anomalies in feature values.

        Args:
            method: Detection method ('zscore' or 'iqr')
            threshold: Z-score threshold (default: 3.0) or IQR multiplier (default: 1.5)

        Returns:
            DataFrame with anomaly records
        """
        if self.features_df is None or len(self.features_df) == 0:
            return pd.DataFrame()

        print(f"Detecting anomalies using {method} method...")

        anomaly_records = []

        for feature in self.VWAP_FEATURES:
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

    def generate_interactive_dashboard(self) -> go.Figure:
        """
        Generate multi-tab interactive Plotly dashboard.

        Returns:
            Plotly Figure with all visualizations
        """
        print("Generating interactive dashboard...")

        # This will be implemented in the HTML export
        # For now, return a placeholder
        fig = go.Figure()
        fig.add_annotation(
            text="Dashboard will be embedded in HTML report",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=20),
        )

        return fig

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

        # Tab 1: Overview
        html_parts.append(self._generate_overview_tab())

        # Tab 2: Feature Distributions
        html_parts.append(self._generate_feature_distributions_tab())

        # Tab 3: Constraint Analysis
        html_parts.append(self._generate_constraint_analysis_tab())

        # Tab 4: Temporal Patterns
        html_parts.append(self._generate_temporal_patterns_tab())

        # Tab 5: Correlations
        html_parts.append(self._generate_correlations_tab())

        # Tab 6: Anomalies (if detected)
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
    <title>VWAP Feature EDA Report - {start_date} to {end_date}</title>
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
            border-bottom: 3px solid #3498db;
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            margin: 10px;
            border-radius: 8px;
            min-width: 200px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
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
            background-color: #3498db;
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
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 VWAP Feature EDA Report</h1>
        <p><strong>Analysis Period:</strong> {start_date} to {end_date}</p>
        <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
"""

    def _generate_summary_section(self) -> str:
        """Generate summary statistics section."""
        if self.features_df is None or self.feature_stats is None:
            return "<p>No data available for summary.</p>"

        total_features = len(self.features_df)
        date_range_days = (self.features_df["timestamp"].max() - self.features_df["timestamp"].min()).days

        html = f"""
        <h2>📊 Summary Statistics</h2>
        <div class="metric-card">
            <div class="metric-value">{total_features:,}</div>
            <div class="metric-label">Total Feature Records</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{date_range_days}</div>
            <div class="metric-label">Days Analyzed</div>
        </div>
"""

        if self.constraint_stats:
            pass_rate = (
                self.constraint_stats["total_approved"] / self.constraint_stats["total_evaluated"] * 100
                if self.constraint_stats["total_evaluated"] > 0
                else 0
            )
            html += f"""
        <div class="metric-card">
            <div class="metric-value">{pass_rate:.1f}%</div>
            <div class="metric-label">Signal Pass Rate</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{self.constraint_stats["total_rejections"]}</div>
            <div class="metric-label">Total Rejections</div>
        </div>
"""

        html += "</div>"
        return html

    def _generate_overview_tab(self) -> str:
        """Generate overview tab."""
        if self.feature_stats is None:
            return ""

        # Feature availability table
        html = """
        <h2>📋 Feature Availability</h2>
        <table>
            <thead>
                <tr>
                    <th>Feature</th>
                    <th>Count</th>
                    <th>Null Count</th>
                    <th>Null %</th>
                    <th>Mean</th>
                    <th>Median</th>
                    <th>Std Dev</th>
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
                    <td>{stats['null_count']}</td>
                    <td>100.0%</td>
                    <td>-</td>
                    <td>-</td>
                    <td>-</td>
                </tr>
"""
            else:
                html += f"""
                <tr>
                    <td>{feature}</td>
                    <td>{stats['count']:,}</td>
                    <td>{stats['null_count']:,}</td>
                    <td>{stats['null_pct']:.1f}%</td>
                    <td>{stats['mean']:.3f}</td>
                    <td>{stats['median']:.3f}</td>
                    <td>{stats['std']:.3f}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
"""
        return html

    def _generate_feature_distributions_tab(self) -> str:
        """Generate feature distributions tab with charts."""
        if self.features_df is None or self.feature_stats is None:
            return ""

        html = "<h2>📈 Feature Distributions</h2>"

        for feature in self.VWAP_FEATURES:
            if feature not in self.features_df.columns:
                continue

            # Skip if no data
            if self.feature_stats.get(feature, {}).get("count", 0) == 0:
                continue

            # Histogram
            fig_hist = create_histogram_with_kde(
                self.features_df[feature],
                title=f"{feature} Distribution",
                xlabel=feature,
            )
            html += f'<div class="chart-container">{fig_hist.to_html(include_plotlyjs=False, div_id=f"hist_{feature}")}</div>'

            # Box plot by direction
            if "direction" in self.features_df.columns:
                fig_box = create_box_plot_by_group(
                    self.features_df,
                    value_col=feature,
                    group_col="direction",
                    title=f"{feature} by Direction",
                    ylabel=feature,
                )
                html += f'<div class="chart-container">{fig_box.to_html(include_plotlyjs=False, div_id=f"box_{feature}")}</div>'

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
            title="Constraint Failure Counts",
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
                    <td>{stats['example_reason']}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
"""

        # Threshold optimization curves
        for constraint_name in ["vwap_reclaim_distance", "min_vwap_acceptance", "reclaim_timing_gate"]:
            optimization = self.analyze_threshold_optimization(constraint_name)
            if optimization:
                thresholds = np.array(optimization["thresholds"])
                pass_rates = np.array(optimization["pass_rates"])
                current_threshold = optimization["current_threshold"]

                fig_opt = create_threshold_optimization_curve(
                    thresholds=thresholds,
                    pass_rates=pass_rates,
                    current_threshold=current_threshold,
                    title=f"Threshold Optimization: {constraint_name}",
                    xlabel=optimization["field"],
                )
                html += f'<div class="chart-container">{fig_opt.to_html(include_plotlyjs=False, div_id=f"opt_{constraint_name}")}</div>'

        return html

    def _generate_temporal_patterns_tab(self) -> str:
        """Generate temporal patterns tab."""
        if self.features_df is None:
            return ""

        html = "<h2>⏰ Temporal Patterns</h2>"

        # Time-series for key features
        for feature in ["vwap_deviation_normalized", "bars_near_vwap", "atr"]:
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

        # Intraday heatmap
        for feature in ["vwap_deviation_normalized", "bars_near_vwap"]:
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

        html = "<h2>🔗 Feature Correlations</h2>"

        fig_corr = create_correlation_heatmap(corr_matrix)
        html += f'<div class="chart-container">{fig_corr.to_html(include_plotlyjs=False, div_id="correlation_heatmap")}</div>'

        # List strong correlations
        html += "<h3>Strong Correlations (|r| > 0.6)</h3><ul>"
        for i in range(len(corr_matrix.columns)):
            for j in range(i + 1, len(corr_matrix.columns)):
                corr_value = corr_matrix.iloc[i, j]
                if abs(corr_value) > 0.6:
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

        # Check for high failure rate constraints
        if self.constraint_stats:
            for constraint_name, stats in self.constraint_stats["constraints"].items():
                failure_rate = 1 - stats["pass_rate"]
                if failure_rate > 0.3:
                    recommendations.append(
                        f"<strong>{constraint_name}</strong>: {failure_rate*100:.1f}% failure rate. "
                        f"Consider relaxing threshold or reviewing constraint logic."
                    )

        # Check for high null percentage features
        if self.feature_stats:
            for feature, stats in self.feature_stats.items():
                null_pct = stats.get("null_pct", 0)
                if null_pct > 20:
                    warnings.append(
                        f"<strong>{feature}</strong>: {null_pct:.1f}% null values. "
                        f"Check feature computation or data pipeline."
                    )
                elif null_pct < 5:
                    successes.append(
                        f"<strong>{feature}</strong>: {null_pct:.1f}% null values (good coverage)."
                    )

        # Render recommendations
        for rec in recommendations:
            html += f'<div class="recommendation">{rec}</div>'

        for warn in warnings:
            html += f'<div class="warning">{warn}</div>'

        for success in successes[:3]:  # Show top 3
            html += f'<div class="success">{success}</div>'

        if not recommendations and not warnings:
            html += '<div class="success">No major issues detected. All constraints and features look healthy!</div>'

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
                "report_type": "vwap_feature_eda",
                "period": {"start": start_date, "end": end_date},
                "generated": datetime.now().isoformat(),
                "symbol": "GC",
            },
            "summary": {},
            "feature_statistics": {},
            "constraint_analysis": {},
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
                report["summary"]["signal_pass_rate"] = (
                    self.constraint_stats["total_approved"]
                    / self.constraint_stats["total_evaluated"]
                    if self.constraint_stats["total_evaluated"] > 0
                    else 0
                )
                report["summary"]["total_rejections"] = self.constraint_stats["total_rejections"]
                report["summary"]["total_approved"] = self.constraint_stats["total_approved"]

        # Feature statistics
        if self.feature_stats:
            report["feature_statistics"] = self.feature_stats

        # Constraint analysis
        if self.constraint_stats:
            report["constraint_analysis"] = self.constraint_stats

        # Temporal patterns
        temporal = self.analyze_temporal_patterns()
        if temporal:
            report["temporal_patterns"] = temporal

        # Correlations
        corr_matrix = self.analyze_feature_correlations()
        if not corr_matrix.empty:
            # Convert to dict format
            report["correlations"] = {
                "matrix": corr_matrix.to_dict(),
                "strong_correlations": [],
            }
            # Find strong correlations
            for i in range(len(corr_matrix.columns)):
                for j in range(i + 1, len(corr_matrix.columns)):
                    corr_value = corr_matrix.iloc[i, j]
                    if abs(corr_value) > 0.6:
                        report["correlations"]["strong_correlations"].append({
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

        if self.feature_stats:
            for feature, stats in self.feature_stats.items():
                null_pct = stats.get("null_pct", 0)
                if null_pct > 20:
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
        description="Comprehensive EDA for VWAP_RECLAIM features and constraints"
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
        help="Output HTML path (default: reports/vwap_eda_{start}_{end}.html)",
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
    output_path = args.output or f"reports/vwap_eda_{args.start}_{args.end}.html"

    # Run EDA
    eda = VWAPFeatureEDA(db_url)

    # Load data
    await eda.load_data(args.start, args.end, symbol=args.symbol)

    if eda.features_df is None or len(eda.features_df) == 0:
        print("No features data found for the specified date range.")
        sys.exit(1)

    # Analyze
    eda.analyze_feature_distributions()
    eda.analyze_constraint_failures()
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

    print(f"\n✅ EDA complete!")
    if not args.json_only:
        print(f"   HTML report: {output_path}")
    if export_json or args.json_only:
        print(f"   JSON report: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
