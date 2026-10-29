"""
analysis.visualization.dashboard

Interactive research dashboard.

Consumes ResearchReport objects and renders
interactive analysis views.
"""

from __future__ import annotations

from dataclasses import dataclass

from dash import Dash

from analysis.visualization.components.layout import (
    dashboard_layout,
)


@dataclass(slots=True)
class DashboardConfig:
    """
    Dashboard configuration.
    """

    title: str = "Research Wing Dashboard"

    host: str = "127.0.0.1"

    port: int = 8050

    debug: bool = True



class ResearchDashboard:
    """
    Main dashboard application.

    Visualization layer only.

    It does not:
    - run backtests
    - calculate metrics
    - modify research objects
    """

    def __init__(
        self,
        *,
        report=None,
        config: DashboardConfig | None = None,
    ) -> None:


        self.report = report


        self.config = (
            config
            or DashboardConfig()
        )


        self.app = Dash(
            "research_wing_dashboard"
        )


        self._build_layout()



    def _build_layout(
        self,
    ) -> None:

        self.app.layout = dashboard_layout(
            report=self.report,
            title=self.config.title,
        )



    def run(
        self,
    ) -> None:

        self.app.run(
            host=self.config.host,
            port=self.config.port,
            debug=self.config.debug,
        )