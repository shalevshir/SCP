"""Signal Panel Component - Current Trade Signal Display.

This module provides the signal display panel for the dashboard.
"""


import dash_bootstrap_components as dbc
from dash import html
from rule_engine.signal import Signal


def create_signal_panel() -> dbc.Card:
    """Create the signal display panel.

    Returns:
        Dash Bootstrap Card containing signal display
    """
    return dbc.Card(
        [
            dbc.CardHeader("Current Signal"),
            dbc.CardBody([html.Div(id="signal-panel")]),
        ]
    )


def render_signal(signal: Signal | None) -> html.Div:
    """Render the signal panel content.

    Args:
        signal: Current trade signal or None

    Returns:
        HTML div with signal information
    """
    if not signal or signal.direction == "neutral":
        return html.Div(
            [
                html.H5("No Signal", className="text-muted"),
                html.P("Waiting for setup..."),
            ]
        )

    # Determine color based on direction
    if signal.direction == "long":
        direction_color = "text-success"
        direction_icon = "↑"
    elif signal.direction == "short":
        direction_color = "text-danger"
        direction_icon = "↓"
    else:
        direction_color = "text-warning"
        direction_icon = "→"

    # Confidence badge styling
    if signal.confidence == "A+":
        confidence_class = "badge bg-success"
    elif signal.confidence == "Watch":
        confidence_class = "badge bg-warning text-dark"
    else:
        confidence_class = "badge bg-danger"

    # Score badge styling
    if signal.score >= 8:
        score_class = "text-success"
    elif signal.score >= 6:
        score_class = "text-warning"
    else:
        score_class = "text-danger"

    return html.Div(
        [
            # Direction header
            html.H4(
                [
                    "Direction: ",
                    html.Span(
                        f"{direction_icon} {signal.direction.upper()}",
                        className=direction_color,
                    ),
                ]
            ),
            html.Hr(),
            # Score and confidence
            html.P(
                [
                    html.Strong("Score: "),
                    html.Span(f"{signal.score:.1f}/10", className=score_class),
                ]
            ),
            html.P(
                [
                    html.Strong("Confidence: "),
                    html.Span(signal.confidence, className=confidence_class),
                ]
            ),
            html.Hr(),
            # Setup details
            html.P([html.Strong("Setup: "), signal.setup_type]),
            html.P([html.Strong("HTF Bias: "), signal.htf_bias]),
            html.P([html.Strong("Tier: "), signal.enforcer_tier]),
            # Rationale
            html.Hr(),
            html.P(
                [
                    html.Strong("Rationale: "),
                    html.Small(signal.rationale, className="text-muted"),
                ]
            ),
        ]
    )


def render_signal_badge(signal: Signal | None) -> html.Span:
    """Render a compact signal badge for header display.

    Args:
        signal: Current trade signal or None

    Returns:
        HTML span with compact signal indicator
    """
    if not signal or signal.direction == "neutral":
        return html.Span("No Signal", className="badge bg-secondary")

    # Direction and confidence styling
    if signal.confidence == "A+":
        badge_class = (
            "badge bg-success" if signal.direction == "long" else "badge bg-danger"
        )
    else:
        badge_class = "badge bg-warning text-dark"

    direction_arrow = "↑" if signal.direction == "long" else "↓"

    return html.Span(
        f"{direction_arrow} {signal.confidence} ({signal.score:.1f})",
        className=badge_class,
    )
