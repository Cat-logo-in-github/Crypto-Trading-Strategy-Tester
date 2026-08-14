"""
Temporary strategy test
"""

class TradingStrategy:

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

    counter = 0


    @classmethod
    def generate_signal(cls, df):

        cls.counter += 1

        print(
            f"STRATEGY TEST COUNTER: {cls.counter}"
        )


        if cls.counter % 10 == 0:
            return cls.SELL


        if cls.counter % 5 == 0:
            return cls.BUY


        return cls.HOLD