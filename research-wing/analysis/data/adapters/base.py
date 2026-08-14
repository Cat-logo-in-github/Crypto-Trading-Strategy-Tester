from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """
    Converts any external dataset into a raw canonical intermediate format.
    """

    @abstractmethod
    def load(self, **kwargs) -> list[dict[str, Any]]:
        """
        Must return list of raw OHLCV-like dictionaries:

        {
            "timestamp": ...,
            "open": ...,
            "high": ...,
            "low": ...,
            "close": ...,
            "volume": ...
        }
        """
        raise NotImplementedError