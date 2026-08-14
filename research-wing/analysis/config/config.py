from dataclasses import dataclass
import os
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True, slots=True)
class Config:
    binance_api_key: str | None = os.getenv("BINANCE_API_KEY")
    binance_api_secret: str | None = os.getenv("BINANCE_API_SECRET")

    data_source: str = os.getenv("DATA_SOURCE", "binance")
    base_asset: str = os.getenv("BASE_ASSET", "BTCUSDT")
    timeframe: str = os.getenv("TIMEFRAME", "1h")