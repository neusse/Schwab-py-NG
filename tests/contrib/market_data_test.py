import datetime
import decimal
import unittest

from schwab.contrib.market_data import (
    aggregate_candles, iter_candle_rows, iter_quote_rows, millis_to_datetime)

from tests.utils import no_duplicates


def candle(timestamp, open_, high, low, close, volume, symbol='AAPL'):
    return {'datetime': timestamp, 'open': open_, 'high': high, 'low': low,
            'close': close, 'volume': volume, 'symbol': symbol}


class MarketDataTest(unittest.TestCase):

    @no_duplicates
    def test_quote_rows_flatten_unknown_nested_fields(self):
        row = next(iter_quote_rows({'AAPL': {
            'symbol': 'AAPL',
            'quote': {'lastPrice': 100},
            'newSection': {'newField': 7},
        }}))
        self.assertEqual(100, row['quote.lastPrice'])
        self.assertEqual(7, row['newSection.newField'])

    @no_duplicates
    def test_candle_rows_add_symbol_and_utc_datetime(self):
        row = next(iter_candle_rows({
            'symbol': 'AAPL',
            'candles': [candle(0, 1, 2, 0, 1, 5, symbol=None)],
        }))
        self.assertEqual('AAPL', row['symbol'])
        self.assertEqual(datetime.datetime(1970, 1, 1,
                                           tzinfo=datetime.timezone.utc),
                         row['datetime_utc'])
        self.assertEqual(row['datetime_utc'], millis_to_datetime(0))

    @no_duplicates
    def test_aggregate_uses_exact_groups_and_drops_gaps(self):
        minute = 60 * 1000
        candles = [
            candle(0, 10, 12, 9, 11, 100),
            candle(minute, 11, 14, 10, 13, 200),
            candle(3 * minute, 20, 21, 19, 20, 5),
            candle(4 * minute, 20, 23, 18, 22, 7),
        ]
        rows = aggregate_candles(
            candles, source_minutes=1, target_minutes=2)
        self.assertEqual([0, 3 * minute], [row['datetime'] for row in rows])
        self.assertEqual(decimal.Decimal('10'), rows[0]['open'])
        self.assertEqual(decimal.Decimal('14'), rows[0]['high'])
        self.assertEqual(decimal.Decimal('9'), rows[0]['low'])
        self.assertEqual(decimal.Decimal('13'), rows[0]['close'])
        self.assertEqual(decimal.Decimal('300'), rows[0]['volume'])

    @no_duplicates
    def test_duplicate_timestamp_replaces_and_symbols_stay_separate(self):
        minute = 60 * 1000
        candles = [
            candle(0, 1, 1, 1, 1, 1),
            candle(0, 2, 2, 2, 2, 2),
            candle(minute, 3, 3, 3, 3, 3),
            candle(0, 4, 4, 4, 4, 4, 'MSFT'),
            candle(minute, 5, 5, 5, 5, 5, 'MSFT'),
        ]
        rows = aggregate_candles(
            candles, source_minutes=1, target_minutes=2)
        self.assertEqual(['AAPL', 'MSFT'], [row['symbol'] for row in rows])
        self.assertEqual(decimal.Decimal('2'), rows[0]['open'])

    @no_duplicates
    def test_invalid_parameters_and_candles_are_refused(self):
        with self.assertRaises(ValueError):
            aggregate_candles([], source_minutes=5, target_minutes=7)
        with self.assertRaises(ValueError):
            aggregate_candles(
                [{'datetime': 0}], source_minutes=1, target_minutes=2)
        with self.assertRaises(ValueError):
            millis_to_datetime(True)

    @no_duplicates
    def test_conversion_shape_and_numeric_validation(self):
        for value in ('bad', float('inf'), 10 ** 30):
            with self.assertRaises(ValueError):
                millis_to_datetime(value)
        row = next(iter_quote_rows({'AAPL': {
            'values': [1, {'b': 2}], 'symbol': ''}}))
        self.assertEqual('[1,{"b":2}]', row['values'])
        self.assertEqual('AAPL', row['symbol'])
        for payload in (None, {'AAPL': None}):
            with self.assertRaises(ValueError):
                list(iter_quote_rows(payload))

        invalid_candles = (
            None,
            {'candles': {'bad': 1}},
            {'candles': [None]},
            {'candles': [{}]},
        )
        for value in invalid_candles:
            with self.assertRaises(ValueError):
                list(iter_candle_rows(value))

    @no_duplicates
    def test_aggregate_rejects_every_invalid_input_shape(self):
        for source, target in ((True, 2), (1, False), (0, 2), (2, 2)):
            with self.assertRaises(ValueError):
                aggregate_candles([], source_minutes=source,
                                  target_minutes=target)
        invalid = (
            None,
            {},
            candle(1.5, 1, 1, 1, 1, 1),
            candle(0, True, 1, 1, 1, 1),
            candle(0, 'bad', 1, 1, 1, 1),
            candle(0, float('inf'), 1, 1, 1, 1),
        )
        for value in invalid:
            with self.assertRaises(ValueError):
                aggregate_candles([value], source_minutes=1,
                                  target_minutes=2)

    @no_duplicates
    def test_aggregate_symbol_is_optional(self):
        rows = aggregate_candles([
            candle(0, 1, 1, 1, 1, 1, None),
            candle(60_000, 1, 1, 1, 1, 1, None),
        ], source_minutes=1, target_minutes=2)
        self.assertNotIn('symbol', rows[0])
