"""
analysis.visualization.components.layout

Main dashboard page layout.

Defines dashboard structure only.
"""

from __future__ import annotations

from dash import html, dcc

from analysis.visualization.theme import (
    BACKGROUND,
    TEXT,
    SUBTEXT,
    CARD_BACKGROUND,
)


def card(
    content,
    *,
    title: str | None = None,
):

    children = []


    if title:

        children.append(
            html.H3(
                title,
                style={
                    "color": TEXT,
                    "marginBottom": "10px",
                },
            )
        )


    children.append(content)


    return html.Div(
        children,

        style={
            "backgroundColor": CARD_BACKGROUND,
            "borderRadius": "10px",
            "padding": "20px",
            "margin": "10px",
            "boxShadow":
                "0 4px 12px rgba(0,0,0,0.25)",
        },
    )



def graph_card(
    figure,
    *,
    title: str,
):

    from dash import dcc

    from analysis.visualization.theme import (
        GRAPH_CONFIG,
    )


    return card(

        dcc.Graph(
            figure=figure,
            config=GRAPH_CONFIG,
            responsive=True,
        ),

        title=title,

    )



def dashboard_layout(
    *,
    report=None,
    title="Research Wing Dashboard",
):

    content = []


    if report is None:

        content.append(
            card(
                html.Div(
                    "No research report loaded."
                ),
                title="Overview",
            )
        )


    else:

        from analysis.visualization.components.market import (
            market_figure,
        )

        from analysis.visualization.components.equity import (
            equity_figure,
        )

        from analysis.visualization.components.drawdown import (
            drawdown_figure,
        )

        from analysis.visualization.components.statistics import (
            statistics_panel,
        )

        from analysis.visualization.components.table import (
            trade_table,
        )

        #
        # Statistics
        #
        content.append(

            card(

                statistics_panel(
                    report
                ),

                title="Performance Statistics",

            )

        )
                
        #
        # Primary research chart
        #
        content.append(

            graph_card(

                market_figure(
                    report,
                    show_trades=True,
                ),

                title="Market + Trades",

            )

        )

        #
        # Trade Table
        #
        content.append(

            card(

                trade_table(
                    report
                ),

                title="Completed Trades",

            )

        )


        #
        # Portfolio performance
        #
        content.append(

            graph_card(

                equity_figure(
                    report.equity_curve
                ),

                title="Equity Curve",

            )

        )


        #
        # Risk
        #
        content.append(

            graph_card(

                drawdown_figure(
                    report.equity_curve
                ),

                title="Drawdown",

            )

        )



    return html.Div(

        [

            html.Div(

                [

                    html.H1(
                        title,
                        style={
                            "color": TEXT,
                        },
                    ),

                    html.P(
                        "Quantitative research environment",
                        style={
                            "color": SUBTEXT,
                        },
                    ),

                ]

            ),


            dcc.Tabs(

                children=[

                    dcc.Tab(
                        label="Overview"
                    ),

                    dcc.Tab(
                        label="Trades"
                    ),

                    dcc.Tab(
                        label="Risk"
                    ),

                    dcc.Tab(
                        label="Benchmark"
                    ),

                ]

            ),


            html.Div(
                content
            ),

        ],

        style={
            "backgroundColor": BACKGROUND,
            "minHeight": "100vh",
        },

    )