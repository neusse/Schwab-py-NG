'''Opt-in aggregation and off-reader consumption for streaming messages.

These classes are independent of :class:`schwab.streaming.StreamClient`.
Register ``handle_message`` or ``async_handle_message`` as a normal stream
handler; raw dispatch and subscriptions remain unchanged.
'''

import asyncio
import inspect
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


QUOTE_SERVICES = frozenset((
    'LEVELONE_EQUITIES',
    'LEVELONE_OPTIONS',
    'LEVELONE_FUTURES',
    'LEVELONE_FUTURES_OPTIONS',
    'LEVELONE_FOREX',
))

CHART_SERVICES = frozenset(('CHART_EQUITY', 'CHART_FUTURES'))


def _positive_limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('{} must be a positive integer'.format(name))
    return value


def _parts(message, allowed):
    if not isinstance(message, Mapping):
        raise ValueError('stream message must be an object')
    service = str(message.get('service') or '')
    if service not in allowed:
        raise ValueError('unsupported aggregation service: {!r}'.format(service))
    content = message.get('content') or ()
    if not isinstance(content, (list, tuple)):
        raise ValueError('stream content must be an array')
    return service, content


@dataclass(frozen=True)
class QuoteStateSnapshot:
    '''Current merged fields for one quote symbol.'''

    service: str
    symbol: str
    fields: dict
    sequence: int
    stale: bool


@dataclass(frozen=True)
class ChartCandleSnapshot:
    '''One merged chart candle and its connection-health state.'''

    service: str
    symbol: str
    timestamp: int
    fields: dict
    sequence: int
    stale: bool


class QuoteStateAggregator:
    '''Merge sparse level-one updates into bounded current quote state.

    The least-recently-updated symbol is evicted when ``max_symbols`` is
    exceeded. Duplicate updates are idempotent at the field level; unknown
    fields are retained. Call :meth:`mark_disconnected` when a stream drops so
    returned snapshots visibly become stale.
    '''

    def __init__(self, max_symbols=1000):
        self.max_symbols = _positive_limit(max_symbols, 'max_symbols')
        self._states = OrderedDict()
        self._sequence = 0
        self._connected = False

    def handle_message(self, message):
        '''Synchronously merge one level-one handler message.'''
        service, content = _parts(message, QUOTE_SERVICES)
        self._connected = True
        updated = []
        for raw in content:
            if not isinstance(raw, Mapping):
                raise ValueError('each stream content item must be an object')
            symbol = str(raw.get('key') or raw.get('symbol') or '')
            if not symbol:
                raise ValueError('quote content has no key or symbol')
            key = (service, symbol)
            fields, _ = self._states.pop(key, ({}, 0))
            merged = dict(fields)
            merged.update(raw)
            self._sequence += 1
            self._states[key] = (merged, self._sequence)
            while len(self._states) > self.max_symbols:
                self._states.popitem(last=False)
            updated.append(self.get(service, symbol))
        return tuple(updated)

    async def async_handle_message(self, message):
        '''Asynchronous-handler form of :meth:`handle_message`.'''
        return self.handle_message(message)

    def get(self, service, symbol):
        '''Return one snapshot, or ``None`` when it is not retained.'''
        value = self._states.get((service, symbol))
        if value is None:
            return None
        fields, sequence = value
        return QuoteStateSnapshot(
            service, symbol, dict(fields), sequence,
            not self._connected)

    def snapshots(self):
        '''Return all retained snapshots in service/symbol order.'''
        return tuple(self.get(*key) for key in sorted(self._states))

    def mark_connected(self, *, clear=False):
        '''Mark state healthy after login, optionally clearing old values.'''
        if clear:
            self.reset()
        self._connected = True

    def mark_disconnected(self):
        '''Mark every retained snapshot stale without discarding it.'''
        self._connected = False

    def reset(self):
        '''Discard every retained symbol and reset update ordering.'''
        self._states.clear()
        self._sequence = 0


class ChartCandleAggregator:
    '''Keep bounded minute-chart candles by service, symbol, and timestamp.

    A repeat of the same timestamp merges fields and replaces conflicting
    values. Out-of-order candles are accepted. Once a symbol exceeds
    ``max_candles_per_symbol``, its oldest timestamp is evicted, so an older
    late arrival may be accepted and immediately evicted.
    '''

    TIMESTAMP_FIELDS = ('CHART_TIME_MILLIS', 'datetime', 'timestamp')

    def __init__(self, max_candles_per_symbol=500):
        self.max_candles_per_symbol = _positive_limit(
            max_candles_per_symbol, 'max_candles_per_symbol')
        self._states = {}
        self._sequence = 0
        self._connected = False

    @classmethod
    def _timestamp(cls, raw):
        for name in cls.TIMESTAMP_FIELDS:
            value = raw.get(name)
            if value is not None:
                if isinstance(value, bool):
                    break
                try:
                    number = Decimal(str(value))
                    if (not number.is_finite()
                            or number != number.to_integral_value()):
                        break
                    return int(number)
                except (InvalidOperation, TypeError, ValueError, OverflowError):
                    break
        raise ValueError('chart content has no integer timestamp')

    def handle_message(self, message):
        '''Synchronously merge one chart handler message.'''
        service, content = _parts(message, CHART_SERVICES)
        self._connected = True
        updated = []
        for raw in content:
            if not isinstance(raw, Mapping):
                raise ValueError('each stream content item must be an object')
            symbol = str(raw.get('key') or raw.get('symbol') or '')
            if not symbol:
                raise ValueError('chart content has no key or symbol')
            timestamp = self._timestamp(raw)
            key = (service, symbol)
            candles = self._states.setdefault(key, {})
            fields, _ = candles.get(timestamp, ({}, 0))
            merged = dict(fields)
            merged.update(raw)
            self._sequence += 1
            candles[timestamp] = (merged, self._sequence)
            while len(candles) > self.max_candles_per_symbol:
                del candles[min(candles)]
            snapshot = self.get(service, symbol, timestamp)
            if snapshot is not None:
                updated.append(snapshot)
        return tuple(updated)

    async def async_handle_message(self, message):
        '''Asynchronous-handler form of :meth:`handle_message`.'''
        return self.handle_message(message)

    def get(self, service, symbol, timestamp):
        '''Return one candle snapshot, or ``None`` when it is not retained.'''
        value = self._states.get((service, symbol), {}).get(timestamp)
        if value is None:
            return None
        fields, sequence = value
        return ChartCandleSnapshot(
            service, symbol, timestamp, dict(fields),
            sequence, not self._connected)

    def snapshots(self, service=None, symbol=None):
        '''Return retained candles sorted by service, symbol, and timestamp.'''
        output = []
        for key in sorted(self._states):
            if service is not None and key[0] != service:
                continue
            if symbol is not None and key[1] != symbol:
                continue
            for timestamp in sorted(self._states[key]):
                output.append(self.get(key[0], key[1], timestamp))
        return tuple(output)

    def mark_connected(self, *, clear=False):
        '''Mark state healthy after login, optionally clearing old candles.'''
        if clear:
            self.reset()
        self._connected = True

    def mark_disconnected(self):
        '''Mark retained candles stale without discarding them.'''
        self._connected = False

    def reset(self):
        '''Discard all retained candles and reset update ordering.'''
        self._states.clear()
        self._sequence = 0


_STOP = object()


class AsyncMessageConsumer:
    '''Move storage or user work off the shared stream reader.

    ``sink`` receives one message at a time and may be synchronous or
    asynchronous. ``overflow`` is ``'block'``, ``'drop_oldest'``, or
    ``'drop_newest'``. Use :meth:`handler` for a non-blocking stream handler or
    :meth:`async_handler` when blocking backpressure is desired. Run
    :meth:`run` in its own task and finish with :meth:`close`.
    '''

    OVERFLOW_POLICIES = frozenset(('block', 'drop_oldest', 'drop_newest'))

    def __init__(self, sink, *, max_queue_size=1000, overflow='drop_oldest'):
        if not callable(sink):
            raise TypeError('sink must be callable')
        if overflow not in self.OVERFLOW_POLICIES:
            raise ValueError('unknown overflow policy: {!r}'.format(overflow))
        self.sink = sink
        self.max_queue_size = _positive_limit(max_queue_size,
                                              'max_queue_size')
        self.overflow = overflow
        self.queue = asyncio.Queue(self.max_queue_size)
        self.dropped = 0
        self.processed = 0
        self._closed = False

    def handler(self, message):
        '''Queue one message without awaiting; return whether it was retained.'''
        if self._closed:
            raise RuntimeError('consumer is closed')
        if not self.queue.full():
            self.queue.put_nowait(message)
            return True
        if self.overflow == 'drop_newest':
            self.dropped += 1
            return False
        if self.overflow == 'drop_oldest':
            self.queue.get_nowait()
            self.queue.task_done()
            self.dropped += 1
            self.queue.put_nowait(message)
            return True
        raise asyncio.QueueFull(
            'blocking overflow requires await consumer.async_handler(message)')

    async def async_handler(self, message):
        '''Queue one message, awaiting room only under ``'block'`` policy.'''
        if self._closed:
            raise RuntimeError('consumer is closed')
        if self.overflow == 'block':
            await self.queue.put(message)
            return True
        return self.handler(message)

    async def run(self):
        '''Consume until :meth:`close` places its sentinel behind queued work.'''
        while True:
            message = await self.queue.get()
            try:
                if message is _STOP:
                    return self.processed
                result = self.sink(message)
                if inspect.isawaitable(result):
                    await result
                self.processed += 1
            finally:
                self.queue.task_done()

    async def close(self):
        '''Reject new messages and stop :meth:`run` after queued work.'''
        if self._closed:
            return
        self._closed = True
        await self.queue.put(_STOP)
