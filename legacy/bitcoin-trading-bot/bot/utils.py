"""
utils.py

General helper functions for the bot.
"""

import os
from datetime import datetime


def ensure_directories():
    """
    Create required project folders if they don't exist.
    """

    folders = [
        "data",
        "logs",
        "tests",
    ]

    for folder in folders:

        if not os.path.exists(folder):
            os.makedirs(folder)


def timestamp():
    """
    Return a readable timestamp.
    """

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def format_currency(value):
    """
    Format numbers as USD.
    """

    return f"${value:,.2f}"


def format_btc(value):
    """
    Format BTC amount.
    """

    return f"{value:.8f}"