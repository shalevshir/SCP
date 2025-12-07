"""Chart Component - Price Chart with Candlesticks and VWAP.

This module provides the price chart panel for the dashboard.
"""

from typing import Optional

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc
from plotly.subplots import make_subplots


def create_price_chart() -> dbc.Card:
    """Create the price chart panel.

    Returns:
        Dash Bootstrap Card containing the chart
    """
    return dbc.Card(
        [
            dbc.CardHeader("GC Price Chart (1M)"),
            dbc.CardBody(
                [
                    dcc.Graph(
                        id="price-chart",
                        config={"displayModeBar": False},
                        style={"height": "600px"},
                    )
                ]
            ),
        ]
    )


def render_price_chart(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    vwap_value: Optional[float] = None,
) -> go.Figure:
    """Render the price chart figure.

    Args:
        gc_df: GC price history DataFrame with OHLCV columns
        dxy_df: DXY price history DataFrame
        vwap_value: Current VWAP value for horizontal line

    Returns:
        Plotly figure object
    """
    if gc_df.empty:
        # Return empty chart with styling
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            xaxis_title="Time",
            yaxis_title="Price",
            showlegend=True,
            annotations=[
                dict(
                    text="Waiting for data...",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=20, color="gray"),
                )
            ],
        )
        return fig

    # Create figure with secondary y-axis for DXY
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add GC candlestick trace (primary y-axis)
    fig.add_trace(
        go.Candlestick(
            x=gc_df["timestamp"],
            open=gc_df["open"],
            high=gc_df["high"],
            low=gc_df["low"],
            close=gc_df["close"],
            name="GC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            increasing_fillcolor="#26a69a",
            decreasing_fillcolor="#ef5350",
        ),
        secondary_y=False,
    )

    # Add DXY line trace (secondary y-axis) if available
    if not dxy_df.empty:
        fig.add_trace(
            go.Scatter(
                x=dxy_df["timestamp"],
                y=dxy_df["close"],
                name="DXY",
                line=dict(color="orange", width=2),
                opacity=0.7,
            ),
            secondary_y=True,
        )

    # Add VWAP horizontal line if available
    if vwap_value is not None and not pd.isna(vwap_value):
        fig.add_hline(
            y=float(vwap_value),
            line_dash="dash",
            line_color="cyan",
            annotation_text="VWAP",
            annotation_position="right",
            annotation_font_color="cyan",
        )

    # Update axes labels
    fig.update_xaxes(title_text="Time")
    fig.update_yaxes(title_text="GC Price (USD)", secondary_y=False)
    fig.update_yaxes(title_text="DXY Index", secondary_y=True)

    # Update layout
    fig.update_layout(
        template="plotly_dark",
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(0,0,0,0.5)",
        ),
        xaxis_rangeslider_visible=False,
        height=600,
        hovermode="x unified",
        margin=dict(l=60, r=60, t=30, b=40),
    )

    return fig


def render_chart_with_signals(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    vwap_value: Optional[float] = None,
    signals: Optional[list] = None,
) -> go.Figure:
    """Render price chart with signal markers.

    Args:
        gc_df: GC price history DataFrame
        dxy_df: DXY price history DataFrame
        vwap_value: Current VWAP value
        signals: List of signals to mark on chart (future enhancement)

    Returns:
        Plotly figure object
    """
    # Get base chart
    fig = render_price_chart(gc_df, dxy_df, vwap_value)

    # Add signal markers if provided
    if signals and not gc_df.empty:
        for signal in signals:
            if signal.direction == "long":
                marker_color = "green"
                marker_symbol = "triangle-up"
            elif signal.direction == "short":
                marker_color = "red"
                marker_symbol = "triangle-down"
            else:
                continue  # Skip neutral signals

            # Find the price at signal timestamp
            # This is a placeholder - would need timestamp matching
            fig.add_trace(
                go.Scatter(
                    x=[signal.timestamp],
                    y=[gc_df["close"].iloc[-1]],  # Placeholder
                    mode="markers",
                    marker=dict(
                        color=marker_color,
                        size=15,
                        symbol=marker_symbol,
                    ),
                    name=f"{signal.setup_type} ({signal.confidence})",
                    showlegend=True,
                )
            )

    return fig

