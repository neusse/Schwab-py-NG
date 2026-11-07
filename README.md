<div align="center">

<img src="docs/assets/schwab-py-ng-banner.svg" alt="Schwab-py-NG — hardened Python access to the Charles Schwab API" width="100%">

# Schwab-py-NG

**Hardened Python access to the Charles Schwab API, built for code that trades real money.**

[![Tests](https://github.com/neusse/Schwab-py-NG/actions/workflows/python.yml/badge.svg)](https://github.com/neusse/Schwab-py-NG/actions/workflows/python.yml)
[![Documentation](https://github.com/neusse/Schwab-py-NG/actions/workflows/docs-pages.yml/badge.svg)](https://neusse.github.io/Schwab-py-NG/)
[![Version](https://img.shields.io/badge/version-5.2.0-0ea5e9.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-3776ab.svg?logo=python&logoColor=white)](setup.py)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux-14b8a6.svg)](#support-matrix)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Documentation](https://neusse.github.io/Schwab-py-NG/) · [Compatibility](COMPATIBILITY_CHANGES.md) · [Changes](CHANGELOG.md) · [Integration notes](INTEGRATION.md) · [Install](#installing) · [Quick start](#sixty-seconds-in) · [Contributing](https://neusse.github.io/Schwab-py-NG/contributing.html)

</div>

```shell
pip uninstall -y schwab-py
pip install "schwab-py-ng @ git+https://github.com/neusse/Schwab-py-NG.git"
```

Every endpoint Schwab publishes, an order builder that produces JSON Schwab
accepts, and a streaming client that turns this:

```python
{'key': 'AAPL', '1': 421.55, '2': 421.60, '3': 421.58}
```

into this:

```python
{'key': 'AAPL', 'BID_PRICE': 421.55, 'ASK_PRICE': 421.60, 'LAST_PRICE': 421.58}
```

Synchronous and `asyncio` over the same interface. Python 3.10–3.14 on
Windows and Linux.

## Project status

Schwab-py-NG currently identifies as version 5.2.0. It keeps the established
`schwab` import namespace while consolidating the strongest maintained fixes
from the forks reviewed in [INTEGRATION.md](INTEGRATION.md). The full suite
contains more than 1,300 tests, and every push is checked against Python
3.10–3.14. Pull requests, tags, and manually dispatched CI runs additionally
exercise Windows.

This repository is the install source for now; Schwab-py-NG has not been
published to PyPI. Install it directly from GitHub as shown above.

## Documentation and changes

The complete, searchable documentation is published at
**[neusse.github.io/Schwab-py-NG](https://neusse.github.io/Schwab-py-NG/)**.
Start with the [getting-started
guide](https://neusse.github.io/Schwab-py-NG/getting-started.html), then use the
[client](https://neusse.github.io/Schwab-py-NG/client.html),
[streaming](https://neusse.github.io/Schwab-py-NG/streaming.html), and
[order-builder](https://neusse.github.io/Schwab-py-NG/order-builder.html)
references as needed.

Migrating an existing program from the original `schwab-py`? Read
**[Compatibility Changes](COMPATIBILITY_CHANGES.md)** before installing. It
collects the API, dependency, streaming, order, authentication, and operational
differences that may require changes in an existing program.

For the complete release-to-release history, read the
**[changelog](CHANGELOG.md)**. For the exact upstream repositories, revisions,
and integration decisions behind NG, read **[INTEGRATION.md](INTEGRATION.md)**.

---

> [!CAUTION]
>
> ## This places real orders with real money, and it has bugs
>
> Not "may have". Every defect ever found in this library was in code with 100%
> test coverage, and the ones that mattered were **silent** — a limit price a
> cent low, an option symbol naming a different contract, an order routed to a
> venue nobody asked for, an accepted order whose id was thrown away. None
> raised. None failed a test. The [changelog](CHANGELOG.md) lists them, and the
> next one is in there somewhere too, unfound.
>
> **You are responsible for every order your code places.** Not the author, not
> the maintainer, not anyone who has ever contributed. The MIT licence puts it
> in legal terms — no warranty of any kind, express or implied, and no liability
> for any claim or damages — and it means what it says: if this library loses
> you money, the loss is yours.
>
> Nothing here is financial advice and nothing here is a guarantee of
> correctness. There is no undo. A wrong order is filled before you know it was
> wrong.
>
> So: start with size you can afford to lose entirely, and stay there longer
> than feels necessary. Reconcile against the broker rather than trusting what
> this library tells you happened. Read the code on every path that places,
> replaces or cancels an order — all of it is [right
> here](https://github.com/neusse/Schwab-py-NG/tree/main/schwab). And assume the
> bug you have not found is on the path you did not read.
>
> If that is not a trade you want to make, use Schwab's own interfaces instead.
> That is a completely reasonable choice.

---

## What is `schwab`?

Charles Schwab publishes a trading API: REST endpoints for quotes, option chains,
price history, accounts and orders, plus a websocket for real-time data. It is a
capable API, and a raw one.

Raw in specific ways:

| | |
|---|---|
| **You run the OAuth flow yourself** | …against a refresh token that expires seven days after authorization, so an unattended program eventually just stops |
| **The streamer numbers its fields** | …and the same number means different things on different services. Field `2` is the ask price on `LEVELONE_EQUITIES` and the open price on `CHART_EQUITY` |
| **Order JSON is deeply nested** | …and a malformed order comes back rejected with little hint as to what was wrong |
| **Parameters are server-validated strings** | …so a typo becomes an HTTP 400 halfway through a session rather than an error where you wrote it |
| **The developer portal is behind a login** | …so there is not much to read while you work any of this out |

`schwab` is the Python layer over all of that. One method per endpoint, with the
legal parameter values as enums. An order builder that assembles Schwab's JSON from
named parts, plus ready-made templates for the orders and option strategies most
people place. A streaming client that logs in, matches responses to requests, and
relabels every message before your handler sees it. Token refresh handled and
written to disk.

Everywhere it can, it gets out of the way: you pass raw values and get back the raw
`httpx2` response, to interpret however you like. Anything you can do with
hand-rolled HTTP you can do here, with less of it.

---

## Why use it

Wrapping the tedious parts is table stakes. What follows is what `schwab` does
*differently* — and, more to the point, what each one costs you when it is missing.

| What you get | What happens without it |
|---|---|
| **Prices go out exactly as written** | A float is rounded somewhere, and your order goes in a cent low with nothing to say so |
| **A token file that survives a crash** | A process killed mid-refresh leaves a corrupt token that only a browser can repair |
| **A stream that reports what it swallowed** | A feed that died an hour ago looks exactly like a quiet market |
| **Errors that name the actual fault** | You debug the callback port when the real problem was a missing package |
| **Enums for every parameter** | A typo returns HTTP 400 from the venue instead of failing on the line you wrote |

The detail behind each:

### Prices go out exactly as written

`set_price` takes a string or a `decimal.Decimal` and **refuses a `float`**, because
a float cannot represent most prices exactly and converting one has to round
somewhere. `8.2 * 100` is `819.9999999999999`; truncate that and you have sent an
order a cent low, with nothing anywhere to say so. Making the caller decide the
rounding is the only version of this that cannot be silently wrong.

### A token file that survives a crash

Token writes go to a temporary file and are renamed into place, so a process killed
mid-refresh leaves either the old token or the new one — never a half-written file
that can only be repaired by sitting down at a browser.

`client.token_age()` tells you how long you have before Schwab's seven-day refresh
window closes, counted from the original authorization rather than the last refresh,
which is the number that actually governs expiry.

### A stream that reports what it swallowed

A websocket client has to absorb some failures: a handler that raised, a response to
a request nobody is waiting for any more, a frame that will not parse. Absorbing them
quietly makes a broken feed look like a slow one.

`add_error_handler` hands you every one of them as an exception object, so a stalled
strategy can tell the difference between a quiet market and a stream that stopped
working an hour ago.

### Errors that name the actual fault

A rejected order carries Schwab's own explanation, not just a status code. A missing
package is reported as a missing package, not as a callback server that exited. A
stream request the server accepts but never answers raises `ResponseTimeoutError`
instead of waiting forever behind a keepalive that is still cheerfully replying to
pings.

### Enums for every parameter

Every endpoint Schwab publishes has a method, and every endpoint's legal parameter
values are enums on the client — so a misspelled projection or an invalid order
duration fails immediately in Python, where you can see which line did it.

---

## Sixty seconds in

**1. Authenticate.** A browser opens, you log in, and the token is written to disk
and refreshed for you from then on.

```python
from schwab.auth import easy_client

c = easy_client(
        api_key='YOUR_API_KEY',
        app_secret='YOUR_APP_SECRET',
        callback_url='https://127.0.0.1:8182',
        token_path='/path/to/token.json')
```

**2. Ask for data.** You get back the raw `httpx2` response.

```python
r = c.get_price_history_every_day('AAPL')
r.raise_for_status()
candles = r.json()['candles']
```

**3. Place an order** from a template, without touching Schwab's order JSON.

```python
from schwab.orders.equities import equity_buy_limit
from schwab.utils import find_account_hash

account_hash = find_account_hash(c.get_account_numbers().json(), '123456789')
c.place_order(account_hash, equity_buy_limit('AAPL', 10, '210.50'))
```

The price is a string on purpose — see [Prices go out exactly as
written](#prices-go-out-exactly-as-written).

**4. Stream quotes**, with fields you can read.

```python
import asyncio
from schwab.streaming import StreamClient

async def main():
    stream = StreamClient(c)
    await stream.login()

    stream.add_level_one_equity_handler(
            lambda msg: print(msg['content'][0]['ASK_PRICE']))
    await stream.level_one_equity_subs(['AAPL', 'MSFT'])

    while True:
        await stream.handle_message()

asyncio.run(main())
```

One Schwab user can have only one streaming connection, but that connection
can carry many feeds at once. The **[many-feeds example](examples/streaming/many_feeds_one_session.py)**
subscribes one `StreamClient` to quotes, charts, books, screeners, news, and
account activity, and the **[streaming guide](https://neusse.github.io/Schwab-py-NG/streaming.html#one-session-many-feeds)**
maps every usable service to its typical use. Schwab does not implement the
inherited `TIMESALE_*` services; use level-one trade fields or chart bars
instead.

New here? The **[getting started guide](https://neusse.github.io/Schwab-py-NG/getting-started.html)** walks through
registering an app with Schwab and getting your first token.

---

## What it covers

| | |
|---|---|
| **Authentication** | Browser login, a manual flow for headless boxes and notebooks, a two-step flow for web backends, and token refresh handled for you |
| **Market data** | Quotes, fundamentals, option chains, price history from one-minute through weekly bars—including locally aggregated hourly candles—movers, market hours, instrument lookup |
| **Streaming** | Fourteen live-observed services over one websocket: level one equities, options, futures and forex; Nasdaq and NYSE order books; charts, screeners, news headlines, and your own account activity. News is an undocumented Schwab service that has delivered data in live captures and can change without notice. |
| **Orders** | Construction, placement, replacement, cancellation and preview, with templates for the common equity orders and option strategies |
| **Accounts** | Balances, positions, orders and transaction history |
| **Sync and async** | Swap `Client` for `AsyncClient`, add `await`, change nothing else |

The **[documentation](https://neusse.github.io/Schwab-py-NG/)** is worth reading even if you end up calling
the API directly. Schwab's own portal is behind a login, so for much of this API
those pages are the most accessible description of how it actually behaves.

<details>
<summary><b>What it does not do</b></summary>

<br>

A few things people ask for that Schwab's API does not offer:

- **No paper trading.** Orders placed through this API are real.
- **No historical options pricing.** Current chains only.
- **No streaming time and sales.** Schwab does not implement the inherited
  `TIMESALE_EQUITY`, `TIMESALE_OPTIONS`, or `TIMESALE_FUTURES` services. Their
  compatibility methods remain in this library, but applications should not
  call them.
- **No thinkorswim.** Schwab owns
  [thinkorswim](https://www.schwab.com/trading/thinkorswim/desktop), but this API is
  unaffiliated with it. You can trade the same accounts; some of what TOS does has no
  API equivalent.

</details>

---

## Installing

```shell
pip uninstall -y schwab-py
pip install "schwab-py-ng @ git+https://github.com/neusse/Schwab-py-NG.git"
```

The uninstall is required even when the old package appears to work:
`schwab-py` and `schwab-py-ng` both own the `schwab` import package, and
installing one over the other can leave a mixed or partially deleted module.
Python 3.10 and up, no extras to remember.

The distribution is `schwab-py-ng`; the compatible import package remains
`schwab`.

```python
import schwab
```

`schwab-py-ng` and `schwab-py` both install the `schwab` import package and
must not share an environment. Uninstall `schwab-py` before installing NG.

### Support matrix

| Component | Supported |
|---|---|
| Python | 3.10, 3.11, 3.12, 3.13, 3.14 |
| Operating systems | Windows and Linux |
| API styles | Synchronous and `asyncio` |
| Package source | GitHub (`main`) |

macOS is not a project target. It may work, but it is not part of the tested
support contract. See [INTEGRATION.md](INTEGRATION.md) for the platform decision
and the exact upstream revisions reviewed.

---

## Getting help and contributing

Contributions are welcome under the project's MIT license—no contributor
agreement is required. Use an
[issue](https://github.com/neusse/Schwab-py-NG/issues) for bugs, questions, and
feature proposals. Open an issue before a large API or behavior change so the
design can be agreed before substantial work begins. Never post credentials,
token files, account identifiers, or unreviewed logs; report security problems
[privately](https://github.com/neusse/Schwab-py-NG/security/advisories/new).

Code changes come through a fork or branch and a [pull
request](https://github.com/neusse/Schwab-py-NG/pulls). Keep one concern per
pull request, add a regression test that fails without the change, update the
user documentation when behavior changes, and let the Linux/Windows CI matrix
finish before merge. The complete setup and review expectations are in the
**[contribution guide](https://neusse.github.io/Schwab-py-NG/contributing.html)**.

## Where this came from

Schwab-py-NG preserves the history and compatible `schwab` import namespace of
[alexgolec/schwab-py](https://github.com/alexgolec/schwab-py), the original
MIT-licensed library by Alex Golec. Its hardened runtime is derived primarily
from [Hu1kSmash/schwaby](https://github.com/Hu1kSmash/schwaby) 5.2.0, including
its token, logging, streaming, order-validation, and test-suite improvements.
The focused changes in [jubishop/schwab-py](https://github.com/jubishop/schwab-py)
and [yoshishima/schwab-py](https://github.com/yoshishima/schwab-py) were also
reviewed; overlapping fixes are credited through their source histories and
summarized in [INTEGRATION.md](INTEGRATION.md).

It became a separate project for a practical reason rather than a philosophical one.
This client runs systematic strategies against funded accounts, and that use imposes
requirements a general-purpose wrapper has no particular reason to prioritise — the
guarantees under [Why use it](#why-use-it) above, most of which needed changes to
existing behaviour rather than additions on top of it.

Those changes were offered upstream first. They were not taken up, so rather than run
an ever-growing private patch set against someone else's release schedule, they were
consolidated here and this became its own project with its own release line.

## License

Schwab-py-NG is released under the [MIT license](LICENSE).

Copyright is shared: © 2023 Alex Golec for the original work, © 2026 Tom Hirt for
the changes since. Alex's notice is retained in full, as the licence requires and
as the work deserves.

**Disclaimer.** `schwab` is an unofficial API wrapper, in no way endorsed by or
affiliated with Charles Schwab or any associated organization. Read and
understand the terms of service of the underlying API before using it.

The software is provided **as is, without warranty of any kind**. The author,
the maintainer and every contributor accept no responsibility or liability for
any loss, damage, missed trade, unintended order, or any other consequence
whatsoever arising from its use — financial or otherwise, foreseeable or not.
Using it against a funded account is entirely at your own risk. See
[LICENSE](LICENSE) for the binding text, and the caution at the top of this file
for what it means in practice.
