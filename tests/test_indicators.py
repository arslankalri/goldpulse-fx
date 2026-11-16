import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gold_app import indicators


def candle(h, l, c, v=1.0, t=0):
    return {"t": t, "o": c, "h": h, "l": l, "c": c, "v": v, "ct": t}


class TestEMA(unittest.TestCase):
    def test_constant_series(self):
        s = indicators.ema([5.0] * 30, 20)
        self.assertAlmostEqual(s[-1], 5.0)

    def test_known_values(self):
        # period 2: seed (1+2)/2=1.5 at idx1; k=2/3; idx2 = 3*(2/3)+1.5*(1/3)=2.5
        s = indicators.ema([1.0, 2.0, 3.0], 2)
        self.assertIsNone(s[0])
        self.assertAlmostEqual(s[1], 1.5)
        self.assertAlmostEqual(s[2], 2.5)


class TestATR(unittest.TestCase):
    def test_constant_range(self):
        candles = [candle(102, 100, 101) for _ in range(30)]
        self.assertAlmostEqual(indicators.atr_last(candles, 14), 2.0)


class TestRSI(unittest.TestCase):
    def test_all_gains_is_100(self):
        closes = [float(i) for i in range(1, 40)]
        self.assertAlmostEqual(indicators.rsi(closes, 14)[-1], 100.0)

    def test_all_losses_is_0(self):
        closes = [float(40 - i) for i in range(40)]
        self.assertAlmostEqual(indicators.rsi(closes, 14)[-1], 0.0)


class TestVWAP(unittest.TestCase):
    def test_known_value(self):
        candles = [candle(10, 10, 10, v=1.0), candle(20, 20, 20, v=3.0)]
        self.assertAlmostEqual(indicators.session_vwap(candles)[-1], 17.5)


class TestSwingsAndPriorDay(unittest.TestCase):
    def test_swing_high(self):
        candles = [candle(h, h - 2, h - 1) for h in [10, 11, 15, 11, 10]]
        self.assertEqual(indicators.swing_highs(candles, 2, 2), [(2, 15)])

    def test_prior_day(self):
        candles = [candle(50, 40, 45), candle(60, 55, 58), candle(70, 65, 66)]
        self.assertEqual(indicators.prior_day_high_low(candles), (60, 55))


if __name__ == "__main__":
    unittest.main()
