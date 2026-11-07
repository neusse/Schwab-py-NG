"""Subscribe to every supported feed family on one streaming connection.

Schwab permits one streaming session per user, not one feed per session. A
single StreamClient can carry many services and symbols at the same time. This
example registers all handlers first, then subscribes sequentially on that one
connection.

Set OPTION_SYMBOL and FUTURES_OPTION_SYMBOL to current contract symbols to
enable the option-dependent examples. Contract symbols expire, so hard-coding
sample values here would make an otherwise working example silently go stale.
"""

import asyncio
import os

import schwab
from schwab.streaming import StreamClient

API_KEY = 'XXXXXX'
APP_SECRET = 'XXXXXX'
TOKEN_PATH = './token.json'

EQUITIES = ['AAPL', 'MSFT']
NYSE_EQUITIES = ['IBM']
NASDAQ_EQUITIES = ['MSFT']
FUTURES = ['/ES']
FOREX = ['EUR/USD']

# Get a current option symbol from Client.get_option_chain(). Set these in the
# environment instead of committing an expiring contract to source control.
OPTION_SYMBOL = os.environ.get('SCHWAB_OPTION_SYMBOL')
FUTURES_OPTION_SYMBOL = os.environ.get('SCHWAB_FUTURES_OPTION_SYMBOL')

# A screener is a server-maintained ranking, such as "the ten most actively
# traded Nasdaq stocks in the current five-minute bucket." Its key is
# PREFIX_SORT-FIELD_FREQUENCY, not a ticker symbol. Each update is a complete
# ranked snapshot rather than one stock changing position.
EQUITY_SCREENERS = ['NASDAQ_VOLUME_5']
OPTION_SCREENERS = ['OPTION_CALL_VOLUME_5']


def content(message):
    """Return the service's list of relabeled content items."""
    return message.get('content', ())


def store_record(record_type, service, record):
    """THIS IS THE HOOK FOR SAVING STREAM DATA.

    Every handler below calls this function with the complete relabeled item,
    before printing a smaller human-friendly summary. Replace ``pass`` with
    your own storage handoff. For example:

        storage_queue.put_nowait((record_type, service, record.copy()))

    A separate worker can read that queue and write PostgreSQL, SQLite, Redis,
    Parquet, a message broker, or your own in-memory model. Do not perform a
    slow database or network write directly here: handlers share the stream's
    reader, so blocking this function delays every subscribed feed.

    ``record_type`` says which table or collection it naturally belongs in.
    ``service`` distinguishes feeds such as equity and futures quotes.
    ``record`` is the full item; store it rather than the print summary if you
    may need fields later.
    """
    pass


def show_quote(message):
    """Use level-one feeds for current market state, not every trade."""
    for quote in content(message):
        # STORAGE HOOK: save the complete quote update here. Level-one updates
        # can contain only fields that changed, so a database consumer may
        # merge this item into the last known state for quote['key'].
        store_record('quote', message['service'], quote)

        # Printing is only a demo. The saved `quote` above contains many more
        # fields than this short display.
        print(message['service'], quote.get('key'), {
            'bid': quote.get('BID_PRICE'),
            'ask': quote.get('ASK_PRICE'),
            'last': quote.get('LAST_PRICE'),
        })


def show_chart_bar(message):
    """Use chart feeds for minute OHLCV bars."""
    for bar in content(message):
        # STORAGE HOOK: a natural candle-table key is service + symbol + bar
        # timestamp. Store the full bar so later analysis retains OHLCV.
        store_record('minute_bar', message['service'], bar)

        print(message['service'], bar.get('key'), {
            'open': bar.get('OPEN_PRICE'),
            'high': bar.get('HIGH_PRICE'),
            'low': bar.get('LOW_PRICE'),
            'close': bar.get('CLOSE_PRICE'),
            'volume': bar.get('VOLUME'),
        })


def show_trade(message):
    """Use time-and-sales feeds for each individual market trade."""
    for trade in content(message):
        # STORAGE HOOK: append this individual print to a trades table or
        # queue. Unlike level one, this is an event, not current quote state.
        store_record('trade', message['service'], trade)

        print(message['service'], trade.get('key'), {
            'time': trade.get('TRADE_TIME'),
            'price': trade.get('LAST_PRICE'),
            'size': trade.get('LAST_SIZE'),
            'sequence': trade.get('LAST_SEQUENCE'),
        })


def show_book(message):
    """Use book feeds for market-depth price levels."""
    for book in content(message):
        # STORAGE HOOK: save the whole book item, including every bid/ask level
        # and its per-exchange breakdown. The print below keeps only the best
        # prices and counts, which is not enough to reconstruct market depth.
        store_record('order_book', message['service'], book)

        bids = book.get('BIDS') or []
        asks = book.get('ASKS') or []
        best_bid = bids[0].get('BID_PRICE') if bids else None
        best_ask = asks[0].get('ASK_PRICE') if asks else None
        print(message['service'], book.get('key'), {
            'best_bid': best_bid,
            'best_ask': best_ask,
            'bid_levels': len(bids),
            'ask_levels': len(asks),
        })


def show_screener(message):
    """Use screeners for complete server-ranked market snapshots.

    A screener is not a quote subscription. ``NASDAQ_VOLUME_5`` asks Schwab
    for a ranked Nasdaq volume list using a five-minute bucket. ``ITEMS`` is
    the complete current ranking; a symbol missing from the next push simply
    fell out of that snapshot.
    """
    for snapshot in content(message):
        ranked = snapshot.get('ITEMS') or []

        # STORAGE HOOK: store one snapshot with its TIMESTAMP, SORT_FIELD,
        # FREQUENCY, key, and complete ITEMS list. Saving only the printed
        # symbols throws away prices, changes, volume, rank inputs, and time.
        store_record('screener_snapshot', message['service'], snapshot)

        print(message['service'], snapshot.get('key'),
              [item.get('symbol') or item.get('SYMBOL') for item in ranked])


def show_news(message):
    """Use headline feeds for symbol-related news notifications."""
    for story in content(message):
        # STORAGE HOOK: store the whole story notification. A headline may be
        # delivered more than once or under several subscribed symbols, so a
        # storage worker can deduplicate using the identifiers and timestamp.
        store_record('news_headline', message['service'], story)

        print(message['service'], story.get('key'), {
            'headline': story.get('HEADLINE'),
            'source': story.get('SOURCE'),
            'language': story.get('LANGUAGE'),
        })


def show_account_activity(message):
    """Use account activity for order, fill, cancel, and change events."""
    for event in content(message):
        # STORAGE HOOK: persist the complete event before interpreting it.
        # MESSAGE_DATA can be JSON text or a plain-text Schwab notice, and the
        # full original is valuable when an unfamiliar event type appears.
        store_record('account_activity', message['service'], event)

        print(message['service'], event.get('MESSAGE_TYPE'),
              event.get('MESSAGE_DATA'))


def show_stream_error(service, exception, message):
    # A handler error or an absorbed protocol problem must not look like a
    # quiet market. In production, send this to monitoring instead of print.
    print('stream error on {!r}: {!r}'.format(service, exception))


def register_handlers(stream):
    """Register handlers before subscribing so the first push is not lost."""
    stream.add_level_one_equity_handler(show_quote)
    stream.add_level_one_option_handler(show_quote)
    stream.add_level_one_futures_handler(show_quote)
    stream.add_level_one_futures_options_handler(show_quote)
    stream.add_level_one_forex_handler(show_quote)

    stream.add_chart_equity_handler(show_chart_bar)
    stream.add_chart_futures_handler(show_chart_bar)

    stream.add_timesale_equity_handler(show_trade)
    stream.add_timesale_options_handler(show_trade)
    stream.add_timesale_futures_handler(show_trade)

    stream.add_nyse_book_handler(show_book)
    stream.add_nasdaq_book_handler(show_book)
    stream.add_options_book_handler(show_book)

    stream.add_screener_equity_handler(show_screener)
    stream.add_screener_option_handler(show_screener)
    stream.add_news_headline_handler(show_news)
    stream.add_account_activity_handler(show_account_activity)
    stream.add_error_handler(show_stream_error)


async def subscribe(stream):
    """Subscribe to many independent services on the same connection."""
    # Level one is current quote state: best bid/ask, last, sizes, and related
    # fields. It is the usual feed for a live quote display or current model.
    await stream.level_one_equity_subs(EQUITIES)
    await stream.level_one_futures_subs(FUTURES)
    await stream.level_one_forex_subs(FOREX)

    # Charts are minute OHLCV bars, useful for indicators and candle storage.
    await stream.chart_equity_subs(EQUITIES)
    await stream.chart_futures_subs(FUTURES)

    # Time and sales is the event-by-event trade tape, useful when minute bars
    # or the latest level-one trade are not detailed enough.
    await stream.timesale_equity_subs(EQUITIES)
    await stream.timesale_futures_subs(FUTURES)

    # Books are nested market depth, useful for liquidity and imbalance work.
    await stream.nyse_book_subs(NYSE_EQUITIES)
    await stream.nasdaq_book_subs(NASDAQ_EQUITIES)

    # Screener keys are criteria, not ticker symbols, and each screener service
    # accepts at most ten keys.
    await stream.screener_equity_subs(EQUITY_SCREENERS)
    await stream.screener_option_subs(OPTION_SCREENERS)

    # News emits headline notifications for the subscribed symbols. Account
    # activity emits events for your own orders and fills, not market data.
    await stream.news_headline_subs(EQUITIES)
    await stream.account_activity_sub()

    if OPTION_SYMBOL:
        option_symbols = [OPTION_SYMBOL]
        await stream.level_one_option_subs(option_symbols)
        await stream.timesale_options_subs(option_symbols)
        await stream.options_book_subs(option_symbols)
    else:
        print('Set SCHWAB_OPTION_SYMBOL to enable the three option feeds')

    if FUTURES_OPTION_SYMBOL:
        await stream.level_one_futures_options_subs(
                [FUTURES_OPTION_SYMBOL])
    else:
        print('Set SCHWAB_FUTURES_OPTION_SYMBOL to enable futures options')


async def main():
    client = schwab.auth.client_from_token_file(
            TOKEN_PATH, api_key=API_KEY, app_secret=APP_SECRET)

    # This is the only StreamClient. Every subscription below shares it.
    async with StreamClient(client) as stream:
        register_handlers(stream)
        await stream.login()
        await subscribe(stream)

        while True:
            # One read routes the next message to the handler for its service.
            await stream.handle_message()


if __name__ == '__main__':
    asyncio.run(main())
