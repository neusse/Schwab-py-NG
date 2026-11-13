.. _ng_utilities:

=====================
Application Utilities
=====================

NG keeps REST clients deliberately raw: requests return ``httpx2`` responses
and applications decide what to retain. The helpers here sit after that seam.
They normalize already-decoded payloads, preserve hierarchy, and move slow
stream processing off the websocket reader without taking ownership of a
client, token, database, or dataframe library.

These utilities adapt the reusable ideas from the maintainer's
`schwab-py-extra <https://github.com/neusse/schwab-py-extra>`__ experiments.
They use only NG's existing runtime dependencies. Pandas, Rich, yfinance,
Alpaca, matplotlib, GUI code, and strategy logic remain application concerns.


Command-line workflows
======================

The installed ``schwab-ng`` command makes the common read-only workflows
available without writing a Python script. Credentials come from
``SCHWAB_TOKEN_PATH``, ``SCHWAB_API_KEY``, and ``SCHWAB_APP_SECRET``; secrets
are not accepted as command-line arguments.

.. code-block:: shell

  schwab-ng doctor
  schwab-fetch-new-token
  schwab-ng orders --today
  schwab-ng orders --today --account 570 --csv orders.csv
  schwab-ng positions --account 570
  schwab-ng transactions --days 7 --symbol AAPL --json
  schwab-ng candles AAPL --every hour --days 5 --csv aapl-hourly.csv

Orders, positions, and transactions query each linked account independently so
every result can be labeled with the web interface convention, such as
``...570``. ``--account`` accepts those last three characters. If two linked
accounts share a suffix, the command refuses the ambiguous selection and asks
for the full account number. Full numbers and account hashes are never written
to tables, CSV, or JSON.

Tables are the default. ``--csv PATH`` writes a file and ``--json`` produces
machine-readable output. Order CSV and JSON retain the related order, leg,
activity, and execution rows; the terminal table shows one useful summary per
order and reports top-level orders separately from related export rows.
Date-aware commands accept ``--today``, ``--days``, or inclusive
``--from``/``--to`` dates. The standalone
``schwab-ng-orders``, ``schwab-ng-positions``, ``schwab-ng-transactions``, and
``schwab-ng-candles`` commands are aliases for the corresponding subcommands.
Candle requests default to the last five days so an interactive command does
not unexpectedly print decades of daily or weekly history.

When the seven-day refresh token has fully expired, ``schwab-fetch-new-token``
uses :func:`~schwab.auth.easy_client` to start a complete browser OAuth
authorization and replaces the file at ``SCHWAB_TOKEN_PATH``. It also exists as
``schwab-ng fetch-new-token``. This is never an access-token or refresh-token
refresh. ``easy_client`` normally opens the browser, captures the callback, and
exchanges the authorization code automatically; its existing copy/paste
fallback is retained if automatic capture fails.

Before asking, the command reports whether the token file is absent or
unreadable, the next access-token refresh deadline when ``expires_at`` is
available, and the estimated refresh-token full expiry derived from its
creation timestamp and Schwab's seven-day term. It explicitly says whether
full OAuth is already required. These are diagnostics only: the command always
does full OAuth and never chooses refresh. The command additionally requires
``SCHWAB_CALLBACK_URL``. Existing tokens require confirmation unless ``--yes``
is supplied, and remain untouched when authorization is canceled or fails. A
successful ``easy_client`` authorization is written to a staging location,
then NG's atomic token writer replaces the real file. API keys and secrets
cannot be supplied on the command line.


Trader API visibility is not web Order Status parity
----------------------------------------------------

The commands report only what Schwab's public Trader API returns. They do not
scrape schwab.com and a zero-result response is described as exactly that,
rather than as proof that no order exists.

This difference was observed directly on 2026-11-13: Schwab web Order Status
showed a filled, dollar-denominated SGOV market order in account ``...570`` at
1:22 PM ET. Full-day calls to both the all-linked and per-account order
endpoints returned zero orders, and the account transaction endpoint returned
zero matching transactions. Dollar/fractional order handling is a plausible
explanation, but Schwab has not confirmed it and this observation does not
establish a universal rule. Reconcile important results with Schwab's own
interface.


Safe installation and token diagnostics
=======================================

After installing NG, run:

.. code-block:: shell

  schwab-ng-doctor --token-path /path/to/token.json

The doctor detects the corrupting case where both ``schwab-py`` and
``schwab-py-ng`` are installed; reports Python, platform, timezone, import
ownership, and every required runtime package version; checks token creation,
refresh age, access expiry, writability, and owner-only permissions on POSIX;
and can compare installed versions with PyPI. It never prints token values,
credentials, full account identifiers, or response bodies.

When all three environment values are present, the doctor also checks a quote
and linked-account discovery by default. Building the client can refresh and
rewrite the token. Use ``--offline`` to suppress live calls, or ``--connect``
to require them and fail when credentials are incomplete:

.. code-block:: shell

  schwab-ng doctor --offline
  schwab-ng doctor --connect --check-updates

The arguments may instead come from ``SCHWAB_TOKEN_PATH``,
``SCHWAB_API_KEY``, and ``SCHWAB_APP_SECRET`` (lower-case spellings are also
accepted). Credentials are intentionally not accepted as command-line options,
where process listings and shell history could expose them. The quote response
is checked and discarded. Successful account discovery displays only the last
three characters. A failure names only its exception class and HTTP status;
sensitive exception text is suppressed. ``--json`` is suitable for automation.

.. autoclass:: schwab.doctor.DoctorCheck
.. autofunction:: schwab.doctor.run_checks
.. autofunction:: schwab.doctor.configure_parser
.. autofunction:: schwab.doctor.run_cli
.. autofunction:: schwab.doctor.main

.. autofunction:: schwab.cli.build_parser
.. autofunction:: schwab.cli.main
.. autofunction:: schwab.cli.run_orders
.. autofunction:: schwab.cli.run_positions
.. autofunction:: schwab.cli.run_transactions
.. autofunction:: schwab.cli.run_candles
.. autofunction:: schwab.cli.run_fetch_new_token
.. autofunction:: schwab.cli.orders_main
.. autofunction:: schwab.cli.positions_main
.. autofunction:: schwab.cli.transactions_main
.. autofunction:: schwab.cli.candles_main
.. autofunction:: schwab.cli.fetch_new_token_main


Accounts and positions
======================

:func:`~schwab.contrib.account.account_snapshots` accepts JSON from
:meth:`~schwab.client.Client.get_account` or
:meth:`~schwab.client.Client.get_accounts`. Long and short quantities remain
separate and ``net_quantity`` is long minus short. Instruments are identified
by asset type, symbol, CUSIP, instrument id, put/call, and underlying symbol;
two contracts are not collapsed merely because their display symbols match.

.. code-block:: python

  from schwab.contrib.account import account_snapshots, iter_position_rows

  response = client.get_accounts(fields=[client.Account.Fields.POSITIONS])
  response.raise_for_status()

  snapshots = account_snapshots(response.json())
  for row in iter_position_rows(response.json()):
      print(row['account'], row['symbol'], row['net_quantity'])

Rows expose only a masked account label by default. ``AccountIdentity`` keeps
the raw join key because a program comparing two endpoint responses needs it;
treat that value as an account identifier and do not log it. Passing
``include_account_key=True`` to ``iter_position_rows`` is an explicit request
to put that private identifier into the output.

Aggregation combines equal instruments across accounts and returns positions
whose ``account_key`` is ``None`` so the lost per-account dimension cannot be
mistaken for a real account. Snapshot diffs retain additions, removals, and
changes as separate before/after values.

.. autofunction:: schwab.contrib.account.mask_account_number
.. autofunction:: schwab.contrib.account.account_suffix
.. autoclass:: schwab.contrib.account.AccountIdentity
.. autoclass:: schwab.contrib.account.PositionIdentity
.. autoclass:: schwab.contrib.account.Position
   :members:
.. autoclass:: schwab.contrib.account.AccountSnapshot
.. autoclass:: schwab.contrib.account.PositionChange
   :members:
.. autofunction:: schwab.contrib.account.account_snapshots
.. autofunction:: schwab.contrib.account.aggregate_positions
.. autofunction:: schwab.contrib.account.diff_positions
.. autofunction:: schwab.contrib.account.iter_position_rows

Runnable examples:

* `one position snapshot <https://github.com/neusse/Schwab-py-NG/blob/main/examples/accounts/positions_snapshot.py>`__
* `polling position monitor <https://github.com/neusse/Schwab-py-NG/blob/main/examples/accounts/positions_monitor.py>`__


Orders, transactions, and CSV
=============================

Schwab order and transaction payloads contain variable-length trees. Flattening
``transferItems`` into columns such as ``transfer_0_*`` makes the schema depend
on the longest transaction, while flattening an order to one row loses child
orders, legs, and executions. NG emits related row types instead:

.. code-block:: python

  from schwab.contrib.export import iter_order_rows, write_csv

  response = client.get_orders_for_all_linked_accounts()
  response.raise_for_status()
  write_csv('orders.csv', iter_order_rows(response.json()))

Order rows carry an ``order_path`` (``0``, ``0.1``, and so on), order and
parent-order ids, and a ``record_type`` of ``order``, ``order_leg``,
``order_activity``, or ``execution_leg``. Transaction and transfer-item rows
share their transaction index and id. Account numbers are masked.

``write_csv`` accepts heterogeneous rows, builds columns in first-seen order,
and uses the standard library's UTF-8 CSV writer. It materializes its input to
discover the union of fields, so use a purpose-built streaming exporter for a
dataset which cannot fit in memory.

.. autofunction:: schwab.contrib.export.iter_order_rows
.. autofunction:: schwab.contrib.export.iter_transaction_rows
.. autofunction:: schwab.contrib.export.write_csv

Runnable examples:

* `order export <https://github.com/neusse/Schwab-py-NG/blob/main/examples/accounts/export_orders.py>`__
* `transaction export <https://github.com/neusse/Schwab-py-NG/blob/main/examples/accounts/export_transactions.py>`__


Quotes and candles
==================

Quote rows retain nested section names such as ``quote.lastPrice`` and
``reference.description``. Unknown sections and fields are retained. Candle
rows add a timezone-aware UTC ``datetime_utc`` while keeping Schwab's original
millisecond timestamp.

.. code-block:: python

  from schwab.contrib.market_data import iter_candle_rows

  response = client.get_price_history_every_hour('AAPL')
  response.raise_for_status()
  rows = list(iter_candle_rows(response.json()))

  # pandas is optional and belongs to the application:
  # frame = pandas.DataFrame(rows).set_index('datetime_utc')

Custom candle aggregation requires explicit source and target sizes. Only
exact consecutive groups are combined; gaps and incomplete groups are omitted.
Groups restart after a gap, matching regular-session 09:30+10:00 behavior for
thirty-minute-to-hour conversion. A repeated symbol/timestamp replaces the
earlier source candle before aggregation.

.. autofunction:: schwab.contrib.market_data.millis_to_datetime
.. autofunction:: schwab.contrib.market_data.iter_quote_rows
.. autofunction:: schwab.contrib.market_data.iter_candle_rows
.. autofunction:: schwab.contrib.market_data.aggregate_candles

See the `candle row example
<https://github.com/neusse/Schwab-py-NG/blob/main/examples/market_data/candles_to_rows.py>`__.


Opt-in streaming aggregation
============================

The stream remains raw and stateless by default. Aggregators are ordinary
handlers an application chooses to register. Synthetic tests prove only their
mechanics; they do not prove Schwab supplies a feed. The supported services and
their live evidence remain the table in :ref:`stream`, and the inherited
``TIMESALE_*`` compatibility names remain unsupported and excluded from these
aggregators; see :ref:`time_and_sales`.

Quote state
-----------

Level-one updates carry only fields which changed. ``QuoteStateAggregator``
merges those sparse updates by service and symbol, preserves unknown fields,
and evicts the least-recently-updated symbol when its bound is exceeded.

.. code-block:: python

  from schwab.contrib.streaming import QuoteStateAggregator

  quotes = QuoteStateAggregator(max_symbols=500)
  stream.add_level_one_equity_handler(quotes.handle_message)

  # After a disconnect, retained values remain available but visibly stale.
  quotes.mark_disconnected()
  assert quotes.get('LEVELONE_EQUITIES', 'AAPL').stale

A duplicate update is idempotent at the field level. ``reset`` discards state;
``mark_connected(clear=True)`` combines reconnection and reset. Without a
reset, state survives reconnection but is stale between
``mark_disconnected`` and the first new message or ``mark_connected`` call.

Chart candles
-------------

``ChartCandleAggregator`` keeps a bounded time series per service and symbol.
An update for an existing timestamp merges partial fields and replaces
conflicting values. Out-of-order timestamps are inserted in time order. Once
the per-symbol bound is exceeded, the oldest timestamp is evicted; a very old
late arrival can therefore be accepted and immediately evicted.

Storage and backpressure
------------------------

Handlers run on the shared websocket reader. Database writes, user callbacks,
and other blocking work must be handed off. ``AsyncMessageConsumer`` provides
one bounded queue and one sink seam:

.. code-block:: python

  import asyncio
  from schwab.contrib.streaming import AsyncMessageConsumer

  consumer = AsyncMessageConsumer(
      save_message, max_queue_size=1000, overflow='drop_oldest')
  worker = asyncio.create_task(consumer.run())
  stream.add_level_one_equity_handler(consumer.handler)

  # During shutdown, after the stream has stopped producing:
  await consumer.close()
  await worker

``drop_oldest`` retains the newest message, ``drop_newest`` refuses the new
one, and ``block`` applies backpressure only through ``await
consumer.async_handler(message)``. The synchronous ``handler`` never waits;
under ``block`` it raises ``asyncio.QueueFull`` when full. ``dropped`` and
``processed`` are explicit counters. ``close`` places a sentinel behind queued
work and rejects later messages.

The `SQLite example
<https://github.com/neusse/Schwab-py-NG/blob/main/examples/streaming/store_level_one_in_sqlite.py>`__
stores JSON with indexed service, symbol, and timestamp fields instead of
hard-coding one wide schema which breaks when Schwab adds a field.

.. autoclass:: schwab.contrib.streaming.QuoteStateSnapshot
.. autoclass:: schwab.contrib.streaming.ChartCandleSnapshot
.. autoclass:: schwab.contrib.streaming.QuoteStateAggregator
   :members:
.. autoclass:: schwab.contrib.streaming.ChartCandleAggregator
   :members:
.. autoclass:: schwab.contrib.streaming.AsyncMessageConsumer
   :members:
