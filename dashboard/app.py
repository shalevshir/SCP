"""Plotly Dash Dashboard for Live Trading Simulation.

This module provides LiveDashboard that displays real-time indicators,
HTF bias, signals, and price charts using Plotly Dash.

Architecture:
- Uses SimulationEngine (pure Python) for business logic
- UI components are composable and testable
- Single interval callback for all updates
"""

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html

from common.logger import get_logger
from dashboard.components.chart import create_price_chart, render_price_chart
from dashboard.components.controls import (
    create_controls_panel,
    render_pause_reason,
    render_status_indicator,
    render_timestamp,
)
from dashboard.components.indicators import (
    create_htf_panel,
    create_indicators_panel,
    render_htf_panel,
    render_indicators,
)
from dashboard.components.signal import create_signal_panel, render_signal
from dashboard.core.engine import SimulationEngine

logger = get_logger(__name__)


class LiveDashboard:
    """Plotly Dash dashboard for live trading simulation.

    Multi-panel dashboard displaying:
    - Indicators (VWAP, RSI, EMAs, DXY correlation, structure)
    - HTF bias (1H/15M bias, overall direction)
    - Current signal (direction, score, confidence, setup type)
    - Price chart (candlestick + VWAP overlay + DXY)
    - Controls (play/pause/step, speed, timestamp)

    Attributes:
        engine: Simulation engine (business logic)
        app: Dash application instance
    """

    def __init__(self, engine: SimulationEngine):
        """Initialize dashboard.

        Args:
            engine: Configured simulation engine
        """
        self.engine = engine

        # Create Dash app with Bootstrap theme
        self.app = dash.Dash(
            __name__,
            external_stylesheets=[dbc.themes.DARKLY],
            title="Shir Capital Live Dashboard",
        )

        # Build layout
        self.app.layout = self._build_layout()

        # Register callbacks
        self._register_callbacks()

        logger.info("Dashboard initialized with new Engine-UI architecture")

    def _build_layout(self) -> dbc.Container:
        """Build dashboard layout using components.

        Returns:
            Dash layout container
        """
        return dbc.Container(
            [
                # Header
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.H1(
                                    "Shir Capital Live Trading Dashboard",
                                    className="text-center mb-4",
                                ),
                                html.Hr(),
                            ]
                        )
                    ]
                ),
                # Control Panel
                dbc.Row(
                    [dbc.Col([create_controls_panel()])],
                    className="mb-4",
                ),
                # Main content: 3 columns
                dbc.Row(
                    [
                        # Left Column: Indicators & HTF Bias
                        dbc.Col(
                            [
                                create_indicators_panel(),
                                create_htf_panel(),
                            ],
                            width=3,
                        ),
                        # Middle Column: Price Chart
                        dbc.Col(
                            [create_signal_panel(), create_price_chart()],
                            width=6,
                        ),
                        # Right Column: Signal (moved above chart on mobile)
                        dbc.Col(
                            [
                                # Additional info panel placeholder
                                dbc.Card(
                                    [
                                        dbc.CardHeader("Session Info"),
                                        dbc.CardBody([html.Div(id="session-panel")]),
                                    ]
                                )
                            ],
                            width=3,
                        ),
                    ]
                ),
                # Interval component for periodic updates
                dcc.Interval(
                    id="interval-component",
                    interval=500,  # Update every 500ms
                    n_intervals=0,
                ),
                # Store for state (used by callbacks)
                dcc.Store(id="state-store"),
            ],
            fluid=True,
            className="p-4",
        )

    def _register_callbacks(self) -> None:
        """Register Dash callbacks for interactivity."""

        @self.app.callback(
            [
                Output("status-indicator", "children"),
                Output("current-timestamp", "children"),
                Output("progress-bar", "value"),
                Output("pause-reason", "children"),
                Output("indicators-panel", "children"),
                Output("htf-panel", "children"),
                Output("signal-panel", "children"),
                Output("price-chart", "figure"),
                Output("session-panel", "children"),
                Output("speed-input", "value"),
            ],
            [Input("interval-component", "n_intervals")],
        )
        def update_all(n: int):
            """Main update callback - refreshes all panels from engine state."""
            state = self.engine.state

            # Status indicator
            status = render_status_indicator(
                state.is_simulation_running, state.is_paused
            )

            # Timestamp
            timestamp_str = render_timestamp(state.timestamp)

            # Progress
            progress = state.simulation_progress * 100

            # Pause reason
            pause_reason = render_pause_reason(
                state.pause_reason, state.paused_at_signal
            )

            # Indicators panel
            indicators = render_indicators(state.features, state.htf_bias)

            # HTF panel
            htf_panel = render_htf_panel(state.htf_bias)

            # Signal panel
            signal_panel = render_signal(state.current_signal)

            # Price chart
            gc_df = state.get_price_history_gc_df()
            dxy_df = state.get_price_history_dxy_df()
            vwap = state.features.get("vwap") if not state.features.empty else None
            chart = render_price_chart(gc_df, dxy_df, vwap)

            # Session info panel
            session_panel = self._render_session_panel(state)

            # Speed (in case it was changed externally)
            speed = state.simulation_speed

            return (
                status,
                timestamp_str,
                progress,
                pause_reason,
                indicators,
                htf_panel,
                signal_panel,
                chart,
                session_panel,
                speed,
            )

        @self.app.callback(
            Output("state-store", "data"),
            [Input("btn-play", "n_clicks")],
            prevent_initial_call=True,
        )
        def on_play(n_clicks):
            """Handle play button click."""
            if n_clicks:
                if self.engine.state.is_paused:
                    self.engine.resume()
                elif not self.engine.is_running():
                    self.engine.start()
                logger.info("Play button clicked")
            return {"action": "play"}

        @self.app.callback(
            Output("state-store", "data", allow_duplicate=True),
            [Input("btn-pause", "n_clicks")],
            prevent_initial_call=True,
        )
        def on_pause(n_clicks):
            """Handle pause button click."""
            if n_clicks and self.engine.is_running():
                self.engine.pause("Manual pause")
                logger.info("Pause button clicked")
            return {"action": "pause"}

        @self.app.callback(
            Output("state-store", "data", allow_duplicate=True),
            [Input("btn-step", "n_clicks")],
            prevent_initial_call=True,
        )
        def on_step(n_clicks):
            """Handle step button click."""
            if n_clicks:
                # Step processes one bar even when paused
                signal = self.engine.step()
                if signal:
                    logger.info(f"Step: {signal.direction} signal generated")
                else:
                    logger.debug("Step: No signal")
            return {"action": "step"}

        @self.app.callback(
            Output("state-store", "data", allow_duplicate=True),
            [Input("speed-input", "value")],
            prevent_initial_call=True,
        )
        def on_speed_change(speed: float):
            """Handle speed input change."""
            if speed and speed > 0:
                self.engine.set_speed(speed)
                logger.info(f"Speed changed to {speed}x")
            return {"action": "speed", "value": speed}

    def _render_session_panel(self, state) -> html.Div:
        """Render session information panel.

        Args:
            state: Current dashboard state

        Returns:
            HTML div with session info
        """
        parts = []

        # Session active status
        if state.is_session_active:
            parts.append(
                html.P(
                    [
                        html.Strong("Session: "),
                        html.Span("Active", className="text-success"),
                    ]
                )
            )
        else:
            parts.append(
                html.P(
                    [
                        html.Strong("Session: "),
                        html.Span("Inactive", className="text-muted"),
                    ]
                )
            )

        # Constraints info
        if state.session_constraints:
            parts.append(
                html.P(
                    [
                        html.Strong("Tier: "),
                        state.session_constraints.get("name", "N/A"),
                    ]
                )
            )
            min_score = state.session_constraints.get("min_signal_score", 0)
            parts.append(
                html.P([html.Strong("Min Score: "), f"{min_score:.1f}"])
            )

        # Warmup status
        if self.engine.htf_calculator.is_warmed_up():
            parts.append(
                html.P(
                    [
                        html.Strong("HTF Warmup: "),
                        html.Span("Complete", className="text-success"),
                    ]
                )
            )
        else:
            parts.append(
                html.P(
                    [
                        html.Strong("HTF Warmup: "),
                        html.Span("In Progress...", className="text-warning"),
                    ]
                )
            )

        return html.Div(parts)

    def run(
        self, host: str = "0.0.0.0", port: int = 8050, debug: bool = False
    ) -> None:
        """Run the dashboard server.

        Args:
            host: Host address (default: 0.0.0.0)
            port: Port number (default: 8050)
            debug: Enable debug mode (default: False)
        """
        logger.info(f"Starting dashboard server on {host}:{port}")
        self.app.run_server(host=host, port=port, debug=debug)
