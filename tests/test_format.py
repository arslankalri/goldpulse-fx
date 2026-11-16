import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gold_app.format import fmt_price, version_label


class TestFmtPrice(unittest.TestCase):
    def test_thousands(self):
        self.assertEqual(fmt_price(3840.99), "3,840.99")
        self.assertEqual(fmt_price(1918.5), "1,918.50")
        self.assertEqual(fmt_price(70123.456), "70,123.46")

    def test_mid(self):
        self.assertEqual(fmt_price(43.35), "43.35")
        self.assertEqual(fmt_price(576.5), "576.50")

    def test_sub_one_significant(self):
        self.assertEqual(fmt_price(0.0249), "0.0249")
        self.assertEqual(fmt_price(0.001644), "0.001644")
        self.assertEqual(fmt_price(0.01708), "0.01708")
        self.assertEqual(fmt_price(0.00001234), "0.00001234")

    def test_zero_and_none(self):
        self.assertEqual(fmt_price(0), "0")
        self.assertEqual(fmt_price(None), "-")

    def test_version_label(self):
        self.assertEqual(version_label("2.4.0"), "v2.4")
        self.assertEqual(version_label("2.4.1"), "v2.4.1")
        self.assertEqual(version_label("0.1.0"), "v0.1")


if __name__ == "__main__":
    unittest.main()
