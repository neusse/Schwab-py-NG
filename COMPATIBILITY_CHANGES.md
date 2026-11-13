# Compatibility Changes

This guide is for programs moving from Alex Golec's original
[`schwab-py`](https://github.com/alexgolec/schwab-py) to Schwab-py-NG. It
describes changes that can require code, dependency, configuration, or
operational updates. Additive APIs are generally omitted unless they change
the behavior or shape of an existing call.

The comparison baseline is the upstream `main` revision recorded in
[INTEGRATION.md](INTEGRATION.md). Schwab-py-NG continues to use the `schwab`
Python import package, so most imports and ordinary REST calls remain
compatible.

## Why compatibility changes were necessary

The original project solved a large and difficult problem well, but any API
client accumulates bit rot when the services and dependencies around it keep
moving. Schwab's live responses have developed shapes and behaviors that were
not represented in the original client. Python has deprecated older runtime
patterns, Authlib changed its HTTP integration, and `websockets` replaced its
legacy client API. Some old compatibility paths had also become technical
debt: parameters that were accepted but unused, values labeled with the wrong
meaning, and error paths that could leave a live order untracked.

Other debt was operational rather than syntactic. Streaming calls could wait
forever, handler failures behaved differently depending on whether a handler
was synchronous or asynchronous, token writes were not crash-safe, and debug
logs could expose access tokens or full account numbers. Those behaviors may
have been reasonable or unavoidable when they were introduced; leaving them
unchanged after their failure modes were known would not be reasonable for a
client used with funded accounts.

Schwab-py-NG therefore favors explicit failures, current dependency APIs,
credential safety, and preserving enough information to recover a live order.
That sometimes conflicts with exact bug-for-bug compatibility. The changes
below are the migration cost of addressing that accumulated drift and debt.
They are documented so an upgrade does not turn a known correction into a new
surprise.

This is a migration guide, not the complete release history. See
[CHANGELOG.md](CHANGELOG.md) for the rationale, measurements, and regression
coverage behind individual changes.

## Compatibility summary

| Area | Risk | What to audit |
| --- | --- | --- |
| Installation | High | Environments containing both distributions |
| HTTP types | High | `httpx` imports, exception handlers, response type checks, and mocks |
| Orders | High | Numeric price arguments, order-ID handling, and venue routing |
| Streaming | High | Constructor arguments, timeouts, handler failures, field names, and shutdown |
| Authentication | Medium | Token-file validation and caught exception types |
| Logging | Medium | Custom handlers and error-tracking integrations |
| Market data | Medium | Exact response ranges and exact-key schemas |

## Additive application utilities

The ``schwab.contrib.account``, ``schwab.contrib.export``,
``schwab.contrib.market_data``, and ``schwab.contrib.streaming`` modules and
the ``schwab-ng-doctor`` command are additive. Existing client return values,
stream handlers, and subscription methods are unchanged. No pandas, Rich,
yfinance, Alpaca, matplotlib, GUI, or strategy dependency is installed.

The utilities deliberately do not reproduce several behaviors from the old
``schwab-py-extra`` experiments: they do not create or cache clients, persist
environment variables, manually refresh or delete token files, reveal token
suffixes or account numbers, or write databases from the shared stream reader.

## Installation and runtime

### The two distributions cannot share an environment

`schwab-py` and `schwab-py-ng` both install the `schwab` import package. Pip
tracks them as different distributions even though they claim the same files,
so installing one over the other can create a mixed or partially deleted
package.

Use a clean environment, or uninstall the original distribution first:

```shell
pip uninstall -y schwab-py
pip install "schwab-py-ng @ git+https://github.com/neusse/Schwab-py-NG.git"
```

Imports deliberately remain the same:

```python
import schwab
from schwab.auth import easy_client
```

### Python 3.10 or newer is required

Schwab-py-NG supports Python 3.10 through 3.14 on Windows and Linux. macOS is
not part of the tested support contract.

## HTTP client and dependency changes

### Responses and HTTP exceptions come from `httpx2`

Schwab-py-NG uses `httpx2>=2.12.0` with `Authlib>=1.8`. `httpx` and `httpx2`
do not share a response or exception hierarchy. Code can therefore stop
matching without raising an obvious migration error.

Audit code such as:

```python
except httpx.HTTPStatusError:
    ...

isinstance(response, httpx.Response)
```

and update it to use the corresponding `httpx2` types. Test doubles and mocks
must construct the same response type the library now returns.

### Streaming requires `websockets>=14.0`

The streaming implementation uses `websockets.asyncio` rather than the legacy
client:

- `websocket_connect_args["extra_headers"]` must become
  `websocket_connect_args["additional_headers"]`.
- `create_protocol` and `read_limit` have no equivalent and are rejected.
- The underlying connection is no longer a `WebSocketClientProtocol`; code
  that annotates, inspects, or mocks that implementation type must change.

## Order construction and order tracking

### Prices must be strings or `Decimal`

`OrderBuilder.set_price()` and `set_stop_price()` reject integers and floats.
This includes calls such as `set_price(125)` as well as `set_price(125.50)`.

Pass an intentional spelling instead:

```python
builder.set_price("125.50")
builder.set_stop_price("124.00")
```

Prebuilt order templates use these setters and have the same requirement.

### `Decimal` prices are not truncated

A `Decimal` is transmitted with the precision supplied by the caller.
`Decimal("12.129")` therefore remains `12.129`; the library no longer changes
it to `12.12`. Programs that require tick-size rounding must perform it
explicitly before building the order. Construct `Decimal` values from strings,
not binary floats.

### Venue routing uses `set_requested_destination()`

`set_destination_link_name()` now follows Schwab's schema and accepts the free
string field named `destinationLinkName`. It is not the venue selector.
Programs intending to route an order to a venue must use:

```python
builder.set_requested_destination(Destination.NYSE)
```

This is a semantic migration rather than just a rename: the old call could
complete without selecting the venue the caller intended.

### `extract_order_id()` raises instead of returning `None`

When Schwab accepts an order but omits an order ID or returns an unrecognized
`Location` header, `Utils.extract_order_id()` now raises an
`OrderIdNotFoundError` subclass. The order may already be live, so treating the
result like an ordinary `None` can lose the only opportunity to reconcile it.

Replace checks like:

```python
order_id = utils.extract_order_id(response)
if order_id is None:
    ...
```

with exception handling that immediately checks the account's open and recent
orders:

```python
try:
    order_id = utils.extract_order_id(response)
except OrderIdNotFoundError:
    # The order may be live. Reconcile with get_orders_for_account().
    raise
```

### `AccountHashMismatchException` carries live-order information

The exception now carries the response, order ID, actual account hash, and
expected account hash. Catching the exception remains compatible, but code or
test doubles that construct it with a bare message must use the new signature.
Because the order is live on the account Schwab named, record
`exception.order_id` before re-raising or exiting.

### Order-code generation APIs and scripts were removed

The following original public surface is no longer available:

- `schwab.contrib.orders`
- `construct_repeat_order`
- `code_for_builder`
- `UnrepeatableOrderError`
- `schwab-order-codegen.py`
- `schwab-generate-token.py`
- `schwab.scripts.orders_codegen`

The ordinary `OrderBuilder` remains available. Token creation is performed
with the documented authentication functions rather than an installed script.

## Streaming behavior

### `StreamClient(account_id=...)` is no longer accepted

The original parameter was unused. Remove it:

```python
stream = schwab.streaming.StreamClient(client)
```

### Streaming requests time out

An unanswered subscription, unsubscription, login, or logout request raises
`ResponseTimeoutError` after 60 seconds instead of waiting forever. Passing
`response_timeout=None` restores the old wait-forever behavior:

```python
stream = schwab.streaming.StreamClient(client, response_timeout=None)
```

### Handler exceptions are isolated

An exception raised by a synchronous stream handler no longer propagates from
`handle_message()`. Synchronous and asynchronous handler failures are logged
and sent to registered error handlers so one handler cannot stop dispatch to
the others. Programs that caught handler errors around `handle_message()` must
instead register an error handler or monitor the `schwab.streaming` logger.

### Message delivery can interleave with requests

Messages read while a streaming request is in flight are dispatched in arrival
order. The original implementation held them until the request completed
because one lock covered both requesting and reading. Programs that assumed no
handler could run during a subscription or unsubscription call must add their
own coordination.

### `logout()` closes the connection

`await stream.logout()` now closes the WebSocket and its associated resources.
No later stream operation is possible until `login()` initializes a new
connection. `close()` and async context-manager support are also available for
explicit lifecycle management.

### Option field `STRIKE_TYPE` became `STRIKE_PRICE`

Field 20 of `LEVELONE_OPTIONS` is a strike price. Relabeled messages now contain
`"STRIKE_PRICE"`, and `LevelOneOptionFields.STRIKE_TYPE` is no longer present.
Audit both enum references and dictionary lookups.

### Book field `SEQUENCE` became `QUOTE_TIME`

The per-exchange field in `NYSE_BOOK`, `NASDAQ_BOOK`, and `OPTIONS_BOOK`
messages is now labeled `QUOTE_TIME`. It is milliseconds since midnight US
Eastern, not a sequence counter or epoch timestamp. In particular, audit
`entry.get("SEQUENCE")`, because it changes silently to `None` rather than
raising.

### Default equity subscriptions include fractional-share fields

A level-one equity subscription that does not specify fields now requests five
additional fields, including fractional last-size and volume information.
Handlers normally tolerate the added keys, but strict schemas, exact dictionary
comparisons, and serialized snapshots may need updating.

## Authentication and token handling

### Token files are validated more strictly

A token creation timestamp that is missing, nonnumeric, non-finite, Boolean,
or nested in an unusable token shape raises `ValueError`. `easy_client()` no
longer treats such a malformed file as merely old and automatically starts a
new login. Repair or remove the invalid token file before authenticating again.

Token writes are now atomic and restrictive so a crash does not truncate the
only refresh credential and a newly created token is not world-readable on
platforms that support Unix file modes.

### Authentication exceptions are more specific

Token refresh refusals consistently raise `TokenRefreshError`, including a
refusal whose body is empty or not JSON. Login code-exchange refusals raise
`LoginExchangeError`, which remains an Authlib `OAuthError`.

Audit handlers that previously caught `json.JSONDecodeError`, `ValueError`,
`HTTPStatusError`, or a generic Authlib error for these cases. Server errors
and transport failures remain HTTP-client errors rather than token-refusal
errors.

### Login callback handling is stricter

Malformed redirects, fragments, missing codes, and mismatched state values are
no longer exchanged as though they were valid authorization callbacks. A late
redirect belonging to another login can be skipped while the current flow
continues waiting. Programs that wrap the callback flow should not assume the
first request received is necessarily exchanged.

## Logging and diagnostics

### Library and dependency logs are sanitized

Schwab-py-NG redacts known access tokens, authorization codes, app credentials,
and full account numbers from library and dependency logs. To prevent a custom
formatter from rendering the original exception again, a logged exception may
reach handlers with:

- a preformatted and redacted message,
- empty `record.args`,
- cleared `record.exc_info`, and
- redacted traceback text in `record.exc_text`.

Standard logging formatters continue to work. Custom JSON formatters, queue
handlers, and error-tracking integrations that read `exc_info` directly should
read the sanitized text instead and be tested with authentication and streaming
failures.

## Input and market-data behavior

### Option-symbol parsing is stricter

`OptionSymbol.parse_symbol()` requires Schwab's fixed 21-character option
symbol layout and rejects malformed padding, dates, sides, and strike fields.
The original implementation could parse a malformed string as a different
contract, so inputs previously accepted are not necessarily safe to normalize
automatically.

### Price-history helpers honor explicit ranges

When a price-history convenience method receives explicit start and end dates,
it no longer also sends an unrelated `period`. Schwab has not treated the
conflicting parameters consistently across accounts, so a program that
accidentally relied on the old combination may receive a different range. The
new `get_price_history_every_hour()` method is additive and does not alter the
existing helper signatures.

### Datetimes with unusable timezone information are treated as naive

A datetime whose `tzinfo` returns no UTC offset is treated as naive rather than
being silently converted from the host machine's local timezone. Existing
naive-datetime warnings and conversions therefore also apply to this case.

## Migration checklist

Before running an original program against a funded account:

1. Create a clean environment and install only `schwab-py-ng`.
2. Confirm Python 3.10 or newer and update `httpx`/`websockets` integrations.
3. Search for numeric `set_price` and `set_stop_price` arguments.
4. Search for `account_id=`, `STRIKE_TYPE`, `SEQUENCE`, `extra_headers`,
   `create_protocol`, and `read_limit`.
5. Replace `extract_order_id() is None` handling with reconciliation-aware
   exception handling.
6. Review stream timeout, handler-error, interleaving, and logout assumptions.
7. Test custom logging handlers for sanitized exception records.
8. Validate token-file recovery and authentication exception handling.
9. Run market-data and streaming parsers against added or renamed fields.
10. Exercise order placement first with the smallest acceptable risk and
    reconcile every result directly against the broker.

