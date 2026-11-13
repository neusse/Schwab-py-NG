import io
import tempfile
import unittest
from decimal import Decimal

from schwab.contrib.export import (
    iter_order_rows, iter_transaction_rows, write_csv)

from tests.utils import no_duplicates


class ExportTest(unittest.TestCase):

    @no_duplicates
    def test_order_rows_preserve_tree_legs_and_executions(self):
        orders = [{
            'orderId': 10,
            'accountNumber': '12345678',
            'status': 'FILLED',
            'orderLegCollection': [{
                'legId': 7,
                'instruction': 'BUY',
                'quantity': 2,
                'instrument': {'assetType': 'EQUITY', 'symbol': 'AAPL'},
            }],
            'orderActivityCollection': [{
                'activityType': 'EXECUTION',
                'executionLegs': [{'legId': 7, 'quantity': 2, 'price': 100}],
            }],
            'childOrderStrategies': [{
                'orderId': 11,
                'orderLegCollection': [{
                    'instruction': 'SELL',
                    'quantity': 2,
                    'instrument': {'assetType': 'EQUITY', 'symbol': 'AAPL'},
                }],
            }],
        }]
        rows = list(iter_order_rows(orders))
        self.assertEqual(
            ['order', 'order_leg', 'execution_leg', 'order', 'order_leg'],
            [row['record_type'] for row in rows])
        self.assertEqual('0.0', rows[3]['order_path'])
        self.assertEqual(10, rows[3]['parent_order_id'])
        self.assertEqual('...678', rows[3]['account'])
        self.assertEqual('678', rows[3]['account_suffix'])
        self.assertEqual(0, rows[2]['leg_index'])
        self.assertEqual('...678', rows[0]['account'])

    @no_duplicates
    def test_transaction_rows_keep_variable_items_as_rows(self):
        rows = list(iter_transaction_rows([{
            'activityId': 42,
            'accountNumber': '12345678',
            'type': 'TRADE',
            'transferItems': [
                {'amount': 2, 'instrument': {'symbol': 'AAPL'}},
                {'amount': -200, 'instrument': {'symbol': 'CURRENCY_USD'}},
            ],
        }]))
        self.assertEqual(['transaction', 'transfer_item', 'transfer_item'],
                         [row['record_type'] for row in rows])
        self.assertEqual([0, 1], [rows[1]['item_index'], rows[2]['item_index']])
        self.assertEqual(42, rows[2]['transaction_id'])
        self.assertEqual('678', rows[2]['account_suffix'])

    @no_duplicates
    def test_write_csv_unions_columns_in_first_seen_order(self):
        output = io.StringIO(newline='')
        count = write_csv(output, [{'a': 1}, {'b': 2, 'a': 3}])
        self.assertEqual(2, count)
        self.assertEqual('a,b\r\n1,\r\n3,2\r\n', output.getvalue())

    @no_duplicates
    def test_bad_nested_shapes_are_refused(self):
        with self.assertRaises(ValueError):
            list(iter_order_rows([{'orderLegCollection': {}}]))
        with self.assertRaises(ValueError):
            list(iter_transaction_rows([{'transferItems': [None]}]))

    @no_duplicates
    def test_mapping_inputs_empty_activity_and_csv_values(self):
        rows = list(iter_order_rows({
            'orderActivityCollection': [{'activityType': 'CANCEL'}]}))
        self.assertEqual(['order', 'order_activity'],
                         [row['record_type'] for row in rows])
        self.assertEqual('Unknown', rows[0]['account'])
        transaction = list(iter_transaction_rows({'transactionId': 9}))
        self.assertEqual(9, transaction[0]['transaction_id'])

        output = io.StringIO(newline='')
        write_csv(output, [{'none': None, 'decimal': Decimal('1.20'),
                            'nested': {'b': 2, 'a': 1}}])
        self.assertIn(',1.20,"{""a"":1,""b"":2}"', output.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/rows.csv'
            self.assertEqual(1, write_csv(path, [{'a': 1}]))
            with open(path, encoding='utf-8') as saved:
                self.assertEqual('a\n1\n', saved.read().replace('\r\n', '\n'))
        self.assertEqual(0, write_csv(io.StringIO(), []))

    @no_duplicates
    def test_export_validation_errors(self):
        for producer, value in (
                (iter_order_rows, 1),
                (iter_order_rows, [None]),
                (iter_order_rows, [{'orderLegCollection': [None]}]),
                (iter_order_rows, [{'orderLegCollection': [
                    {'instrument': None}]}]),
                (iter_order_rows, [{'orderActivityCollection': [None]}]),
                (iter_order_rows, [{'orderActivityCollection': [
                    {'executionLegs': [None]}]}]),
                (iter_transaction_rows, 1)):
            with self.assertRaises(ValueError):
                list(producer(value))
        with self.assertRaises(TypeError):
            write_csv(io.StringIO(), 1)
        with self.assertRaises(ValueError):
            write_csv(io.StringIO(), [None])
        with self.assertRaises(TypeError):
            write_csv(object(), [])
