from datetime import datetime

from analysis.engine.trade import Trade, TradeSide
from analysis.engine.analytics.trade_reconstruction import (
    reconstruct_closed_trades,
)


trades = [

    Trade(
        id="1",
        order_id="1",
        timestamp=datetime(2025,1,1),
        symbol="BTCUSDT",
        side=TradeSide.BUY,
        quantity=1,
        price=100,
        fees=1,
    ),

    Trade(
        id="2",
        order_id="2",
        timestamp=datetime(2025,1,2),
        symbol="BTCUSDT",
        side=TradeSide.SELL,
        quantity=1,
        price=120,
        fees=1,
    ),
]


result = reconstruct_closed_trades(
    trades
)


print(result)
print(result[0].gross_pnl)
print(result[0].net_pnl)
print(result[0].holding_period)