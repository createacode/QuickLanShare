from __future__ import annotations

import unittest

from quicklanshare.services.filestream import RangeNotSatisfiable, parse_range


class ParseRangeTests(unittest.TestCase):
    size = 17_900_000_000

    def test_full_prefix(self):
        self.assertEqual(parse_range("bytes=0-2147483647", self.size), (0, 2147483647))

    def test_start_beyond_2gb(self):
        self.assertEqual(parse_range("bytes=2147483648-", self.size), (2147483648, self.size - 1))

    def test_suffix(self):
        self.assertEqual(parse_range("bytes=-100", self.size), (self.size - 100, self.size - 1))

    def test_end_clamped(self):
        self.assertEqual(parse_range("bytes=0-999999999999", self.size), (0, self.size - 1))

    def test_small_file(self):
        self.assertEqual(parse_range("bytes=2-4", 10), (2, 4))

    def test_invalid_ranges(self):
        for header in ("bytes=10-2", "bytes=99-", "bytes=-0", "bytes=abc"):
            with self.subTest(header=header):
                with self.assertRaises(RangeNotSatisfiable):
                    parse_range(header, 10)

    def test_non_range_header_is_ignored(self):
        self.assertIsNone(parse_range(None, 10))
        self.assertIsNone(parse_range("", 10))
        self.assertIsNone(parse_range("items=0-1", 10))


if __name__ == "__main__":
    unittest.main()
