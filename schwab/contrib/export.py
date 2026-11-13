'''Turn nested Schwab orders and transactions into stable, related rows.'''

import csv
import json
import os
from collections.abc import Iterable, Mapping
from decimal import Decimal

from .account import mask_account_number


def _sequence(value, field):
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError('{} must be an array'.format(field))
    return value


def _object(value, field):
    if not isinstance(value, Mapping):
        raise ValueError('{} must be an object'.format(field))
    return value


def _order_rows(order, path, parent_order_id, inherited_account='Unknown'):
    order = _object(order, 'order')
    order_id = order.get('orderId')
    account = (mask_account_number(order.get('accountNumber'))
               if order.get('accountNumber') not in (None, '')
               else inherited_account)
    base = {
        'order_path': path,
        'order_id': order_id,
        'parent_order_id': parent_order_id,
        'account': account,
    }
    yield {
        **base,
        'record_type': 'order',
        'status': order.get('status'),
        'entered_time': order.get('enteredTime'),
        'close_time': order.get('closeTime'),
        'order_type': order.get('orderType'),
        'session': order.get('session'),
        'duration': order.get('duration'),
        'price': order.get('price'),
        'stop_price': order.get('stopPrice'),
        'quantity': order.get('quantity'),
        'filled_quantity': order.get('filledQuantity'),
        'remaining_quantity': order.get('remainingQuantity'),
        'complex_order_strategy_type': order.get('complexOrderStrategyType'),
        'order_strategy_type': order.get('orderStrategyType'),
        'cancelable': order.get('cancelable'),
        'editable': order.get('editable'),
    }

    legs = _sequence(order.get('orderLegCollection'), 'orderLegCollection')
    leg_ids = {}
    for index, leg in enumerate(legs):
        leg = _object(leg, 'order leg')
        instrument = _object(leg.get('instrument', {}), 'order instrument')
        leg_id = leg.get('legId', index)
        leg_ids[str(leg_id)] = index
        yield {
            **base,
            'record_type': 'order_leg',
            'leg_index': index,
            'leg_id': leg_id,
            'instruction': leg.get('instruction'),
            'position_effect': leg.get('positionEffect'),
            'quantity': leg.get('quantity'),
            'quantity_type': leg.get('quantityType'),
            'asset_type': instrument.get('assetType'),
            'symbol': instrument.get('symbol'),
            'cusip': instrument.get('cusip'),
            'instrument_id': instrument.get('instrumentId'),
            'description': instrument.get('description'),
            'put_call': instrument.get('putCall'),
            'underlying_symbol': instrument.get('underlyingSymbol'),
        }

    activities = _sequence(order.get('orderActivityCollection'),
                           'orderActivityCollection')
    for activity_index, activity in enumerate(activities):
        activity = _object(activity, 'order activity')
        executions = _sequence(activity.get('executionLegs'), 'executionLegs')
        if not executions:
            yield {
                **base,
                'record_type': 'order_activity',
                'activity_index': activity_index,
                'activity_type': activity.get('activityType'),
                'execution_type': activity.get('executionType'),
                'quantity': activity.get('quantity'),
                'remaining_quantity': activity.get('remainingQuantity'),
            }
        for execution_index, execution in enumerate(executions):
            execution = _object(execution, 'execution leg')
            leg_id = execution.get('legId')
            yield {
                **base,
                'record_type': 'execution_leg',
                'activity_index': activity_index,
                'execution_index': execution_index,
                'activity_type': activity.get('activityType'),
                'execution_type': activity.get('executionType'),
                'leg_id': leg_id,
                'leg_index': leg_ids.get(str(leg_id)),
                'quantity': execution.get('quantity'),
                'price': execution.get('price'),
                'time': execution.get('time'),
            }

    children = _sequence(order.get('childOrderStrategies'),
                         'childOrderStrategies')
    for child_index, child in enumerate(children):
        child_path = '{}.{}'.format(path, child_index)
        yield from _order_rows(child, child_path, order_id, account)


def iter_order_rows(orders):
    '''Yield order, leg, activity, and execution rows without losing hierarchy.

    ``order_path`` is stable within the supplied tree: ``0`` is the first
    top-level order, ``0.1`` its second child, and so on.  ``record_type``
    identifies the schema of each row.
    '''
    if isinstance(orders, Mapping):
        orders = [orders]
    for index, order in enumerate(_sequence(orders, 'orders')):
        yield from _order_rows(order, str(index), None)


def iter_transaction_rows(transactions):
    '''Yield one transaction row and one row per transfer item.

    The parent is related to every child by ``transaction_index`` and
    ``transaction_id``. Variable-length transfer arrays therefore remain rows
    instead of becoming unstable ``transfer_0_*`` columns.
    '''
    if isinstance(transactions, Mapping):
        transactions = [transactions]
    for transaction_index, transaction in enumerate(
            _sequence(transactions, 'transactions')):
        transaction = _object(transaction, 'transaction')
        transaction_id = transaction.get('activityId',
                                         transaction.get('transactionId'))
        account = mask_account_number(transaction.get('accountNumber'))
        base = {
            'transaction_index': transaction_index,
            'transaction_id': transaction_id,
            'account': account,
        }
        yield {
            **base,
            'record_type': 'transaction',
            'type': transaction.get('type'),
            'status': transaction.get('status'),
            'sub_account': transaction.get('subAccount'),
            'trade_date': transaction.get('tradeDate'),
            'settlement_date': transaction.get('settlementDate'),
            'position_id': transaction.get('positionId'),
            'net_amount': transaction.get('netAmount'),
            'description': transaction.get('description'),
        }
        items = _sequence(transaction.get('transferItems'), 'transferItems')
        for item_index, item in enumerate(items):
            item = _object(item, 'transfer item')
            instrument = _object(item.get('instrument', {}),
                                 'transfer instrument')
            yield {
                **base,
                'record_type': 'transfer_item',
                'item_index': item_index,
                'amount': item.get('amount'),
                'cost': item.get('cost'),
                'price': item.get('price'),
                'fee_type': item.get('feeType'),
                'position_effect': item.get('positionEffect'),
                'asset_type': instrument.get('assetType'),
                'symbol': instrument.get('symbol'),
                'cusip': instrument.get('cusip'),
                'instrument_id': instrument.get('instrumentId'),
                'description': instrument.get('description'),
                'put_call': instrument.get('putCall'),
                'underlying_symbol': instrument.get('underlyingSymbol'),
            }


def _csv_value(value):
    if value is None:
        return ''
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(',', ':'))
    return value


def write_csv(path, rows):
    '''Write heterogeneous rows to UTF-8 CSV and return the number written.

    Column order follows first appearance across the input. ``path`` may be a
    path-like value or a text file object opened with ``newline=''``.
    '''
    if not isinstance(rows, Iterable):
        raise TypeError('rows must be iterable')
    materialized, fieldnames = [], []
    seen = set()
    for row in rows:
        row = _object(row, 'row')
        converted = {str(key): _csv_value(value)
                     for key, value in row.items()}
        materialized.append(converted)
        for key in converted:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    owns_file = isinstance(path, (str, bytes, os.PathLike))
    output = (open(path, 'w', encoding='utf-8', newline='')
              if owns_file else path)
    if not hasattr(output, 'write'):
        raise TypeError('path must be path-like or a writable text file')
    try:
        if fieldnames:
            writer = csv.DictWriter(output, fieldnames=fieldnames,
                                    extrasaction='raise')
            writer.writeheader()
            writer.writerows(materialized)
    finally:
        if owns_file:
            output.close()
    return len(materialized)
