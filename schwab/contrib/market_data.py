'''Dependency-free conversion helpers for Schwab quotes and candles.'''

import datetime
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation


def millis_to_datetime(value):
    '''Convert Unix milliseconds to a timezone-aware UTC ``datetime``.'''
    if isinstance(value, bool):
        raise ValueError('milliseconds must be numeric')
    try:
        milliseconds = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('milliseconds must be numeric') from exc
    if not milliseconds.is_finite():
        raise ValueError('milliseconds must be finite')
    try:
        return datetime.datetime.fromtimestamp(
            float(milliseconds / 1000), tz=datetime.timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError('milliseconds are outside the datetime range') from exc


def _flat(prefix, value, output):
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = '{}.{}'.format(prefix, key) if prefix else str(key)
            _flat(name, child, output)
    elif isinstance(value, (list, tuple)):
        output[prefix] = json.dumps(value, sort_keys=True,
                                    separators=(',', ':'))
    else:
        output[prefix] = value


def iter_quote_rows(payload):
    '''Yield one flattened row per symbol from ``get_quote(s)`` response JSON.

    Nested fields retain their section name, for example
    ``quote.lastPrice`` and ``reference.description``. Unknown sections and
    fields are preserved rather than discarded.
    '''
    if not isinstance(payload, Mapping):
        raise ValueError('quote payload must be an object keyed by symbol')
    for response_symbol, quote in payload.items():
        if not isinstance(quote, Mapping):
            raise ValueError('each quote must be an object')
        row = {'symbol': str(quote.get('symbol') or response_symbol)}
        for key, value in quote.items():
            if key == 'symbol':
                continue
            _flat(str(key), value, row)
        yield row


def iter_candle_rows(payload):
    '''Yield normalized candle dictionaries from price-history response JSON.'''
    if not isinstance(payload, Mapping):
        raise ValueError('price-history payload must be an object')
    candles = payload.get('candles') or ()
    if not isinstance(candles, (list, tuple)):
        raise ValueError('candles must be an array')
    symbol = payload.get('symbol')
    for candle in candles:
        if not isinstance(candle, Mapping):
            raise ValueError('each candle must be an object')
        if 'datetime' not in candle:
            raise ValueError('each candle must contain datetime')
        row = dict(candle)
        if symbol is not None and row.get('symbol') in (None, ''):
            row['symbol'] = symbol
        row['datetime_utc'] = millis_to_datetime(candle['datetime'])
        yield row


def _number(candle, name):
    if name not in candle or isinstance(candle[name], bool):
        raise ValueError('each candle must contain numeric {}'.format(name))
    try:
        value = Decimal(str(candle[name]))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            'each candle must contain numeric {}'.format(name)) from exc
    if not value.is_finite():
        raise ValueError('each candle must contain finite {}'.format(name))
    return value


def aggregate_candles(candles, *, source_minutes, target_minutes):
    '''Aggregate exact consecutive source candles into larger OHLCV candles.

    ``target_minutes`` must be an integer multiple of ``source_minutes``.
    Groups begin at the first candle after a gap, so regular-session
    thirty-minute bars naturally form 09:30+10:00, 10:30+11:00, and so on.
    Incomplete groups are omitted. A duplicate symbol/timestamp replaces the
    earlier value before aggregation.
    '''
    for name, value in (('source_minutes', source_minutes),
                        ('target_minutes', target_minutes)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError('{} must be a positive integer'.format(name))
    if target_minutes % source_minutes:
        raise ValueError('target_minutes must be a multiple of source_minutes')
    count = target_minutes // source_minutes
    if count < 2:
        raise ValueError('target_minutes must exceed source_minutes')

    by_symbol = {}
    for candle in candles:
        if not isinstance(candle, Mapping):
            raise ValueError('each candle must be an object')
        if 'datetime' not in candle:
            raise ValueError('each candle must contain datetime')
        timestamp = _number(candle, 'datetime')
        if timestamp != timestamp.to_integral_value():
            raise ValueError('candle datetime must be whole milliseconds')
        symbol = str(candle.get('symbol') or '')
        # Validate before the duplicate can hide an invalid earlier record.
        for field in ('open', 'high', 'low', 'close', 'volume'):
            _number(candle, field)
        by_symbol.setdefault(symbol, {})[int(timestamp)] = dict(candle)

    expected_step = source_minutes * 60 * 1000
    output = []
    for symbol in sorted(by_symbol):
        pending = []
        previous = None
        for timestamp, candle in sorted(by_symbol[symbol].items()):
            if previous is not None and timestamp - previous != expected_step:
                pending = []
            pending.append(candle)
            previous = timestamp
            if len(pending) != count:
                continue
            first, last = pending[0], pending[-1]
            combined = {
                'datetime': first['datetime'],
                'open': _number(first, 'open'),
                'high': max(_number(item, 'high') for item in pending),
                'low': min(_number(item, 'low') for item in pending),
                'close': _number(last, 'close'),
                'volume': sum((_number(item, 'volume') for item in pending),
                              Decimal('0')),
                'source_candles': count,
            }
            if symbol:
                combined['symbol'] = symbol
            output.append(combined)
            pending = []
    return tuple(sorted(output, key=lambda item: (
        str(item.get('symbol') or ''), int(item['datetime']))))
