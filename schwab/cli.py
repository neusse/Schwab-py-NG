'''Installed command-line workflows for common Schwab-py-NG tasks.'''

import argparse
import copy
import datetime
import json
import os
import sys
from decimal import Decimal

import httpx2

from . import auth
from .contrib.account import account_suffix, iter_position_rows
from .contrib.export import (iter_order_rows, iter_transaction_rows,
                             write_csv)
from .contrib.market_data import iter_candle_rows
from .doctor import configure_parser as configure_doctor_parser
from .doctor import run_cli as run_doctor


def _environment(name):
    return os.environ.get(name) or os.environ.get(name.lower())


def _client():
    values = {name: _environment(name) for name in (
        'SCHWAB_TOKEN_PATH', 'SCHWAB_API_KEY', 'SCHWAB_APP_SECRET')}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            'missing {}; set the Schwab environment variables first'.format(
                ', '.join(missing)))
    return auth.client_from_token_file(
        values['SCHWAB_TOKEN_PATH'], values['SCHWAB_API_KEY'],
        values['SCHWAB_APP_SECRET'])


def _accounts(client, selector=None):
    response = client.get_account_numbers()
    response.raise_for_status()
    accounts = []
    for item in response.json():
        number = str(item['accountNumber'])
        accounts.append({
            'number': number,
            'hash': item['hashValue'],
            'suffix': account_suffix(number),
            'label': '...{}'.format(account_suffix(number)),
        })
    if selector:
        selected = [item for item in accounts
                    if item['suffix'] == selector or item['number'] == selector]
        if not selected:
            raise RuntimeError('no linked account ends in {}'.format(selector))
        if len(selected) > 1:
            raise RuntimeError(
                'account suffix {} is ambiguous; use the full account number'
                .format(selector))
        return selected
    return accounts


def _window(args):
    now = datetime.datetime.now().astimezone()
    if getattr(args, 'today', False):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if getattr(args, 'from_date', None):
        start_date = datetime.date.fromisoformat(args.from_date)
        start = datetime.datetime.combine(
            start_date, datetime.time.min, tzinfo=now.tzinfo)
    else:
        start = now - datetime.timedelta(days=args.days)
    if getattr(args, 'to_date', None):
        end_date = datetime.date.fromisoformat(args.to_date)
        end = datetime.datetime.combine(
            end_date + datetime.timedelta(days=1), datetime.time.min,
            tzinfo=now.tzinfo)
    else:
        end = now
    if start > end:
        raise RuntimeError('--from must not be later than --to')
    if start < now - datetime.timedelta(days=60, minutes=5):
        raise RuntimeError('Schwab limits these endpoints to the last 60 days')
    return start, end


def _json_default(value):
    if isinstance(value, (datetime.date, datetime.datetime, Decimal)):
        return str(value)
    raise TypeError('{} is not JSON serializable'.format(type(value).__name__))


def _print_table(rows, columns):
    materialized = [[str(row.get(key, '') or '') for key, _ in columns]
                    for row in rows]
    headings = [heading for _, heading in columns]
    widths = [len(value) for value in headings]
    for row in materialized:
        widths = [max(width, len(value))
                  for width, value in zip(widths, row)]
    print('  '.join(value.ljust(width)
                    for value, width in zip(headings, widths)))
    print('  '.join('-' * width for width in widths))
    for row in materialized:
        print('  '.join(value.ljust(width)
                        for value, width in zip(row, widths)))


def _emit(rows, args, columns, summary=None):
    rows = list(rows)
    if args.csv:
        count = write_csv(args.csv, rows)
        print('Wrote {} rows to {}'.format(count, args.csv))
    elif args.json:
        print(json.dumps(rows, indent=2, default=_json_default))
    else:
        _print_table(rows, columns)
    if summary and not args.json:
        print(summary)
    return rows


def _date_arguments(parser, default_days=60):
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--today', action='store_true')
    group.add_argument('--days', type=int, default=default_days)
    parser.add_argument('--from', dest='from_date', metavar='YYYY-MM-DD')
    parser.add_argument('--to', dest='to_date', metavar='YYYY-MM-DD')


def _output_arguments(parser):
    output = parser.add_mutually_exclusive_group()
    output.add_argument('--csv', metavar='PATH')
    output.add_argument('--json', action='store_true')


def _account_argument(parser):
    parser.add_argument(
        '--account', metavar='LAST3',
        help='limit output to the linked account ending in these digits')


def _tag_order(order, number):
    tagged = copy.deepcopy(order)
    tagged['accountNumber'] = number
    return tagged


def _order_summary_rows(rows):
    orders = {row['order_path']: dict(row)
              for row in rows if row['record_type'] == 'order'}
    legs = {}
    for row in rows:
        if row['record_type'] == 'order_leg':
            legs.setdefault(row['order_path'], []).append(row)
    summaries = []
    for path, order in orders.items():
        order_legs = legs.get(path, ())
        summaries.append({
            'account': order['account'],
            'order_path': path,
            'order_id': order['order_id'],
            'entered_time': order.get('entered_time'),
            'status': order.get('status'),
            'side': ','.join(str(leg.get('instruction') or '')
                            for leg in order_legs),
            'symbol': ','.join(str(leg.get('symbol') or '')
                              for leg in order_legs),
            'quantity': (order.get('quantity') or ','.join(
                str(leg.get('quantity') or '') for leg in order_legs)),
            'order_type': order.get('order_type'),
            'price': order.get('price'),
        })
    return summaries


def run_orders(args):
    '''Fetch per-account orders and render a table, CSV, or JSON.'''
    client = _client()
    start, end = _window(args)
    status = client.Order.Status[args.status] if args.status else None
    orders = []
    selected = _accounts(client, args.account)
    for account in selected:
        response = client.get_orders_for_account(
            account['hash'], max_results=args.max_results,
            from_entered_datetime=start, to_entered_datetime=end,
            status=status)
        response.raise_for_status()
        orders.extend(_tag_order(order, account['number'])
                      for order in response.json())
    rows = list(iter_order_rows(orders))
    top_count = sum(1 for row in rows
                    if row['record_type'] == 'order'
                    and '.' not in row['order_path'])
    if args.compare_endpoints:
        response = client.get_orders_for_all_linked_accounts(
            max_results=args.max_results, from_entered_datetime=start,
            to_entered_datetime=end, status=status)
        response.raise_for_status()
        print('Endpoint comparison: per-account={} all-linked={}'.format(
            len(orders), len(response.json())))
    if not rows and not args.json:
        print('Schwab Trader API returned zero orders for the selected window.')
        return []
    displayed = rows if args.csv or args.json else _order_summary_rows(rows)
    _emit(displayed, args, (
        ('account', 'Account'), ('order_id', 'Order ID'),
        ('entered_time', 'Entered'), ('status', 'Status'),
        ('side', 'Side'), ('symbol', 'Symbol'), ('quantity', 'Quantity'),
        ('order_type', 'Type'), ('price', 'Price')),
        '{} top-level orders; {} related rows; source: Schwab Trader API'
        .format(top_count, len(rows)))
    return rows


def run_positions(args):
    '''Fetch linked-account positions and render a table, CSV, or JSON.'''
    client = _client()
    rows = []
    for account in _accounts(client, args.account):
        response = client.get_account(
            account['hash'], fields=[client.Account.Fields.POSITIONS])
        response.raise_for_status()
        payload = copy.deepcopy(response.json())
        info = payload.setdefault('securitiesAccount', {})
        info['accountNumber'] = account['number']
        info.setdefault('hashValue', account['hash'])
        rows.extend(iter_position_rows(payload))
    if not rows and not args.json:
        print('Schwab Trader API returned zero positions.')
        return []
    return _emit(rows, args, (
        ('account', 'Account'), ('symbol', 'Symbol'),
        ('net_quantity', 'Quantity'), ('market_value', 'Market value'),
        ('average_price', 'Average price'),
        ('day_profit_loss', 'Day P/L')),
        '{} positions; source: Schwab Trader API'.format(len(rows)))


def run_transactions(args):
    '''Fetch per-account transactions and render a table, CSV, or JSON.'''
    client = _client()
    start, end = _window(args)
    rows = []
    for account in _accounts(client, args.account):
        response = client.get_transactions(
            account['hash'], start_date=start, end_date=end,
            symbol=args.symbol)
        response.raise_for_status()
        for transaction in response.json():
            tagged = copy.deepcopy(transaction)
            tagged['accountNumber'] = account['number']
            rows.extend(iter_transaction_rows(tagged))
    if not rows and not args.json:
        print('Schwab Trader API returned zero transactions for the selected window.')
        return []
    return _emit(rows, args, (
        ('account', 'Account'), ('record_type', 'Record'),
        ('trade_date', 'Trade date'), ('type', 'Type'),
        ('symbol', 'Symbol'), ('amount', 'Amount'),
        ('net_amount', 'Net amount'), ('description', 'Description')),
        '{} related rows; source: Schwab Trader API'.format(len(rows)))


def run_candles(args):
    '''Fetch common price-history intervals and render table, CSV, or JSON.'''
    client = _client()
    start, end = _window(args)
    method = getattr(client, 'get_price_history_every_{}'.format(args.every))
    response = method(
        args.symbol.upper(), start_datetime=start, end_datetime=end)
    response.raise_for_status()
    rows = list(iter_candle_rows(response.json()))
    return _emit(rows, args, (
        ('symbol', 'Symbol'), ('datetime_utc', 'Time (UTC)'),
        ('open', 'Open'), ('high', 'High'), ('low', 'Low'),
        ('close', 'Close'), ('volume', 'Volume')),
        '{} candles; source: Schwab Market Data API'.format(len(rows)))


def build_parser(prog='schwab-ng'):
    '''Build the top-level command parser.'''
    parser = argparse.ArgumentParser(
        prog=prog, description='Useful Schwab-py-NG command-line workflows.')
    commands = parser.add_subparsers(dest='command', required=True)

    doctor = commands.add_parser('doctor', help='diagnose installation and access')
    configure_doctor_parser(doctor)
    doctor.set_defaults(handler=run_doctor)

    orders = commands.add_parser('orders', help='list or export orders')
    _account_argument(orders)
    _date_arguments(orders)
    _output_arguments(orders)
    orders.add_argument('--status', choices=(
        'AWAITING_PARENT_ORDER', 'AWAITING_CONDITION', 'AWAITING_STOP_CONDITION',
        'AWAITING_MANUAL_REVIEW', 'ACCEPTED', 'AWAITING_UR_OUT',
        'PENDING_ACTIVATION', 'QUEUED', 'WORKING', 'REJECTED',
        'PENDING_CANCEL', 'CANCELED', 'PENDING_REPLACE', 'REPLACED',
        'FILLED', 'EXPIRED', 'NEW', 'AWAITING_RELEASE_TIME',
        'PENDING_ACKNOWLEDGEMENT', 'PENDING_RECALL', 'UNKNOWN'))
    orders.add_argument('--max-results', type=int)
    orders.add_argument('--compare-endpoints', action='store_true')
    orders.set_defaults(handler=run_orders)

    positions = commands.add_parser('positions', help='list or export positions')
    _account_argument(positions)
    _output_arguments(positions)
    positions.set_defaults(handler=run_positions)

    transactions = commands.add_parser(
        'transactions', help='list or export transactions')
    _account_argument(transactions)
    _date_arguments(transactions)
    _output_arguments(transactions)
    transactions.add_argument('--symbol')
    transactions.set_defaults(handler=run_transactions)

    candles = commands.add_parser('candles', help='fetch price-history candles')
    candles.add_argument('symbol')
    candles.add_argument('--every', choices=(
        'minute', 'five_minutes', 'ten_minutes', 'fifteen_minutes',
        'thirty_minutes', 'hour', 'day', 'week'), default='day')
    _date_arguments(candles, default_days=5)
    _output_arguments(candles)
    candles.set_defaults(handler=run_candles)
    return parser


def main(argv=None):
    '''Run the ``schwab-ng`` command family and return an exit status.'''
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = args.handler(args)
        return result if isinstance(result, int) else 0
    except httpx2.HTTPError as exc:
        response = getattr(exc, 'response', None)
        status = getattr(response, 'status_code', None)
        detail = 'HTTP {}'.format(status) if status is not None else type(exc).__name__
        print('schwab-ng: Trader API request failed ({})'.format(detail),
              file=sys.stderr)
        return 1
    except (KeyError, RuntimeError, ValueError) as exc:
        print('schwab-ng: error: {}'.format(exc), file=sys.stderr)
        return 2


def _alias(command, argv=None):
    return main([command] + list(sys.argv[1:] if argv is None else argv))


def orders_main(argv=None):
    '''Run the standalone ``schwab-ng-orders`` alias.'''
    return _alias('orders', argv)


def positions_main(argv=None):
    '''Run the standalone ``schwab-ng-positions`` alias.'''
    return _alias('positions', argv)


def transactions_main(argv=None):
    '''Run the standalone ``schwab-ng-transactions`` alias.'''
    return _alias('transactions', argv)


def candles_main(argv=None):
    '''Run the standalone ``schwab-ng-candles`` alias.'''
    return _alias('candles', argv)
