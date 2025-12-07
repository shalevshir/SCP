"""Indicators Panel Components - 15M Indicators & HTF Bias.

This module provides the indicator and HTF bias panels for the dashboard.
"""

from typing import Optional

import dash_bootstrap_components as dbc
import pandas as pd
from dash import html

from dashboard.components.validation import (
    get_all_indicator_validations,
    get_validation_badge_class,
    get_validation_tooltip,
    validate_structure,
)
from rule_engine.htf.types import HTFBias


def create_indicators_panel() -> dbc.Card:
    """Create the 15M indicators panel.

    Returns:
        Dash Bootstrap Card containing indicators display
    """
    return dbc.Card(
        [
            dbc.CardHeader("15M Indicators"),
            dbc.CardBody([html.Div(id="indicators-panel")]),
        ],
        className="mb-3",
    )


def create_htf_panel() -> dbc.Card:
    """Create the HTF bias panel.

    Returns:
        Dash Bootstrap Card containing HTF bias display
    """
    return dbc.Card(
        [
            dbc.CardHeader("HTF Bias"),
            dbc.CardBody([html.Div(id="htf-panel")]),
        ]
    )


def render_indicators(features: pd.Series, htf_bias: Optional[HTFBias]) -> html.Div:
    """Render the 15M indicators panel content.

    Args:
        features: Current feature values
        htf_bias: Current HTF bias for validation context

    Returns:
        HTML div with indicator values and validation badges
    """
    if features.empty:
        return html.P("Waiting for data...", className="text-muted")

    # Get validation status for all indicators
    validations = get_all_indicator_validations(features, htf_bias)

    def format_with_badge(
        label: str,
        value: Optional[float],
        decimals: int,
        validation_key: str,
    ) -> html.P:
        """Format indicator with value and SOP validation badge."""
        # Format value
        if value is None or (isinstance(value, float) and pd.isna(value)):
            value_str = "N/A"
        else:
            try:
                value_str = f"{float(value):.{decimals}f}"
            except (ValueError, TypeError):
                value_str = str(value)

        # Get validation status
        status = validations.get(validation_key, "N/A")
        badge_class = get_validation_badge_class(status)
        tooltip = get_validation_tooltip(validation_key, status, value)

        return html.P(
            [
                html.Strong(f"{label}: "),
                value_str,
                html.Span(
                    f" [{status}]",
                    className=badge_class + " ms-2",
                    title=tooltip,
                ),
            ]
        )

    def format_structure() -> html.P:
        """Format structure with SOP validation badge."""
        val = features.get("structure_label")
        status = validations.get("structure", "N/A")
        badge_class = get_validation_badge_class(status)
        tooltip = get_validation_tooltip("structure", status, None)

        # Format value
        if val is None or (isinstance(val, float) and pd.isna(val)):
            value_str = "None"
        else:
            value_str = str(val)

        return html.P(
            [
                html.Strong("Structure: "),
                value_str,
                html.Span(
                    f" [{status}]",
                    className=badge_class + " ms-2",
                    title=tooltip,
                ),
            ]
        )

    return html.Div(
        [
            format_with_badge("VWAP", features.get("vwap"), 2, "vwap"),
            format_with_badge("RSI", features.get("rsi"), 1, "rsi"),
            format_with_badge("EMA 9", features.get("ema_9"), 2, "ema_stack"),
            format_with_badge("EMA 20", features.get("ema_20"), 2, "ema_stack"),
            format_with_badge("EMA 50", features.get("ema_50"), 2, "ema_stack"),
            format_with_badge("DXY Corr", features.get("dxy_corr"), 3, "dxy_corr"),
            format_structure(),
        ]
    )


def render_htf_panel(htf_bias: Optional[HTFBias]) -> html.Div:
    """Render the HTF bias panel content.

    Args:
        htf_bias: Current HTF bias object

    Returns:
        HTML div with HTF bias information
    """
    if not htf_bias:
        return html.Div(
            [
                html.P("Waiting for HTF data... ", className="text-muted"),
                html.Span("[N/A]", className="badge bg-secondary ms-2"),
                html.Br(),
                html.Small("(Needs 1H boundary at :59)", className="text-muted"),
            ]
        )

    # Determine color based on bias
    if htf_bias.bias == "bullish":
        bias_color = "text-success"
    elif htf_bias.bias == "bearish":
        bias_color = "text-danger"
    else:
        bias_color = "text-warning"

    # Overall HTF validity (score >= 6 and not neutral)
    is_valid = htf_bias.score >= 6.0 and htf_bias.bias != "neutral"

    # HTF bias badge
    if is_valid:
        htf_badge_status = "VALID"
        htf_badge_class = "badge bg-success ms-2"
    else:
        htf_badge_status = "WEAK"
        htf_badge_class = "badge bg-warning text-dark ms-2"

    def format_structure_with_badge(structure_value: Optional[str]) -> list:
        """Format structure with SOP validation badge."""
        status = validate_structure(structure_value, htf_bias)
        badge_class = get_validation_badge_class(status)
        tooltip = get_validation_tooltip("structure", status, None)

        value_str = str(structure_value or "N/A")

        return [
            value_str,
            html.Span(
                f" [{status}]",
                className=badge_class + " ms-2",
                title=tooltip,
            ),
        ]

    def format_boolean_with_badge(value: bool, is_good_fn) -> list:
        """Format boolean with badge."""
        is_good = is_good_fn(value)

        if is_good:
            status = "VALID"
            badge_class = "badge bg-success ms-2"
        else:
            status = "INVALID"
            badge_class = "badge bg-danger ms-2"

        value_str = "Yes" if value else "No"

        return [value_str, html.Span(f" [{status}]", className=badge_class)]

    return html.Div(
        [
            html.H5(
                [
                    "Bias: ",
                    html.Span(htf_bias.bias.upper(), className=bias_color),
                    html.Span(f" [{htf_badge_status}]", className=htf_badge_class),
                ]
            ),
            html.P([html.Strong("Score: "), f"{htf_bias.score:.1f}/10"]),
            html.P([html.Strong("Confidence: "), htf_bias.confidence]),
            html.Hr(),
            html.P(
                [
                    html.Strong("1H Structure: "),
                    *format_structure_with_badge(htf_bias.structure_1h),
                ]
            ),
            html.P(
                [
                    html.Strong("15M Structure: "),
                    *format_structure_with_badge(htf_bias.structure_15m),
                ]
            ),
            html.P(
                [
                    html.Strong("DXY Aligned: "),
                    *format_boolean_with_badge(htf_bias.dxy_alignment, lambda x: x is True),
                ]
            ),
            html.P(
                [
                    html.Strong("VWAP Confirmed: "),
                    *format_boolean_with_badge(
                        htf_bias.vwap_trend_confirmed, lambda x: x is True
                    ),
                ]
            ),
        ]
    )

