"""Reusable Plotly chart builders for EDA visualizations."""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Any
from scipy import stats as scipy_stats


# Color scheme
COLORS = {
    "pass": "#2ecc71",  # Green
    "fail": "#e74c3c",  # Red
    "neutral": "#3498db",  # Blue
    "warning": "#f39c12",  # Orange
    "long": "#2ecc71",  # Green
    "short": "#e74c3c",  # Red
}


def create_histogram_with_kde(
    data: pd.Series,
    title: str,
    xlabel: str,
    bins: int = 50,
) -> go.Figure:
    """
    Create histogram with KDE overlay.

    Args:
        data: Series of numeric values
        title: Chart title
        xlabel: X-axis label
        bins: Number of histogram bins

    Returns:
        Plotly Figure
    """
    # Remove nulls
    clean_data = data.dropna()

    if len(clean_data) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="No data available",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
        fig.update_layout(title=title)
        return fig

    # Histogram
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=clean_data,
            nbinsx=bins,
            name="Count",
            marker_color=COLORS["neutral"],
            opacity=0.7,
        )
    )

    # KDE overlay (if enough data points)
    if len(clean_data) > 10:
        try:
            kde = scipy_stats.gaussian_kde(clean_data)
            x_range = np.linspace(clean_data.min(), clean_data.max(), 200)
            kde_values = kde(x_range)

            # Scale KDE to match histogram (approximate)
            kde_scaled = kde_values * len(clean_data) * (clean_data.max() - clean_data.min()) / bins

            fig.add_trace(
                go.Scatter(
                    x=x_range,
                    y=kde_scaled,
                    mode="lines",
                    name="KDE",
                    line=dict(color=COLORS["warning"], width=2),
                    yaxis="y2",
                )
            )

            fig.update_layout(
                yaxis2=dict(
                    overlaying="y",
                    side="right",
                    showgrid=False,
                )
            )
        except Exception:
            # KDE failed, skip it
            pass

    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title="Count",
        template="plotly_white",
        hovermode="x unified",
    )

    return fig


def create_box_plot_by_group(
    df: pd.DataFrame,
    value_col: str,
    group_col: str,
    title: str,
    ylabel: str,
) -> go.Figure:
    """
    Create box plot grouped by category.

    Args:
        df: DataFrame
        value_col: Column name for values
        group_col: Column name for grouping
        title: Chart title
        ylabel: Y-axis label

    Returns:
        Plotly Figure
    """
    fig = go.Figure()

    groups = df[group_col].dropna().unique()
    for group in sorted(groups):
        group_data = df[df[group_col] == group][value_col].dropna()

        color = COLORS.get(str(group), COLORS["neutral"])
        fig.add_trace(
            go.Box(
                y=group_data,
                name=str(group),
                marker_color=color,
                boxmean="sd",
            )
        )

    fig.update_layout(
        title=title,
        yaxis_title=ylabel,
        template="plotly_white",
        showlegend=True,
    )

    return fig


def create_time_series(
    df: pd.DataFrame,
    timestamp_col: str,
    value_col: str,
    title: str,
    ylabel: str,
    session_markers: bool = True,
) -> go.Figure:
    """
    Create time-series plot with optional session markers.

    Args:
        df: DataFrame
        timestamp_col: Column name for timestamps
        value_col: Column name for values
        title: Chart title
        ylabel: Y-axis label
        session_markers: Whether to add session transition markers

    Returns:
        Plotly Figure
    """
    fig = go.Figure()

    # Main time-series
    fig.add_trace(
        go.Scatter(
            x=df[timestamp_col],
            y=df[value_col],
            mode="lines+markers",
            name=value_col,
            line=dict(color=COLORS["neutral"], width=1),
            marker=dict(size=3),
        )
    )

    # Session markers at 08:20 ET (RTH open for Gold)
    if session_markers and len(df) > 0:
        try:
            df_with_time = df.copy()
            df_with_time['hour'] = df_with_time[timestamp_col].dt.hour
            df_with_time['minute'] = df_with_time[timestamp_col].dt.minute

            # Find 08:20 ET timestamps (approximate - depends on timezone)
            session_starts = df_with_time[
                (df_with_time['hour'] == 8) & (df_with_time['minute'] == 20)
            ][timestamp_col]

            for ts in session_starts:
                # Use add_shape for vertical line instead of add_vline
                fig.add_shape(
                    type="line",
                    x0=ts,
                    x1=ts,
                    y0=0,
                    y1=1,
                    yref="paper",
                    line=dict(color="gray", width=1, dash="dash"),
                    opacity=0.5,
                )
        except Exception:
            # Skip session markers if they cause issues
            pass

    fig.update_layout(
        title=title,
        xaxis_title="Timestamp",
        yaxis_title=ylabel,
        template="plotly_white",
        hovermode="x unified",
        xaxis=dict(
            rangeslider=dict(visible=True),
            type="date",
        ),
    )

    return fig


def create_correlation_heatmap(
    corr_matrix: pd.DataFrame,
    title: str = "Feature Correlation Matrix",
) -> go.Figure:
    """
    Create interactive correlation heatmap.

    Args:
        corr_matrix: Correlation matrix DataFrame
        title: Chart title

    Returns:
        Plotly Figure
    """
    fig = go.Figure(
        data=go.Heatmap(
            z=corr_matrix.values,
            x=corr_matrix.columns,
            y=corr_matrix.index,
            colorscale="RdBu_r",
            zmid=0,
            zmin=-1,
            zmax=1,
            text=corr_matrix.values.round(2),
            texttemplate="%{text}",
            textfont={"size": 10},
            colorbar=dict(title="Correlation"),
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="",
        yaxis_title="",
        template="plotly_white",
        height=600,
        width=800,
    )

    return fig


def create_bar_chart(
    labels: list[str],
    values: list[float],
    title: str,
    xlabel: str,
    ylabel: str,
    color: str | None = None,
) -> go.Figure:
    """
    Create bar chart.

    Args:
        labels: Category labels
        values: Bar values
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        color: Bar color (default: neutral blue)

    Returns:
        Plotly Figure
    """
    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color=color or COLORS["neutral"],
                text=values,
                texttemplate="%{text:.0f}",
                textposition="outside",
            )
        ]
    )

    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        template="plotly_white",
    )

    return fig


def create_pie_chart(
    labels: list[str],
    values: list[float],
    title: str,
) -> go.Figure:
    """
    Create pie chart.

    Args:
        labels: Slice labels
        values: Slice values
        title: Chart title

    Returns:
        Plotly Figure
    """
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                textinfo="label+percent",
                marker=dict(colors=[COLORS.get(str(label), COLORS["neutral"]) for label in labels]),
            )
        ]
    )

    fig.update_layout(
        title=title,
        template="plotly_white",
    )

    return fig


def create_threshold_optimization_curve(
    thresholds: np.ndarray,
    pass_rates: np.ndarray,
    current_threshold: float,
    title: str,
    xlabel: str,
) -> go.Figure:
    """
    Create threshold vs pass rate optimization curve.

    Args:
        thresholds: Array of threshold values tested
        pass_rates: Array of corresponding pass rates
        current_threshold: Current threshold value (highlighted)
        title: Chart title
        xlabel: X-axis label

    Returns:
        Plotly Figure
    """
    fig = go.Figure()

    # Pass rate curve
    fig.add_trace(
        go.Scatter(
            x=thresholds,
            y=pass_rates * 100,  # Convert to percentage
            mode="lines+markers",
            name="Pass Rate",
            line=dict(color=COLORS["neutral"], width=2),
        )
    )

    # Highlight current threshold
    current_idx = np.argmin(np.abs(thresholds - current_threshold))
    fig.add_trace(
        go.Scatter(
            x=[thresholds[current_idx]],
            y=[pass_rates[current_idx] * 100],
            mode="markers",
            name=f"Current ({current_threshold})",
            marker=dict(color=COLORS["warning"], size=12, symbol="star"),
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title="Pass Rate (%)",
        template="plotly_white",
        hovermode="x unified",
    )

    return fig


def create_intraday_heatmap(
    df: pd.DataFrame,
    timestamp_col: str,
    value_col: str,
    title: str,
) -> go.Figure:
    """
    Create intraday heatmap (hour vs day).

    Args:
        df: DataFrame
        timestamp_col: Column name for timestamps
        value_col: Column name for values to aggregate
        title: Chart title

    Returns:
        Plotly Figure
    """
    # Extract hour and date
    df_copy = df.copy()
    df_copy['hour'] = df_copy[timestamp_col].dt.hour
    df_copy['date'] = df_copy[timestamp_col].dt.date

    # Pivot to create heatmap data
    pivot = df_copy.pivot_table(
        values=value_col,
        index='hour',
        columns='date',
        aggfunc='mean',
    )

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[str(d) for d in pivot.columns],
            y=pivot.index,
            colorscale="Viridis",
            colorbar=dict(title=value_col),
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Hour of Day",
        template="plotly_white",
    )

    return fig
