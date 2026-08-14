"""
analysis.visualization.components.table

Trade inspection table.

Displays completed trades from ResearchReport.

This module:
- renders trade data
- formats values for presentation
- does not calculate analytics
- does not mutate state
"""

from __future__ import annotations

from datetime import datetime, timezone

from dash import html, dash_table

from analysis.engine.models.report import ResearchReport

from analysis.visualization.theme import (
    CARD_BACKGROUND,
    TEXT,
    SUBTEXT,
)



def trade_table(
    report: ResearchReport,
):
    """
    Create completed trades table.
    """

    trades = report.closed_trades


    if not trades:

        return html.Div(

            "No completed trades.",

            style={
                "color": SUBTEXT,
            },

        )



    rows = []


    for trade in trades:

        rows.append(

            {

                "Entry":
                    _format_timestamp(
                        trade.entry_time
                    ),

                "Exit":
                    _format_timestamp(
                        trade.exit_time
                    ),

                "PnL":
                    _format_pnl(
                        trade.net_pnl
                    ),

                "Duration":
                    str(
                        trade.holding_period
                    ),

            }

        )



    return dash_table.DataTable(

        data=rows,


        columns=[

            {
                "name": "Entry",
                "id": "Entry",
            },

            {
                "name": "Exit",
                "id": "Exit",
            },

            {
                "name": "PnL",
                "id": "PnL",
            },

            {
                "name": "Duration",
                "id": "Duration",
            },

        ],


        style_table={

            "overflowX": "auto",

        },


        style_header={

            "backgroundColor": CARD_BACKGROUND,

            "color": TEXT,

            "fontWeight": "bold",

        },


        style_cell={

            "backgroundColor": CARD_BACKGROUND,

            "color": TEXT,

            "padding": "10px",

            "textAlign": "center",

        },


        page_size=15,

    )



def _format_timestamp(
    timestamp,
):
    """
    Convert engine timestamp into readable display time.

    Supports:
    - datetime objects
    - epoch seconds
    - epoch milliseconds
    """

    if isinstance(
        timestamp,
        datetime,
    ):

        return timestamp.strftime(
            "%Y-%m-%d %H:%M"
        )


    # Handle epoch timestamps
    if timestamp > 10_000_000_000:
        timestamp /= 1000


    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).strftime(
        "%Y-%m-%d %H:%M"
    )



def _format_pnl(
    value: float,
):
    """
    Human-readable PnL formatting.
    """

    return f"{value:,.2f}"