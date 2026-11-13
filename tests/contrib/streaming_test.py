import asyncio
import unittest

from schwab.contrib.streaming import (
    AsyncMessageConsumer, ChartCandleAggregator, QuoteStateAggregator)

from tests.utils import no_duplicates


class StreamingAggregatorTest(unittest.IsolatedAsyncioTestCase):

    @no_duplicates
    async def test_quote_partial_duplicate_unknown_and_stale_state(self):
        state = QuoteStateAggregator(max_symbols=2)
        first = {'service': 'LEVELONE_EQUITIES', 'content': [
            {'key': 'AAPL', 'BID_PRICE': 100, 'UNKNOWN': 'kept'}]}
        state.handle_message(first)
        state.handle_message({'service': 'LEVELONE_EQUITIES', 'content': [
            {'key': 'AAPL', 'ASK_PRICE': 101}]})
        await state.async_handle_message({
            'service': 'LEVELONE_EQUITIES', 'content': [
                {'key': 'AAPL', 'ASK_PRICE': 101}]})
        snapshot = state.get('LEVELONE_EQUITIES', 'AAPL')
        self.assertEqual(100, snapshot.fields['BID_PRICE'])
        self.assertEqual(101, snapshot.fields['ASK_PRICE'])
        self.assertEqual('kept', snapshot.fields['UNKNOWN'])
        self.assertFalse(snapshot.stale)
        state.mark_disconnected()
        self.assertTrue(state.get('LEVELONE_EQUITIES', 'AAPL').stale)

    @no_duplicates
    async def test_quote_memory_is_bounded_and_reset_is_explicit(self):
        state = QuoteStateAggregator(max_symbols=2)
        for symbol in ('A', 'B', 'C'):
            state.handle_message({'service': 'LEVELONE_EQUITIES',
                                  'content': [{'key': symbol}]})
        self.assertIsNone(state.get('LEVELONE_EQUITIES', 'A'))
        self.assertEqual(['B', 'C'], [s.symbol for s in state.snapshots()])
        state.reset()
        self.assertEqual((), state.snapshots())

    @no_duplicates
    async def test_chart_replaces_timestamp_accepts_out_of_order_and_bounds(self):
        state = ChartCandleAggregator(max_candles_per_symbol=2)
        for timestamp, close in ((2000, 2), (1000, 1), (2000, 3), (3000, 4)):
            state.handle_message({'service': 'CHART_EQUITY', 'content': [{
                'key': 'AAPL', 'CHART_TIME_MILLIS': timestamp,
                'CLOSE_PRICE': close,
            }]})
        snapshots = state.snapshots('CHART_EQUITY', 'AAPL')
        self.assertEqual([2000, 3000], [s.timestamp for s in snapshots])
        self.assertEqual(3, snapshots[0].fields['CLOSE_PRICE'])
        state.mark_disconnected()
        self.assertTrue(state.snapshots()[0].stale)

    @no_duplicates
    async def test_timesale_services_are_not_aggregated(self):
        with self.assertRaises(ValueError):
            QuoteStateAggregator().handle_message({
                'service': 'TIMESALE_EQUITY', 'content': []})
        with self.assertRaises(ValueError):
            ChartCandleAggregator().handle_message({
                'service': 'TIMESALE_FUTURES', 'content': []})
        with self.assertRaises(ValueError):
            ChartCandleAggregator().handle_message({
                'service': 'CHART_EQUITY', 'content': [{
                    'key': 'AAPL', 'CHART_TIME_MILLIS': 1.5}]})

    @no_duplicates
    async def test_async_consumer_moves_sync_and_async_sinks_off_handler(self):
        seen = []

        async def sink(message):
            await asyncio.sleep(0)
            seen.append(message)

        consumer = AsyncMessageConsumer(
            sink, max_queue_size=2, overflow='drop_oldest')
        self.assertTrue(consumer.handler(1))
        self.assertTrue(consumer.handler(2))
        self.assertTrue(consumer.handler(3))
        self.assertEqual(1, consumer.dropped)
        task = asyncio.create_task(consumer.run())
        await consumer.close()
        self.assertEqual(2, await task)
        self.assertEqual([2, 3], seen)

    @no_duplicates
    async def test_consumer_overflow_policies_are_explicit(self):
        newest = AsyncMessageConsumer(
            lambda message: None, max_queue_size=1,
            overflow='drop_newest')
        newest.handler('first')
        self.assertFalse(newest.handler('second'))
        self.assertEqual(1, newest.dropped)

        blocking = AsyncMessageConsumer(
            lambda message: None, max_queue_size=1, overflow='block')
        blocking.handler('first')
        with self.assertRaises(asyncio.QueueFull):
            blocking.handler('second')

    @no_duplicates
    async def test_aggregator_validation_reconnect_and_chart_async_handler(self):
        for factory in (QuoteStateAggregator, ChartCandleAggregator):
            for limit in (True, 0, 1.5):
                with self.assertRaises(ValueError):
                    factory(limit)
        quote = QuoteStateAggregator()
        for message in (None,
                        {'service': 'LEVELONE_EQUITIES',
                         'content': {'bad': 1}},
                        {'service': 'LEVELONE_EQUITIES', 'content': [None]},
                        {'service': 'LEVELONE_EQUITIES', 'content': [{}]}):
            with self.assertRaises(ValueError):
                quote.handle_message(message)
        quote.handle_message({'service': 'LEVELONE_EQUITIES',
                              'content': [{'key': 'AAPL'}]})
        quote.mark_disconnected()
        quote.mark_connected()
        self.assertFalse(quote.get('LEVELONE_EQUITIES', 'AAPL').stale)
        quote.mark_connected(clear=True)
        self.assertEqual((), quote.snapshots())

        chart = ChartCandleAggregator()
        result = await chart.async_handle_message({
            'service': 'CHART_EQUITY', 'content': [{
                'symbol': 'AAPL', 'timestamp': '1000'}]})
        self.assertEqual(1000, result[0].timestamp)
        self.assertIsNone(chart.get('CHART_EQUITY', 'MSFT', 1000))
        chart.handle_message({'service': 'CHART_FUTURES', 'content': [{
            'key': '/ES', 'datetime': 2000}]})
        self.assertEqual(1, len(chart.snapshots(service='CHART_EQUITY')))
        self.assertEqual(1, len(chart.snapshots(symbol='/ES')))
        chart.mark_disconnected()
        self.assertTrue(chart.snapshots()[0].stale)
        chart.mark_connected()
        chart.mark_connected(clear=True)
        self.assertEqual((), chart.snapshots())
        for content in (None, {}, {'key': 'AAPL', 'timestamp': True},
                        {'key': 'AAPL', 'timestamp': 'bad'},
                        {'key': 'AAPL', 'timestamp': 'Infinity'},
                        {'key': 'AAPL'}):
            with self.assertRaises(ValueError):
                chart.handle_message({'service': 'CHART_EQUITY',
                                      'content': [content]})

    @no_duplicates
    async def test_consumer_blocking_close_and_closed_validation(self):
        seen = []
        consumer = AsyncMessageConsumer(
            seen.append, max_queue_size=1, overflow='block')
        with self.assertRaises(ValueError):
            AsyncMessageConsumer(seen.append, overflow='unknown')
        with self.assertRaises(TypeError):
            AsyncMessageConsumer(None)
        await consumer.async_handler('first')
        task = asyncio.create_task(consumer.run())
        await asyncio.sleep(0)
        await consumer.async_handler('second')
        await consumer.close()
        await consumer.close()
        self.assertEqual(2, await task)
        self.assertEqual(['first', 'second'], seen)
        with self.assertRaises(RuntimeError):
            consumer.handler('late')
        with self.assertRaises(RuntimeError):
            await consumer.async_handler('late')

        newest = AsyncMessageConsumer(
            seen.append, max_queue_size=1, overflow='drop_newest')
        self.assertTrue(await newest.async_handler('kept'))
