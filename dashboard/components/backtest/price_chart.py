"""Price Chart with Entry/Exit Markers - Candlestick chart with trade markers."""

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from backtester.replay_loop import BacktestResults
from backtester.trade import Trade
from dash import dcc, html


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
                        style={"height": "500px"},
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
) -> go.Figure:
    """Render price chart with entry/exit markers.

    Args:
        results: BacktestResults object with all trades
        gc_df: GC price DataFrame with OHLCV columns and DatetimeIndex, or None
        selected_trade_id: Optional trade ID to highlight

    Returns:
        Plotly figure with candlesticks and trade markers
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

    # Create candlestick chart
    fig = go.Figure()

    # Add candlesticks
    fig.add_trace(
        go.Candlestick(
            x=(
                gc_df.index
                if isinstance(gc_df.index, pd.DatetimeIndex)
                else gc_df["timestamp"]
            ),
            open=gc_df["open"],
            high=gc_df["high"],
            low=gc_df["low"],
            close=gc_df["close"],
            name="GC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            increasing_fillcolor="#26a69a",
            decreasing_fillcolor="#ef5350",
        )
    )

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
                        showlegend=(
                            trade == results.trades[0]
                        ),  # Only show legend for first
                    )
                )

    # Highlight selected trade with SL/TP lines
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
            )

            # Add TP line
            fig.add_hline(
                y=selected_trade.take_profit,
                line_dash="dash",
                line_color="green",
                annotation_text=f"TP: {selected_trade.take_profit:.2f}",
                annotation_position="right",
            )

            # Add exit marker if trade is closed
            if selected_trade.exit_timestamp and selected_trade.exit_price:
                exit_time = selected_trade.exit_timestamp
                exit_price = selected_trade.exit_price

                if isinstance(gc_df.index, pd.DatetimeIndex):
                    closest_idx = gc_df.index.get_indexer(
                        [exit_time], method="nearest"
                    )[0]
                    if closest_idx >= 0:
                        exit_color = (
                            "#26a69a"
                            if selected_trade.pnl and selected_trade.pnl > 0
                            else "#ef5350"
                        )

                        # Build hovertemplate with proper None handling for pnl
                        pnl_text = (
                            f"{selected_trade.pnl:.2f} pts"
                            if selected_trade.pnl is not None
                            else "N/A"
                        )
                        hovertemplate = (
                            f"Exit: {exit_price:.2f}<br>"
                            f"Reason: {selected_trade.exit_reason}<br>"
                            f"PnL: {pnl_text}<extra></extra>"
                        )

                        fig.add_trace(
                            go.Scatter(
                                x=[gc_df.index[closest_idx]],
                                y=[exit_price],
                                mode="markers",
                                name="Exit",
                                marker=dict(
                                    symbol="x",
                                    size=15,
                                    color=exit_color,
                                    line=dict(width=2, color="white"),
                                ),
                                hovertemplate=hovertemplate,
                            )
                        )

    # Update layout
    fig.update_layout(
        template="plotly_dark",
        xaxis_title="Time",
        yaxis_title="Price",
        showlegend=True,
        hovermode="x unified",
        height=500,
    )

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
