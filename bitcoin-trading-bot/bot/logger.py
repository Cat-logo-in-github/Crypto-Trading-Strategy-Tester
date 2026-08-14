"""
logger.py

Central logging system for the trading bot.
"""

import logging
import os

from bot.config import (
    LOG_FILE,
    LOG_LEVEL,
)


class BotLogger:

    def __init__(self):

        self.logger = logging.getLogger("BitcoinBot")

        self.logger.setLevel(
            getattr(logging, LOG_LEVEL)
        )


        # Prevent duplicate handlers
        if not self.logger.handlers:

            self._setup()


    def _setup(self):

        # Create logs folder if missing
        folder = os.path.dirname(LOG_FILE)

        if folder:
            os.makedirs(
                folder,
                exist_ok=True
            )


        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )


        # File logging

        file_handler = logging.FileHandler(
            LOG_FILE
        )

        file_handler.setFormatter(
            formatter
        )


        # Terminal logging

        console_handler = logging.StreamHandler()

        console_handler.setFormatter(
            formatter
        )


        self.logger.addHandler(
            file_handler
        )

        self.logger.addHandler(
            console_handler
        )


    def info(self, message):

        self.logger.info(message)


    def warning(self, message):

        self.logger.warning(message)


    def error(self, message):

        self.logger.error(message)


# Shared logger instance

logger = BotLogger()