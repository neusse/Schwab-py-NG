.. _easy_orders:

========================
Guided Order Workflows
========================

The ordinary order templates remain the smallest way to build an order, and
the client methods remain the lowest-level way to send one. ``EasyOrders`` sits
between them for applications that want one reusable workflow around an
account: convenient equity orders, Schwab preview, explicit live-order
confirmation, sequential batches, and caller-owned JSON templates.

It adapts the useful workflow from the MIT-licensed
`neusse/Schwab_EZ_Orders
<https://github.com/neusse/Schwab_EZ_Orders>`__ prototype while using NG's
existing, tested :class:`~schwab.orders.generic.OrderBuilder` and order
templates. It does not create a client, own a token, keep hidden history, or
install a second order-schema implementation.


-----------------------------
Preview before live placement
-----------------------------

.. code-block:: python

  from schwab.orders.easy import EasyOrders
  from schwab.utils import find_account_hash

  account_hash = find_account_hash(
          client.get_account_numbers().json(), '123456789')
  orders = EasyOrders(client, account_hash)

  order = orders.buy('AAPL', 10, limit_price='210.50')

  # Safe: asks Schwab to validate the order and returns its raw response.
  preview = orders.preview(order)
  preview.raise_for_status()

  # Live: preview again, then place only if the preview succeeds.
  result = orders.place(order, confirm_live_order=True)
  result.place_response.raise_for_status()

``confirm_live_order=True`` is intentionally required by ``place`` and
``place_many``. It is a code-level acknowledgement, not a terminal prompt, so
the workflow also works in services and scheduled jobs.
``AsyncEasyOrders`` provides the same workflow for ``AsyncClient``; await its
preview and placement methods normally.

.. warning::

   Schwab's preview endpoint is order validation, **not paper trading**. A
   successful preview does not simulate fills, reserve buying power, promise
   that a later placement will be accepted, or prove that the order will
   execute at the price shown. No placement request is sent until ``place`` is
   called with explicit confirmation.

Every response remains the raw ``httpx2.Response``. When a preview fails,
``OrderSubmission.place_response`` is ``None`` and no placement was attempted.
When it is present, ``OrderSubmission.placed`` means the placement request was
sent; it does not mean Schwab accepted or filled it. Inspect the response.


-------------------
Convenient builders
-------------------

``buy`` and ``sell`` build market orders unless ``limit_price`` is given.
``stop_loss`` and ``trailing_stop_loss`` build exits for an existing long
equity position. ``bracket`` builds a limit entry which triggers an OCO pair:
a profit-target limit order and a stop-loss order. All return the same
``OrderBuilder`` used everywhere else, so callers can continue refining it
before previewing.

For option orders and more strategies, pass any builder from
:ref:`order_templates` to the same ``preview`` and ``place`` methods:

.. code-block:: python

  from schwab.orders.options import bull_call_vertical_open

  spread = bull_call_vertical_open(
          'AAPL  270115C00200000',
          'AAPL  270115C00210000',
          1,
          '3.20')
  result = orders.place(spread, confirm_live_order=True)


-----------------------
Batches and rate limits
-----------------------

``preview_many`` and ``place_many`` operate sequentially, not concurrently.
Use ``pause_between`` to reduce bursts. ``place_many`` stops at the first
failed preview or placement by default; pass ``stop_on_error=False`` only when
later orders are independent of earlier ones.

The client's opt-in :meth:`~schwab.client.Client.set_rate_limit_retry`
configuration can recover returned 429 responses from safe ``GET`` requests.
It never automatically repeats an order placement, replacement or
cancellation response. The guided workflow keeps that rule: a failed mutation
is returned to the caller for reconciliation, never guessed at and repeated.


----------------------
Caller-owned templates
----------------------

Templates are written only to the path supplied by the caller. Writes are
atomic, and loading validates the format version and order shape:

.. code-block:: python

  from schwab.orders.easy import load_order_template, save_order_template

  save_order_template(
          'strategy-orders/aapl-entry.json', order,
          name='AAPL entry', description='Reviewed limit entry')

  saved_order = load_order_template('strategy-orders/aapl-entry.json')
  preview = orders.preview(saved_order)

The library does not choose a template directory, delete templates, or retain
an order-history file. Applications which need an audit log should store the
raw preview and placement responses in their own system of record.

A complete preview-first script, with live placement disabled in its checked-in
form, is in `examples/orders/easy_orders.py
<https://github.com/neusse/Schwab-py-NG/blob/main/examples/orders/easy_orders.py>`__.


---------
Reference
---------

.. autoclass:: schwab.orders.easy.EasyOrders
   :members:

.. autoclass:: schwab.orders.easy.AsyncEasyOrders
   :members:

.. autoclass:: schwab.orders.easy.OrderSubmission
   :members:

.. autofunction:: schwab.orders.easy.save_order_template
.. autofunction:: schwab.orders.easy.load_order_template
.. autoexception:: schwab.orders.easy.LiveOrderConfirmationError
.. autoexception:: schwab.orders.easy.OrderTemplateError
