.. highlight:: python
.. py:module:: schwab.client


.. _client:

===========
HTTP Client
===========

A naive, unopinionated wrapper around the
`Schwab individual trader API
<https://developer.schwab.com/products/trader-api--individual>`_. This
client provides access to all endpoints of the API in as easy and direct a way
as possible.


**Do not attempt to use more than one Client object per token file, as
this will likely cause issues with the underlying OAuth2 session management**

.. code-block:: python

  import httpx2

  from schwab.auth import easy_client

  # Follow the instructions on the screen to authenticate your client.
  c = easy_client(
          api_key='APIKEY',
          app_secret='APP_SECRET',
          callback_url='https://127.0.0.1',
          token_path='/tmp/token.json')

  resp = c.get_price_history_every_day('AAPL')
  assert resp.status_code == httpx2.codes.OK
  history = resp.json()

Note that we create a new client using the ``auth`` package as described in
:ref:`auth`. Creating a client directly is possible, but not recommended.

.. autoclass:: schwab.client.Client

+++++++++++++++++++
Asyncio Support
+++++++++++++++++++

An asynchronous variant is available through a keyword to the client
constructor. This allows for higher-performance API usage, at the cost
of slightly increased application complexity.

.. code-block:: python

  import httpx2

  from schwab.auth import easy_client

  async def main():
      c = easy_client(
              api_key='APIKEY',
              app_secret='APP_SECRET',
              callback_url='https://127.0.0.1:8182',
              token_path='/tmp/token.json',
              asyncio=True)

      resp = await c.get_price_history_every_day('AAPL')
      assert resp.status_code == httpx2.codes.OK
      history = resp.json()

  if __name__ == '__main__':
      import asyncio
      asyncio.run(main())

Both clients hold an HTTP session with open connections, and both can be told
to let go of it:

.. code-block:: python

  c.close_session()          # synchronous client
  await c.close_async_session()   # asyncio client

Neither is worth calling if you create one client and keep it for the life of
the process, which is what most applications do. They matter when clients are
created repeatedly, where the connections would otherwise be released only
whenever the session happens to be garbage collected. A client cannot be used
after being closed.

.. autoclass:: schwab.client.AsyncClient
.. automethod:: schwab.client.Client.close_session
.. automethod:: schwab.client.AsyncClient.close_async_session

+++++++++++++++++++
Calling Conventions
+++++++++++++++++++

Function parameters are categorized as either required or optional.  Required
parameters are passed as positional arguments.  Optional parameters are passed
as keyword arguments.

Parameters which have special values recognized by the API are
represented by `Python enums <https://docs.python.org/3/library/enum.html>`_.
This is because the API rejects requests which pass unrecognized values, and
this enum wrapping is provided as a convenient mechanism to avoid consternation
caused by accidentally passing an unrecognized value.

By default, passing values other than the required enums will raise a
``ValueError``. If you believe the API accepts a value that isn't supported
here, you can use :meth:`set_enforce_enums
<schwab.client.Client.set_enforce_enums>` to disable this behavior at your own
risk. If you *do* find a supported value that isn't listed here, please open an
issue describing it or submit a PR adding the new functionality.

.. automethod:: schwab.client.Client.set_enforce_enums


++++++++++++++++++++++
Dates and Times
++++++++++++++++++++++

**Give datetimes a timezone.** Every parameter below which takes a
``datetime`` names a moment in time, and a ``datetime`` carrying no ``tzinfo``
does not name one -- it is a wall clock reading with no indication of whose
wall it is on.

Passing one anyway is ambiguous, and the two encodings Schwab uses resolve that
ambiguity differently. The epoch-millisecond parameters, which the price
history endpoints use, read a naive datetime as the local time of whichever
machine is running:

.. code-block:: python

  # The same source line, run in two places.
  c.get_price_history_every_minute(
          'AAPL',
          start_datetime=datetime.datetime(2026, 8, 6, 9, 30),
          end_datetime=datetime.datetime(2026, 8, 6, 16, 0))

  # on a host set to UTC:                startDate=1786008600000
  # on a host set to America/New_York:   startDate=1786023000000

Four hours apart. Nothing in the request records which was meant, so a
container and a laptop quietly disagree about what a given window contains.
The ISO-8601 parameters -- ``from_entered_datetime``, ``to_entered_datetime``
and the transaction dates -- are ambiguous in their own way, sending the wall
clock as written and labelling it UTC.

Attaching a timezone removes the question entirely, and any of these will do:

.. code-block:: python

  import datetime
  import zoneinfo

  # Explicit UTC
  datetime.datetime(2026, 8, 6, 13, 30, tzinfo=datetime.timezone.utc)

  # Market local time, which is usually what you actually mean
  datetime.datetime(2026, 8, 6, 9, 30,
                    tzinfo=zoneinfo.ZoneInfo('America/New_York'))

  # Whatever this machine is set to, but said out loud rather than assumed
  datetime.datetime(2026, 8, 6, 9, 30).astimezone()

An aware datetime produces the same request everywhere, whichever timezone it
carries. Passing a naive one emits a warning naming the parameter. Plain
``date`` objects are unaffected, having no time of day to be ambiguous about.


+++++++++++++
Return Values
+++++++++++++

All methods return a response object generated under the hood by the
`HTTPX2 <https://github.com/pydantic/httpx2/blob/main/docs/quickstart.md>`__ module.
For a full listing of what's possible, read that module's documentation. Most if
not all users can simply use the following pattern:

.. code-block:: python

  r = client.some_endpoint()
  assert r.status_code == httpx2.codes.OK, r.raise_for_status()
  data = r.json()

The API indicates errors using the response status code, and this pattern will
raise the appropriate exception if the response is not a success. The data can
be fetched by calling the ``.json()`` method.

This data will be pure python data structures which can be directly accessed.
You can also use your favorite data analysis library's dataframe format using
the appropriate library. For instance you can create a `pandas
<https://pandas.pydata.org/>`__ dataframe using `its conversion method
<https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.from_dict.html>`__.

**Note:** Because this project has no relationship whatsoever with Charles Schwab,
this document makes no effort to describe the structure of the returned JSON
objects. Schwab might change them at any time, at which point this document will
become silently out of date. Instead, each of the methods described below
contains a link to the official documentation. For endpoints that return
meaningful JSON objects, it includes a JSON schema which describes the return
value. Please use that documentation or your own experimentation when figuring
out how to use the data returned by this API.


.. _account_hashes:

++++++++++++++
Account Hashes
++++++++++++++

Many methods of this API are parametrized by account. However, the API does not
accept raw account numbers, but rather account hashes. You can fetch these
hashes using the ``get_account_numbers`` method :ref:`(link)
<account_hashes_method>`. The JSON body of its response is a list pairing each
account number the token can use with the account hash that must be passed
when referring to that account in API calls, and
:func:`~schwab.utils.find_account_hash` picks out the one you mean.

Here is an example of how to fetch an account hash and use it to place an order:

.. code-block:: python

  import httpx2

  from schwab.auth import easy_client
  from schwab.orders.equities import equity_buy_market
  from schwab.utils import find_account_hash

  c = easy_client(
          api_key='api-key',
          app_secret='app-secret',
          callback_url='https://127.0.0.1:8182',
          token_path='/path/to/token.json')

  resp = c.get_account_numbers()
  assert resp.status_code == httpx2.codes.OK

  # resp.json() is a list, with one entry per account the token can use:
  # [
  #    {
  #        "accountNumber": "123456789",
  #        "hashValue":"123ABCXYZ"
  #    }
  #]
  # Schwab documents no order for it, so find your account rather than
  # taking the first.
  account_hash = find_account_hash(resp.json(), '123456789')

  c.place_order(account_hash, equity_buy_market('AAPL', 1))



++++++++++++++++++
Timeout Management
++++++++++++++++++

Timeouts for HTTP calls are managed under the hood by the ``httpx2`` library.
``schwab`` defaults to 30 seconds, which experience has shown should be more
than enough to allow even the slowest API calls to complete. A different timeout
specification can be set using this method:

.. automethod:: schwab.client.Client.set_timeout


+++++++++
Token Age
+++++++++

.. automethod:: schwab.client.Client.token_age


++++++++++++
Account Info
++++++++++++

These methods provide access to useful information about accounts. An incomplete
list of the most interesting bits:

* Account balances, including available trading balance
* Positions
* Order history

.. note::

   ``cashAvailableForTrading`` **was present as** ``0.0`` **on an account
   holding no cash**, not omitted. It sits under
   ``securitiesAccount.currentBalances`` in :meth:`get_account
   <schwab.client.Client.get_account>`'s response. That was one live account,
   and which ``fields`` were requested was not recorded. A check for the key
   being absent is not a check for zero.

See the official documentation for each method for a complete response schema.

.. _account_hashes_method:

.. automethod:: schwab.client.Client.get_account_numbers
.. automethod:: schwab.client.Client.get_account
.. automethod:: schwab.client.Client.get_accounts
.. autoclass:: schwab.client.Client.Account
  :members:
  :undoc-members:


+++++++++++++
Price History
+++++++++++++

Schwab provides price history for equities and ETFs. It does not provide price
history for options, futures, or any other instruments.

In the raw API, fetching price history is somewhat complicated: the API offers a
single endpoint :meth:`Client.get_price_history` that accepts a complex variety
of inputs, but fails to document them in any meaningful way.

Thankfully, we've reverse engineered this endpoint and built some helpful
utilities for fetching prices by minute, hour, day, week, etc. Each method can
be called with or without date bounds. When called without date bounds, it
returns all data available. Each method offers a different lookback period, so
make sure to read the documentation below to learn how much data is available.

.. rubric:: Hourly candles

Schwab's endpoint stops at thirty-minute intraday candles. NG adds
:meth:`Client.get_price_history_every_hour`, which requests those candles and
combines consecutive pairs locally while preserving the usual
``httpx2.Response`` interface:

.. code-block:: python

   response = c.get_price_history_every_hour(
           'AAPL', need_extended_hours_data=False)
   response.raise_for_status()
   hourly_candles = response.json()['candles']

The result uses the first candle's ``open`` and ``datetime``, the larger
``high``, the smaller ``low``, the second candle's ``close``, and the sum of
both ``volume`` values. For regular-session data the pairs are 09:30 + 10:00,
10:30 + 11:00, and so on, in US Eastern time.

Only candles exactly thirty minutes apart are combined. A candle beside a gap
and a final candle without a partner are omitted, because neither describes a
full hour. With extended-hours data, pairs begin at the first candle Schwab
returns after each gap. Set ``need_extended_hours_data=False`` when the regular
09:30 open is the alignment you want.

The newest thirty-minute source candle can still be forming, so the newest
hourly result can also be incomplete in time even though it has two members.
Check its timestamp before treating it as closed. ``AsyncClient`` provides the
same method and response shape; await it normally.

.. note::

   Give any of these a ``start_datetime`` or an ``end_datetime`` and that is
   the range requested. No ``period`` is sent alongside it:
   :meth:`Client.get_price_history` documents that the two should not be
   combined, and what Schwab does when they are is not consistent across
   accounts --- it has been reported disregarding the range, and measured
   honouring it. How far back the candles returned can reach is a separate
   limit, in the next note.

.. note::

   **A longer range did not reach further back.** Asked for thirty-minute
   candles starting 400 days back, and again about 1,014 days back,
   :meth:`get_price_history_every_thirty_minutes
   <schwab.client.Client.get_price_history_every_thirty_minutes>` returned
   identical candles, beginning about 260 days before the request. That was
   measured once, on one day, without extended hours, and the number of candles
   differed by symbol. Check the first candle you get back rather than assuming
   it is the start you asked for.

.. note::

   **The newest thirty-minute candle can still be forming.** Thirty-minute
   candles are labelled with their open time: over four regular sessions of one
   liquid ETF, each session's first candle was labelled 09:30 US Eastern and
   its last 15:30. Requested hourly, seconds after half past the hour,
   :meth:`get_price_history_every_thirty_minutes
   <schwab.client.Client.get_price_history_every_thirty_minutes>` has returned
   the candle that opened at that half hour, which cannot yet have closed. That
   was seen on liquid ETFs at nearly every request over one day on one account,
   and not on a thinly traded one; the number of requests was not recorded,
   and it has not been checked on another day. Other frequencies, other times
   and extended hours were not checked. Before treating the last candle as
   closed, check that its open time plus thirty minutes is not later than your
   request.

.. automethod:: schwab.client.Client.get_price_history_every_minute
.. automethod:: schwab.client.Client.get_price_history_every_five_minutes
.. automethod:: schwab.client.Client.get_price_history_every_ten_minutes
.. automethod:: schwab.client.Client.get_price_history_every_fifteen_minutes
.. automethod:: schwab.client.Client.get_price_history_every_thirty_minutes
.. automethod:: schwab.client.Client.get_price_history_every_hour
.. automethod:: schwab.client.Client.get_price_history_every_day
.. automethod:: schwab.client.Client.get_price_history_every_week

For the sake of completeness, here is the documentation for the raw price
history endpoint, in all its complexity.

.. automethod:: schwab.client.Client.get_price_history
.. autoclass:: schwab.client.Client.PriceHistory
  :members:
  :undoc-members:
  :member-order: bysource

++++++++++++++
Current Quotes
++++++++++++++

.. note::

   **Multi-symbol quote requests can be rate-limited.** :meth:`get_quotes
   <schwab.client.Client.get_quotes>` has returned HTTP 429 in four separate
   minutes of live use, while price history and account requests on the same
   token in those minutes did not. :meth:`get_quote
   <schwab.client.Client.get_quote>` was not measured. Schwab's documentation
   gives a request limit only for placing, replacing and cancelling orders, no
   ``Retry-After`` header was recorded, and four minutes are not enough to
   infer a rate. Handle a 429 from ``get_quotes``; that price history and
   account requests were not seen to return one does not mean they, or any
   other call, cannot.

.. autoclass:: schwab.client.Client.Quote.Fields
  :members:
  :undoc-members:
.. automethod:: schwab.client.Client.get_quote
.. automethod:: schwab.client.Client.get_quotes

.. _option_chain:

+++++++++++++
Option Chains
+++++++++++++

An option chain is market data, not an order. It tells you which contracts
Schwab currently returns and gives each contract's exact ``symbol``; use those
symbols with the :ref:`option order templates <order_templates>`. Requesting a
``STRADDLE`` or ``VERTICAL`` chain does **not** create that order. It asks the
market-data endpoint to organize or calculate a strategy-shaped response.

A small single-contract window is a useful starting point:

.. code-block:: python

  import datetime

  from schwab.client import Client

  response = client.get_option_chain(
      'AAPL',
      contract_type=Client.Options.ContractType.ALL,
      strike_count=5,
      from_date=datetime.date(2027, 1, 1),
      to_date=datetime.date(2027, 3, 31),
      option_type=Client.Options.Type.STANDARD,
  )
  response.raise_for_status()
  chain = response.json()

The parameter groups answer different questions:

* ``contract_type`` selects calls, puts, or both. ``option_type`` selects
  standard, non-standard, or all contracts; these are different filters.
* ``strike`` requests one exact strike, ``strike_range`` requests a moneyness
  category, and ``strike_count`` asks for a number of strikes around the
  market. The client sends whichever combination you provide and does not
  decide whether Schwab considers that combination meaningful. Start with one
  strike selector unless you have verified a combination against the current
  endpoint.
* ``from_date`` and ``to_date`` delimit expirations. Pass
  ``datetime.date`` objects, not ISO strings. A ``datetime`` is accepted
  because it is a ``date`` subclass, but this endpoint serializes only its
  calendar day and discards the time.
* ``exp_month`` filters by calendar month across the requested window.
* ``strategy`` requests a strategy chain. ``interval`` supplies the strike
  interval used by spread-shaped strategy chains. ``volatility``,
  ``underlying_price``, ``interest_rate``, and ``days_to_expiration`` are
  analytical inputs and apply to ``ANALYTICAL`` chains.
* ``include_underlying_quote`` asks Schwab to include the underlying quote.
  ``entitlement`` identifies the market-data entitlement when one must be
  stated explicitly.

For example, this requests market data arranged as verticals; it does not
construct a vertical order:

.. code-block:: python

  response = client.get_option_chain(
      'AAPL',
      strategy=Client.Options.Strategy.VERTICAL,
      interval=5.0,
      strike_count=3,
  )
  response.raise_for_status()

**Response handling**

For a single chain, Schwab commonly groups contracts beneath
``callExpDateMap`` and ``putExpDateMap``. Treat the expiration-map and
strike-map keys as labels rather than parsing business logic out of them. A
strike can contain more than one contract record, and either map can be empty
or absent. This guarded traversal collects the records without assuming one
contract per strike:

.. code-block:: python

  contracts = []
  for side in ('callExpDateMap', 'putExpDateMap'):
      for strike_map in chain.get(side, {}).values():
          for contracts_at_strike in strike_map.values():
              contracts.extend(contracts_at_strike)

  symbols = [contract['symbol'] for contract in contracts
             if 'symbol' in contract]

Do not rely on map ordering, take the first expiration or strike without
checking it, or synthesize a symbol from a display description when Schwab has
already returned the exact symbol. Empty results are valid market-data results,
not necessarily client failures. The response schema belongs to Schwab and can
change independently of this library; check the HTTP status, retain the raw
response while diagnosing, and code defensively around optional fields. The
current official endpoint specification is linked from the method reference
below and may require signing in to the Schwab Developer Portal.

.. automethod:: schwab.client.Client.get_option_chain
.. autoclass:: schwab.client.Client.Options
  :members:
  :undoc-members:

The similarly named
:class:`~schwab.orders.common.ComplexOrderStrategyType` belongs to order
construction, not chain retrieval. See :ref:`complex_options_strategies` and
:ref:`order_templates` after selecting contracts.

If you only need to know *when* contracts expire rather than what they cost,
there is a cheaper call which returns the expiration list on its own:

.. automethod:: schwab.client.Client.get_option_expiration_chain

+++++++++++++++++++++++++++++++++++++
Instrument Searching and Fundamentals
+++++++++++++++++++++++++++++++++++++

.. automethod:: schwab.client.Client.get_instruments
.. automethod:: schwab.client.Client.get_instrument_by_cusip
.. autoclass:: schwab.client.Client.Instrument
  :members:
  :undoc-members:

.. _orders-section:

++++++
Orders
++++++

.. danger::

  **The order methods do not take their arguments in the same order.**

  .. code-block:: python

    c.place_order(account_hash, order_spec)
    c.replace_order(account_hash, order_id, order_spec)
    c.preview_order(account_hash, order_spec)

    c.cancel_order(order_id, account_hash)      # note the order
    c.get_order(order_id, account_hash)         # and here

  Both arguments are opaque strings, so swapping them raises nothing locally.
  It sends a well-formed request naming the wrong account or the wrong order,
  and you find out from the response --- or from a cancel that quietly did not
  cancel what you meant. One caller running this for live trading keeps a
  regression test pinning the argument order of each of these, which is a
  fair signal of how easy the mistake is.


.. _placing_new_orders:

------------------
Placing New Orders
------------------

Placing new orders can be a complicated task. The :meth:`Client.place_order`
method is used to create all orders, from equities to options. The precise order
type is defined by a complex order spec. Schwab provides some `example order
specs`_ to illustrate the process and provides a schema in the `place order
documentation
<https://developer.schwab.com/products/trader-api--individual/details/specifications/Retail%20Trader%20API%20Production>`__,
but beyond that we're on our own.

``schwab`` includes some helpers, described in :ref:`order_templates`, which
provide an incomplete utility for creating various order types. While it only
scratches the surface of what's possible, we encourage you to use that module
instead of creating your own order specs.

.. _`example order specs`: https://developer.schwab.com/products/trader-api--individual/details/documentation/Retail%20Trader%20API%20Production

.. automethod:: schwab.client.Client.place_order

.. danger::

  **An order can fill --- its whole lifecycle delivered on** ``ACCT_ACTIVITY``
  **--- before** :meth:`place_order <schwab.client.Client.place_order>`
  **returns.** On a live account, a single push carried a market order from
  ``OrderCreated`` through ``OrderFillCompleted`` before the call that placed
  it had handed back the order id.

  So a stream handler that decides whether an order is yours by looking its id
  up among the ids you already hold can file your own fill as someone else's,
  with no error. While a placement is still in flight, not recognising an id
  does not mean the order is not yours.

  :ref:`Seen once, not reproduced <confidence_tags>`. The ordering is what a
  consumer observed, not a measurement of when Schwab sent each message, and
  how often it happens is not known.

**Testing an order without placing it.** Schwab will tell you whether it would
accept an order, and what it would become, without sending it to the market.
That is worth doing the first time you construct an order type programmatically
--- a rejection here costs nothing, while a malformed order discovered at
placement time costs an execution window.

.. automethod:: schwab.client.Client.preview_order

.. _accessing_existing_orders:

-------------------------
Accessing Existing Orders
-------------------------

.. automethod:: schwab.client.Client.get_orders_for_account
.. automethod:: schwab.client.Client.get_orders_for_all_linked_accounts
.. automethod:: schwab.client.Client.get_order
.. autoclass:: schwab.client.Client.Order
  :members:
  :undoc-members:

-----------------------
Editing Existing Orders
-----------------------

Endpoints for canceling and replacing existing orders.

These endpoints require the order ID. Because the API does not return a JSON
response when creating an order, the workflow for extracting this order ID is a
little complicated.  You can fetch the order ID from the response to a
:meth:`place_order <schwab.client.Client.place_order>` request using :ref:`this
helper function <extract_order_id>`. Otherwise, see
:ref:`accessing_existing_orders` for finding historical orders.

.. automethod:: schwab.client.Client.cancel_order
.. automethod:: schwab.client.Client.replace_order

.. danger::

  **Replacing an order that is already gone returns HTTP 400 --- and so does a
  malformed order spec.** The status alone cannot tell "the order you are
  replacing has already filled or cancelled" from "your request is wrong", and
  those want opposite responses: the first means stop, the second means fix and
  retry. A caller that cannot separate them has to treat every refusal as a
  fault, which strands a leg that merely filled. Re-read the target order to
  tell them apart. Venue-observed.

  **A replacement is a new order with a new ID.** The original stops working
  and a fresh one takes its place, so anything tracking the old ID is watching
  an order that has ended --- and will conclude the position closed while the
  replacement is still working.

  That order does not necessarily read ``CANCELED``. :meth:`get_order
  <schwab.client.Client.get_order>` read ``REPLACED`` on each ID a
  :ref:`price change <account_activity_price_change>` retired on an option
  order --- five of five, on one order. Those changes were made by hand in
  Schwab's own interface, not through this method, so whether a replacement
  made here reads the same has not been checked. A check for ``CANCELED``
  alone would miss ``REPLACED``; membership in
  :attr:`Client.Order.TERMINAL_STATUSES
  <schwab.client.Client.Order.TERMINAL_STATUSES>` covers both.

  Getting the new ID is less settled than it looks. Schwab documents the
  ``Location`` header nowhere at all --- :meth:`Utils.extract_order_id
  <schwab.utils.Utils.extract_order_id>` reads it because that is where a
  placed order's ID is observed to arrive, not because it is specified. Whether
  a replacement answers the same way has not been established here.

  So do not assume the ID you hold is still the live one:

  .. code-block:: python

    r = client.replace_order(account_hash, order_id, new_order_spec)
    r.raise_for_status()

    # The ID in hand now refers to an order that has stopped working, and
    # its status may read REPLACED rather than CANCELED. Find the
    # replacement rather than inferring it -- see the reconciliation recipe.
    order_id = None

  :ref:`reconciling` shows how to locate an order you have no ID for, which is
  exactly the position a replacement leaves you in. If you find that
  ``extract_order_id`` does read the new ID from a replacement response,
  `that is worth reporting
  <https://github.com/neusse/Schwab-py-NG/issues>`__ --- it would settle this.

**Testing a replacement without sending it.** :meth:`preview_order
<schwab.client.Client.preview_order>` takes the same order spec and reports
what Schwab would do with it, which is worth a call the first time a
replacement is constructed programmatically:

.. code-block:: python

  r = client.preview_order(account_hash, new_order_spec)
  r.raise_for_status()
  print(r.json())


+++++++++++++++
Other Endpoints
+++++++++++++++

Note: if your account is limited to delayed quotes, these quotes are
delayed too.

-------------------
Transaction History
-------------------

.. automethod:: schwab.client.Client.get_transaction
.. automethod:: schwab.client.Client.get_transactions
.. autoclass:: schwab.client.Client.Transactions
  :members:
  :undoc-members:

----------------
User Preferences
----------------

.. automethod:: schwab.client.Client.get_user_preferences

-------------
Market Movers
-------------

.. automethod:: schwab.client.Client.get_movers
.. autoclass:: schwab.client.Client.Movers
  :members:
  :undoc-members:


------------
Market Hours
------------

.. automethod:: schwab.client.Client.get_market_hours
.. autoclass:: schwab.client.Client.MarketHours
  :members:
  :undoc-members:

