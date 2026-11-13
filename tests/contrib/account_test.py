import decimal
import unittest

from schwab.contrib.account import (
    account_snapshots, account_suffix, aggregate_positions, diff_positions,
    iter_position_rows, mask_account_number)

from tests.utils import no_duplicates


def payload(quantity=2, market_value=100):
    return {
        'securitiesAccount': {
            'accountId': 'stable-1',
            'accountNumber': '12345678',
            'positions': [{
                'instrument': {
                    'assetType': 'EQUITY',
                    'symbol': 'AAPL',
                    'cusip': 'CUSIP-1',
                    'description': 'Apple',
                },
                'longQuantity': quantity,
                'shortQuantity': 0,
                'marketValue': market_value,
                'averagePrice': 50,
            }],
        },
    }


class AccountTest(unittest.TestCase):

    @no_duplicates
    def test_masks_without_returning_a_short_value_in_full(self):
        self.assertEqual('...678', mask_account_number('12345678'))
        self.assertEqual('...', mask_account_number('7'))
        self.assertEqual('678', account_suffix('12345678'))
        self.assertEqual('Unknown', mask_account_number(None))
        with self.assertRaises(ValueError):
            mask_account_number('123', True)

    @no_duplicates
    def test_snapshot_keeps_short_quantity_signed(self):
        value = payload()
        position = value['securitiesAccount']['positions'][0]
        position['longQuantity'] = 0
        position['shortQuantity'] = '3.5'
        snapshot = account_snapshots(value)[0]
        self.assertEqual('stable-1', snapshot.identity.account_key)
        self.assertEqual('...678', snapshot.identity.display_label)
        self.assertEqual('678', snapshot.identity.account_suffix)
        self.assertEqual(decimal.Decimal('-3.5'),
                         snapshot.positions[0].net_quantity)

    @no_duplicates
    def test_equal_symbols_with_different_instruments_do_not_collapse(self):
        value = payload()
        second = dict(value['securitiesAccount']['positions'][0])
        second['instrument'] = dict(second['instrument'], cusip='CUSIP-2')
        value['securitiesAccount']['positions'].append(second)
        snapshot = account_snapshots(value)[0]
        self.assertEqual(2, len(snapshot.positions))
        self.assertEqual(2, len(aggregate_positions([snapshot])))

    @no_duplicates
    def test_aggregate_combines_the_same_instrument_across_accounts(self):
        first = account_snapshots(payload(2, 100))[0]
        second_payload = payload(3, 180)
        second_payload['securitiesAccount']['accountId'] = 'stable-2'
        second_payload['securitiesAccount']['accountNumber'] = '87654321'
        second_payload['securitiesAccount']['positions'][0]['averagePrice'] = 60
        second = account_snapshots(second_payload)[0]
        combined = aggregate_positions([first, second])[0]
        self.assertIsNone(combined.account_key)
        self.assertEqual(decimal.Decimal('5'), combined.net_quantity)
        self.assertEqual(decimal.Decimal('280'), combined.market_value)
        self.assertEqual(decimal.Decimal('56'), combined.average_price)

    @no_duplicates
    def test_diff_reports_add_change_and_removal(self):
        before = account_snapshots(payload(2, 100))
        after_value = payload(4, 220)
        changed = diff_positions(before, account_snapshots(after_value))
        self.assertEqual(1, len(changed))
        self.assertEqual(decimal.Decimal('2'), changed[0].quantity_change)
        self.assertEqual(decimal.Decimal('120'),
                         changed[0].market_value_change)
        removed = diff_positions(before, account_snapshots({
            'securitiesAccount': {
                'accountId': 'stable-1', 'accountNumber': '12345678'}}))
        self.assertIsNone(removed[0].after)

    @no_duplicates
    def test_rows_are_dataframe_and_csv_ready(self):
        row = next(iter_position_rows(payload()))
        self.assertEqual('...678', row['account'])
        self.assertEqual('678', row['account_suffix'])
        self.assertNotIn('account_key', row)
        self.assertEqual(decimal.Decimal('2'), row['net_quantity'])
        self.assertEqual('CUSIP-1', row['cusip'])
        private = next(iter_position_rows(
            payload(), include_account_key=True))
        self.assertEqual('stable-1', private['account_key'])

    @no_duplicates
    def test_bad_shapes_and_numbers_are_refused(self):
        with self.assertRaises(ValueError):
            account_snapshots({'securitiesAccount': {'positions': []}})
        value = payload()
        value['securitiesAccount']['positions'][0]['marketValue'] = float('nan')
        with self.assertRaises(ValueError):
            account_snapshots(value)

    @no_duplicates
    def test_validation_and_zero_weight_aggregation(self):
        self.assertEqual('Unknown', mask_account_number(''))
        self.assertEqual('...23', mask_account_number('123', visible=2))
        for visible in (-1, 0, 1.5):
            with self.assertRaises(ValueError):
                mask_account_number('123', visible)
        self.assertEqual('', account_suffix(None))
        with self.assertRaises(ValueError):
            account_suffix('123', 0)
        for bad in (None, {'securitiesAccount': None}):
            with self.assertRaises(ValueError):
                account_snapshots(bad)
        for instrument in (None, {}):
            value = payload()
            value['securitiesAccount']['positions'][0]['instrument'] = instrument
            with self.assertRaises(ValueError):
                account_snapshots(value)
        value = payload()
        value['securitiesAccount']['positions'] = {'bad': 1}
        with self.assertRaises(ValueError):
            account_snapshots(value)
        value = payload()
        value['securitiesAccount']['positions'][0]['longQuantity'] = True
        with self.assertRaises(ValueError):
            account_snapshots(value)
        value = payload()
        value['securitiesAccount']['positions'][0]['longQuantity'] = 'bad'
        with self.assertRaises(ValueError):
            account_snapshots(value)

        first = account_snapshots(payload(0, 0))[0]
        second = account_snapshots(payload(0, 0))[0]
        self.assertEqual(decimal.Decimal('0'),
                         aggregate_positions([first, second])[0].average_price)
        for function, arguments in (
                (aggregate_positions, ([None],)),
                (diff_positions, ([None], []))):
            with self.assertRaises(TypeError):
                function(*arguments)

    @no_duplicates
    def test_diff_addition_and_unchanged_positions(self):
        empty = account_snapshots({
            'securitiesAccount': {
                'accountId': 'stable-1', 'accountNumber': '12345678'}})
        added = diff_positions(empty, account_snapshots(payload()))
        self.assertIsNone(added[0].before)
        self.assertEqual(decimal.Decimal('2'), added[0].quantity_change)
        self.assertEqual(decimal.Decimal('100'), added[0].market_value_change)
        self.assertEqual((), diff_positions(
            account_snapshots(payload()), account_snapshots(payload())))
