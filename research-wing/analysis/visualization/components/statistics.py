"""
analysis.visualization.components.statistics

Dashboard statistics cards.

This module only renders existing research metrics.

It does NOT:
- calculate statistics
- access simulations
- mutate reports
"""

from __future__ import annotations

from dash import html

from analysis.engine.models.report import ResearchReport

from analysis.visualization.theme import (
    TEXT,
    SUBTEXT,
    CARD_BACKGROUND,
)



def metric_card(
    label: str,
    value: str,
):
    """
    Single metric display card.
    """

    return html.Div(

        [

            html.Div(
                label,
                style={
                    "color": SUBTEXT,
                    "fontSize": "14px",
                },
            ),


            html.Div(
                value,
                style={
                    "color": TEXT,
                    "fontSize": "28px",
                    "fontWeight": "bold",
                },
            ),

        ],

        style={

            "backgroundColor": CARD_BACKGROUND,

            "borderRadius": "10px",

            "padding": "20px",

            "margin": "10px",

            "minWidth": "160px",

        },

    )



def statistics_panel(
    report: ResearchReport,
):
    """
    Create dashboard metric section.
    """


    performance = report.performance

    risk = report.risk

    if performance is None or risk is None:
        return html.Div(
            "Statistics unavailable."
        )

    trade_stats = report.trade_statistics

    execution = report.execution_statistics



    cards = [

        metric_card(
            "Return",
            f"{performance.total_return:.2%}",
        ),


        metric_card(
            "Max Drawdown",
            f"{performance.max_drawdown:.2%}",
        ),


        metric_card(
            "Sharpe Ratio",
            f"{risk.sharpe_ratio:.2f}",
        ),

    ]



    if trade_stats is not None:

        cards.extend(

            [

                metric_card(
                    "Win Rate",
                    f"{trade_stats.win_rate:.2%}",
                ),


                metric_card(
                    "Profit Factor",
                    f"{trade_stats.profit_factor:.2f}",
                ),


                metric_card(
                    "Expectancy",
                    f"{trade_stats.expectancy:.2f}",
                ),

            ]

        )



    if execution is not None:

        cards.append(

            metric_card(
                "Fees Paid",
                f"{execution.total_fees:.2f}",
            )

        )



    return html.Div(

        cards,

        style={

            "display": "flex",

            "flexWrap": "wrap",

            "justifyContent": "flex-start",

        },

    )