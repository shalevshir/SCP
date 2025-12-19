"""Price Chart with Entry/Exit Markers - Candlestick chart with trade markers."""

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from backtester.replay_loop import BacktestResults
from backtester.trade import Trade
from dash import dcc, html
from plotly.subplots import make_subplots


def create_price_chart_with_markers() -> dbc.Card:
    """Create the price chart panel with entry/exit markers.

    Returns:
        Dash Bootstrap Card containing the chart and controls
    """
    return dbc.Card(
        [
            dbc.CardHeader("Price Chart with Trade Markers"),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Select Trade:", className="me-2"),
                                    dcc.Dropdown(
                                        id="price-chart-trade-selector",
                                        placeholder="Select a trade to view...",
                                        className="mb-2",
                                    ),
                                ],
                                width=12,
                            ),
                        ],
                        className="mb-2",
                    ),
                    dcc.Graph(
                        id="price-chart-with-markers",
                        config={"displayModeBar": True},
                        style={"height": "700px"},
                    ),
                    html.Div(id="price-chart-trade-details", className="mt-2"),
                ]
            ),
        ]
    )


def render_price_chart_with_markers(
    results: BacktestResults,
    gc_df: pd.DataFrame | None,
    selected_trade_id: str | None = None,
    dxy_df: pd.DataFrame | None = None,
) -> go.Figure:
    """Render price chart with entry/exit markers, VWAP, DXY, and volume.

    Args:
        results: BacktestResults object with all trades
        gc_df: GC price DataFrame with OHLCV columns and DatetimeIndex, or None
        selected_trade_id: Optional trade ID to highlight
        dxy_df: Optional DXY price DataFrame for correlation visualization

    Returns:
        Plotly figure with candlesticks, indicators, and trade markers
    """
    if gc_df is None or gc_df.empty:
        # Return empty chart
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            xaxis_title="Time",
            yaxis_title="Price",
            showlegend=True,
            annotations=[
                dict(
                    text="No price data available",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                    showarrow=False,
                    font=dict(size=16, color="gray"),
                )
            ],
        )
        return fig

    # Get timestamps for x-axis
    timestamps = (
        gc_df.index if isinstance(gc_df.index, pd.DatetimeIndex) else gc_df["timestamp"]
    )

    # Create subplots: main chart with secondary y-axis for DXY, and volume subplot
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.8, 0.2],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
        subplot_titles=("Price Chart with Indicators", "Volume"),
    )

    # Add candlesticks to main chart (row 1)
    fig.add_trace(
        go.Candlestick(
            x=timestamps,
            open=gc_df["open"],
            high=gc_df["high"],
            low=gc_df["low"],
            close=gc_df["close"],
            name="GC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            increasing_fillcolor="#26a69a",
            decreasing_fillcolor="#ef5350",
            showlegend=True,
            legendgroup="price",
        ),
        row=1,
        col=1,
        secondary_y=False,
    )

    # Compute and add VWAP line
    try:
        from feature_engine.vwap import calculate_vwap

        # Prepare DataFrame for VWAP calculation
        vwap_df = gc_df.copy()
        if not isinstance(vwap_df.index, pd.DatetimeIndex):
            vwap_df = vwap_df.set_index("timestamp")

        # Ensure required columns exist
        if "ts_event" not in vwap_df.columns:
            vwap_df["ts_event"] = vwap_df.index

        vwap_series = calculate_vwap(vwap_df, session_reset=True)

        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=vwap_series.values,
                name="VWAP",
                line=dict(color="cyan", width=2, dash="dash"),
                opacity=0.8,
                showlegend=True,
                legendgroup="indicators",
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
    except Exception as e:
        # VWAP calculation failed, continue without it
        pass

    # Add EMA lines (9 and 21)
    try:
        # Calculate 9 EMA
        ema_9 = gc_df["close"].ewm(span=9, adjust=False).mean()
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=ema_9,
                name="EMA 9",
                line=dict(color="yellow", width=1.5),
                opacity=0.7,
                showlegend=True,
                legendgroup="indicators",
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

        # Calculate 21 EMA
        ema_21 = gc_df["close"].ewm(span=21, adjust=False).mean()
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=ema_21,
                name="EMA 21",
                line=dict(color="blue", width=1.5),
                opacity=0.7,
                showlegend=True,
                legendgroup="indicators",
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
    except Exception:
        # EMA calculation failed, continue without it
        pass

    # Add DXY on secondary y-axis if available
    if dxy_df is not None and not dxy_df.empty:
        dxy_timestamps = (
            dxy_df.index
            if isinstance(dxy_df.index, pd.DatetimeIndex)
            else dxy_df["timestamp"]
        )
        fig.add_trace(
            go.Scatter(
                x=dxy_timestamps,
                y=dxy_df["close"],
                name="DXY",
                line=dict(color="orange", width=2),
                opacity=0.6,
                showlegend=True,
                legendgroup="correlation",
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    # Add volume bars (row 2)
    volume_colors = [
        "#26a69a" if gc_df["close"].iloc[i] >= gc_df["open"].iloc[i] else "#ef5350"
        for i in range(len(gc_df))
    ]
    fig.add_trace(
        go.Bar(
            x=timestamps,
            y=gc_df["volume"],
            name="Volume",
            marker_color=volume_colors,
            showlegend=True,
            legendgroup="volume",
        ),
        row=2,
        col=1,
    )

    # Track which legend items we've shown
    shown_long_entry = False
    shown_short_entry = False

    # Add entry markers for all trades
    for trade in results.trades:
        entry_time = trade.entry_timestamp
        entry_price = trade.entry_price

        # Find closest timestamp in gc_df
        if isinstance(gc_df.index, pd.DatetimeIndex):
            closest_idx = gc_df.index.get_indexer([entry_time], method="nearest")[0]
            if closest_idx >= 0:
                marker_color = "#26a69a" if trade.direction == "long" else "#ef5350"
                marker_symbol = (
                    "triangle-up" if trade.direction == "long" else "triangle-down"
                )

                # Show legend only once per direction
                show_in_legend = False
                legendgroup = f"{trade.direction}_entry"
                if trade.direction == "long" and not shown_long_entry:
                    show_in_legend = True
                    shown_long_entry = True
                elif trade.direction == "short" and not shown_short_entry:
                    show_in_legend = True
                    shown_short_entry = True

                fig.add_trace(
                    go.Scatter(
                        x=[gc_df.index[closest_idx]],
                        y=[entry_price],
                        mode="markers",
                        name=f"{trade.direction.upper()} Entry",
                        marker=dict(
                            symbol=marker_symbol,
                            size=12,
                            color=marker_color,
                            line=dict(width=2, color="white"),
                        ),
                        hovertemplate=(
                            f"Trade: {trade.trade_id[:8]}<br>"
                            f"Entry: {entry_price:.2f}<br>"
                            f"Setup: {trade.setup_type}<br>"
                            f"Score: {trade.entry_execution.signal.score:.1f}<extra></extra>"
                        ),
                        showlegend=show_in_legend,
                        legendgroup=legendgroup,
                    ),
                    row=1,
                    col=1,
                    secondary_y=False,
                )

    # Track if we've shown exit legend
    shown_exit_legend = False

    # Add exit markers for all trades
    for trade in results.trades:
        if trade.exit_timestamp and trade.exit_price:
            exit_time = trade.exit_timestamp
            exit_price = trade.exit_price

            # Find closest timestamp in gc_df
            if isinstance(gc_df.index, pd.DatetimeIndex):
                closest_idx = gc_df.index.get_indexer([exit_time], method="nearest")[0]
                if closest_idx >= 0:
                    # Color by win/loss
                    exit_color = (
                        "#26a69a" if trade.pnl and trade.pnl > 0 else "#ef5350"
                    )

                    # Build hovertemplate with proper None handling
                    pnl_text = (
                        f"{trade.pnl:.2f} pts" if trade.pnl is not None else "N/A"
                    )
                    r_text = (
                        f"{trade.r_realized:.2f}R"
                        if trade.r_realized is not None
                        else "N/A"
                    )

                    # Show legend only for first exit marker
                    show_exit_legend = not shown_exit_legend
                    if show_exit_legend:
                        shown_exit_legend = True

                    fig.add_trace(
                        go.Scatter(
                            x=[gc_df.index[closest_idx]],
                            y=[exit_price],
                            mode="markers",
                            name="Exit",
                            marker=dict(
                                symbol="x",
                                size=12,
                                color=exit_color,
                                line=dict(width=2, color="white"),
                            ),
                            hovertemplate=(
                                f"Trade: {trade.trade_id[:8]}<br>"
                                f"Exit: {exit_price:.2f}<br>"
                                f"Reason: {trade.exit_reason}<br>"
                                f"PnL: {pnl_text} ({r_text})<extra></extra>"
                            ),
                            showlegend=show_exit_legend,
                            legendgroup="exits",
                        ),
                        row=1,
                        col=1,
                        secondary_y=False,
                    )

    # Highlight selected trade with SL/TP lines and duration shading
    if selected_trade_id:
        selected_trade = next(
            (t for t in results.trades if t.trade_id == selected_trade_id), None
        )
        if selected_trade:
            # Add SL line
            fig.add_hline(
                y=selected_trade.stop_loss,
                line_dash="dash",
                line_color="red",
                annotation_text=f"SL: {selected_trade.stop_loss:.2f}",
                annotation_position="right",
                row=1,
                col=1,
            )

            # Add TP line
            fig.add_hline(
                y=selected_trade.take_profit,
                line_dash="dash",
                line_color="green",
                annotation_text=f"TP: {selected_trade.take_profit:.2f}",
                annotation_position="right",
                row=1,
                col=1,
            )

            # Add trade duration shading if trade is closed
            if selected_trade.exit_timestamp and selected_trade.exit_price:
                # Determine shade color based on win/loss
                shade_color = (
                    "rgba(38, 166, 154, 0.1)"
                    if selected_trade.pnl and selected_trade.pnl > 0
                    else "rgba(239, 83, 80, 0.1)"
                )

                # Add shaded region for trade duration
                fig.add_vrect(
                    x0=selected_trade.entry_timestamp,
                    x1=selected_trade.exit_timestamp,
                    fillcolor=shade_color,
                    layer="below",
                    line_width=0,
                    row=1,
                    col=1,
                )

    # Update axes labels
    fig.update_xaxes(title_text="Time", row=2, col=1)
    fig.update_yaxes(title_text="GC Price (USD)", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="DXY Index", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

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
        hovermode="x",  # Changed from "x unified" to show OHLC properly
        height=700,  # Increased height for volume subplot
        margin=dict(l=60, r=60, t=40, b=40),
    )
    
    # Configure hover for candlesticks to show OHLC data
    fig.update_traces(
        selector=dict(type="candlestick"),
        hoverinfo="all",
    )

    # Remove rangeslider from candlestick
    fig.update_xaxes(rangeslider_visible=False)

    return fig


def render_trade_details(trade: Trade | None) -> html.Div:
    """Render detailed trade information.

    Args:
        trade: Selected trade or None

    Returns:
        HTML div with trade details
    """
    if trade is None:
        return html.Div("Select a trade to view details", className="text-muted")

    signal = trade.entry_execution.signal

    return dbc.Card(
        [
            dbc.CardHeader(f"Trade Details: {trade.trade_id[:8]}"),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Strong("Entry: "),
                                    f"{trade.entry_price:.2f} @ {trade.entry_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                                    html.Br(),
                                    html.Strong("Exit: "),
                                    (
                                        f"{trade.exit_price:.2f} @ {trade.exit_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                                        if trade.exit_timestamp
                                        and trade.exit_price is not None
                                        else "Open"
                                    ),
                                    html.Br(),
                                    html.Strong("Direction: "),
                                    trade.direction.upper(),
                                    html.Br(),
                                    html.Strong("Setup: "),
                                    trade.setup_type,
                                ],
                                width=6,
                            ),
                            dbc.Col(
                                [
                                    html.Strong("SL: "),
                                    f"{trade.stop_loss:.2f}",
                                    html.Br(),
                                    html.Strong("TP: "),
                                    f"{trade.take_profit:.2f}",
                                    html.Br(),
                                    html.Strong("PnL: "),
                                    (
                                        f"{trade.pnl:.2f} pts"
                                        if trade.pnl is not None
                                        else "N/A"
                                    ),
                                    html.Br(),
                                    html.Strong("R Realized: "),
                                    (
                                        f"{trade.r_realized:.2f}R"
                                        if trade.r_realized is not None
                                        else "N/A"
                                    ),
                                    html.Br(),
                                    html.Strong("Exit Reason: "),
                                    trade.exit_reason or "N/A",
                                ],
                                width=6,
                            ),
                        ]
                    ),
                    html.Hr(),
                    html.Strong("Signal: "),
                    f"Score {signal.score:.1f} ({signal.confidence})",
                    html.Br(),
                    html.Strong("Factors: "),
                    ", ".join(
                        f"{k}={v:.2f}" for k, v in signal.factors.items() if v > 0
                    ),
                ]
            ),
        ]
    )
