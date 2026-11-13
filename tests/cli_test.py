import argparse
import datetime
import io
import tempfile
import unittest
from enum import Enum
from pathlib import Path
from unittest.mock import patch

import httpx2

from schwab import cli

from tests.utils import no_duplicates


class Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


class FakeClient:
    class Order:
        class Status(Enum):
            FILLED = 'FILLED'

    class Account:
        class Fields(Enum):
            POSITIONS = 'positions'

    def __init__(self):
        self.orders = []
        self.all_orders = []
        self.positions = []
        self.transactions = []
        self.candles = {'symbol': 'AAPL', 'candles': []}
        self.calls = []

    def get_account_numbers(self):
        return Response([
            {'accountNumber': '123456570', 'hashValue': 'hash-570'},
            {'accountNumber': '123456915', 'hashValue': 'hash-915'},
        ])

    def get_orders_for_account(self, account_hash, **kwargs):
        self.calls.append(('orders', account_hash, kwargs))
        return Response(self.orders)

    def get_orders_for_all_linked_accounts(self, **kwargs):
        return Response(self.all_orders)

    def get_account(self, account_hash, **kwargs):
        self.calls.append(('positions', account_hash, kwargs))
        return Response({'securitiesAccount': {'positions': self.positions}})

    def get_transactions(self, account_hash, **kwargs):
        self.calls.append(('transactions', account_hash, kwargs))
        return Response(self.transactions)

    def get_price_history_every_hour(self, symbol, **kwargs):
        self.calls.append(('candles', symbol, kwargs))
        return Response(self.candles)


def args(**overrides):
    values = {
        'account': None, 'today': True, 'days': 60,
        'from_date': None, 'to_date': None, 'csv': None, 'json': False,
        'status': None, 'max_results': None, 'compare_endpoints': False,
        'symbol': None, 'every': 'hour',
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class CliTest(unittest.TestCase):

    @no_duplicates
    def test_client_requires_environment_and_uses_auth(self):
        with patch('schwab.cli._environment', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'SCHWAB_TOKEN_PATH'):
                cli._client()
        values = iter(('token', 'key', 'secret'))
        with patch('schwab.cli._environment', side_effect=lambda name: next(values)), \
             patch('schwab.cli.auth.client_from_token_file',
                   return_value='client') as factory:
            self.assertEqual('client', cli._client())
        factory.assert_called_once_with('token', 'key', 'secret')

    @no_duplicates
    def test_account_suffix_selection_and_errors(self):
        client = FakeClient()
        self.assertEqual('570', cli._accounts(client, '570')[0]['suffix'])
        with self.assertRaisesRegex(RuntimeError, 'no linked account'):
            cli._accounts(client, '999')
        response = Response([
            {'accountNumber': '111570', 'hashValue': 'one'},
            {'accountNumber': '222570', 'hashValue': 'two'}])
        client.get_account_numbers = lambda: response
        with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
            cli._accounts(client, '570')

    @no_duplicates
    def test_date_window_today_explicit_and_invalid(self):
        start, end = cli._window(args())
        self.assertEqual(0, start.hour)
        self.assertGreater(end, start)
        start, end = cli._window(args(
            today=False, days=2, from_date='2026-11-10',
            to_date='2026-11-11'))
        self.assertEqual(datetime.date(2026, 11, 10), start.date())
        self.assertEqual(datetime.date(2026, 11, 12), end.date())
        with self.assertRaisesRegex(RuntimeError, 'must not be later'):
            cli._window(args(today=False, days=2,
                             from_date='2026-11-12', to_date='2026-11-10'))

    @no_duplicates
    def test_orders_use_per_account_endpoint_suffix_and_compare(self):
        client = FakeClient()
        client.orders = [{
            'orderId': 5, 'status': 'FILLED', 'enteredTime': 'today',
            'orderType': 'MARKET', 'quantity': 10,
            'orderLegCollection': [{'instruction': 'BUY', 'quantity': 10,
                                    'instrument': {'symbol': 'SGOV'}}],
        }]
        client.all_orders = [client.orders[0]]
        output = io.StringIO()
        with patch('schwab.cli._client', return_value=client), \
             patch('sys.stdout', output):
            rows = cli.run_orders(args(
                account='570', status='FILLED', compare_endpoints=True))
        self.assertEqual({'...570'}, {row['account'] for row in rows})
        self.assertIn('Endpoint comparison: per-account=1 all-linked=1',
                      output.getvalue())
        self.assertIn('1 top-level orders; 2 related rows', output.getvalue())
        self.assertEqual(FakeClient.Order.Status.FILLED,
                         client.calls[0][2]['status'])

    @no_duplicates
    def test_orders_zero_is_truthful_and_csv_exports_related_rows(self):
        client = FakeClient()
        with patch('schwab.cli._client', return_value=client), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual([], cli.run_orders(args(account='570')))
        self.assertIn('Schwab Trader API returned zero orders', output.getvalue())
        client.orders = [{'orderId': 1, 'status': 'WORKING'}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'orders.csv'
            with patch('schwab.cli._client', return_value=client), \
                 patch('sys.stdout', new_callable=io.StringIO):
                cli.run_orders(args(account='570', csv=path))
            self.assertIn('account_suffix', path.read_text(encoding='utf-8'))

    @no_duplicates
    def test_positions_transactions_and_candles(self):
        client = FakeClient()
        client.positions = [{
            'longQuantity': 2, 'marketValue': 200,
            'instrument': {'assetType': 'EQUITY', 'symbol': 'AAPL'}}]
        client.transactions = [{
            'activityId': 9, 'type': 'TRADE', 'tradeDate': '2026-11-13',
            'transferItems': [{'amount': 2,
                               'instrument': {'symbol': 'AAPL'}}]}]
        client.candles = {'symbol': 'AAPL', 'candles': [{
            'datetime': 1000, 'open': 1, 'high': 2, 'low': 1,
            'close': 2, 'volume': 3}]}
        with patch('schwab.cli._client', return_value=client), \
             patch('sys.stdout', new_callable=io.StringIO):
            positions = cli.run_positions(args(account='915', json=True))
            transactions = cli.run_transactions(args(
                account='570', symbol='AAPL', json=True))
            candles = cli.run_candles(args(symbol='aapl', json=True))
        self.assertEqual('...915', positions[0]['account'])
        self.assertEqual('...570', transactions[0]['account'])
        self.assertEqual('AAPL', candles[0]['symbol'])
        self.assertEqual(('candles', 'AAPL'), client.calls[-1][:2])
        self.assertIn('start_datetime', client.calls[-1][2])

    @no_duplicates
    def test_empty_positions_and_transactions_report_source(self):
        client = FakeClient()
        with patch('schwab.cli._client', return_value=client), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual([], cli.run_positions(args(account='570')))
            self.assertEqual([], cli.run_transactions(args(account='570')))
        self.assertIn('zero positions', output.getvalue())
        self.assertIn('zero transactions', output.getvalue())

    @no_duplicates
    def test_parser_main_error_doctor_and_aliases(self):
        parser = cli.build_parser('test')
        self.assertEqual('orders', parser.parse_args(['orders']).command)
        with patch('schwab.cli.run_doctor', return_value=7):
            # The handler reference is captured while the parser is built.
            pass
        with patch('schwab.cli._client', side_effect=RuntimeError('missing')), \
             patch('sys.stderr', new_callable=io.StringIO) as error:
            self.assertEqual(2, cli.main(['positions']))
        self.assertIn('missing', error.getvalue())
        request = httpx2.Request('GET', 'https://example.test/private-hash')
        response = httpx2.Response(429, request=request)
        failure = httpx2.HTTPStatusError(
            'private-hash', request=request, response=response)
        with patch('schwab.cli._client', side_effect=failure), \
             patch('sys.stderr', new_callable=io.StringIO) as error:
            self.assertEqual(1, cli.main(['positions']))
        self.assertIn('HTTP 429', error.getvalue())
        self.assertNotIn('private-hash', error.getvalue())
        with patch('schwab.cli.main', return_value=0) as main:
            self.assertEqual(0, cli.orders_main(['--today']))
            self.assertEqual(0, cli.positions_main([]))
            self.assertEqual(0, cli.transactions_main([]))
            self.assertEqual(0, cli.candles_main(['AAPL']))
        self.assertEqual(4, main.call_count)
