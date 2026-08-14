"""
analysis.visualization.theme

Central dashboard styling.

Keeping theme values separate allows
future support for:

- dark/light modes
- user themes
- exported reports
- branding
"""

from __future__ import annotations


# --------------------------------------------------
# Colors
# --------------------------------------------------

BACKGROUND = "#0E1117"

CARD_BACKGROUND = "#161B22"

# Alias for simpler internal use
CARD = CARD_BACKGROUND

PRIMARY = "#00CC96"

SECONDARY = "#636EFA"

WARNING = "#FFA15A"

DANGER = "#EF553B"

TEXT = "#F5F5F5"

SUBTEXT = "#A0A0A0"

# --------------------------------------------------
# Semantic aliases
# --------------------------------------------------

GREEN = PRIMARY

RED = DANGER

BLUE = SECONDARY

ORANGE = WARNING

WHITE = TEXT

BLACK = BACKGROUND

# --------------------------------------------------
# Plot defaults
# --------------------------------------------------

PLOT_TEMPLATE = "plotly_dark"

# --------------------------------------------------
# Plotly graph configuration
# --------------------------------------------------

GRAPH_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": True,
    "modeBarButtonsToAdd": [
        "toggleSpikelines",
    ],
}

# --------------------------------------------------
# Component styles
# --------------------------------------------------

CARD_STYLE = {
    "backgroundColor": CARD_BACKGROUND,
    "borderRadius": "12px",
    "padding": "20px",
    "boxShadow": (
        "0px 4px 12px rgba(0,0,0,0.25)"
    ),
}


TITLE_STYLE = {
    "color": TEXT,
    "fontSize": "28px",
    "fontWeight": "700",
}


SUBTITLE_STYLE = {
    "color": SUBTEXT,
    "fontSize": "14px",
}