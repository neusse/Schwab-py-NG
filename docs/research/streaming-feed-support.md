# Schwab streaming feed support: documented versus observed

**Reviewed:** 2026-11-07  
**Scope:** `NEWS_HEADLINE`, `TIMESALE_EQUITY`, `TIMESALE_OPTIONS`,
`TIMESALE_FUTURES`, and other reported unavailable services.

## Summary

Schwab's streamer service table, as reproduced from a saved copy of the
Schwab developer portal, lists thirteen services. It does not list
`NEWS_HEADLINE` or any `TIMESALE_*` service. The public Schwab developer portal
page was reachable during this review, but returned no readable documentation
text to the research client. The service table and response-code details below
therefore rely on a third-party transcript whose file identifies its source as
the saved Schwab portal file `market-data-production-docs.html`.

The evidence does **not** support calling news and time-and-sales equally
unsupported:

- `NEWS_HEADLINE` is undocumented, but Schwab returned a successful subscribe
  response and actual headline messages in a live account capture recorded by
  this project. An upstream maintainer had said in August 2024 that news did
  not appear to be available, so availability may have changed or may vary.
- `TIMESALE_EQUITY` is absent from the Schwab service table. A first-hand
  field report records `code=11` (“service not available”) in two attempts,
  one at 2 a.m. ET and one around 9 a.m. ET during pre-market on 2026-03-10.
  It did not record a regular-session test. This is meaningful evidence of
  unavailability in those attempts, not proof that it can never work.
- No live Schwab result was found for `TIMESALE_OPTIONS` or
  `TIMESALE_FUTURES`. Their behavior must remain **unknown**; the equity result
  should not be generalized to them.

For the public support policy, the project classifies all three `TIMESALE_*`
names as **unsupported and not implemented by Schwab**. This deliberately
conservative classification reflects their absence from Schwab's service list,
the explicit equity rejection, the reported support response, and the lack of
any populated Schwab frame. The narrower evidence distinctions remain below so
that the policy is not mistaken for three independently captured rejections.

## Keep three evidence levels separate

1. **Documented service:** the service name appears in Schwab's service table.
2. **Accepted request:** the server acknowledges a request. In the captured
   reference, response code `0` means success; code `11` means the service is
   unavailable, either because it is unsupported or because it is not running
   from the source.
3. **Populated feed:** a subsequent `data` response contains actual items.

An accepted `SUBS` is not proof that the feed populated. The reference defines
request responses and streaming `data` messages separately. See the
[transcribed response format and response codes](https://github.com/pashpashpash/schwab-cli/blob/main/docs/schwab-api/streamer.md)
and the [saved portal transcript's service table](https://github.com/pashpashpash/schwab-cli/blob/main/docs/schwab-api/streamer.md).

## Findings by feed

| Feed | In Schwab's 13-service table? | Live request evidence found | Data evidence found | Assessment |
| --- | --- | --- | --- | --- |
| `NEWS_HEADLINE` | No | The project guide records `code: 0` for a subscription; it separately reports that both `SUBS` and `ADD` immediately delivered an item per symbol. | The guide records 416 items with 191 distinct identifiers across 30 widely held symbols in an 80-minute capture; it also notes an initial historical burst on subscription. | **Undocumented, but observed populated.** Do not describe it as an officially supported Schwab service or rely on it as the only news source. |
| `TIMESALE_EQUITY` | No | A 2024 report of the author's Schwab-support exchange said the service was not in the development plan; the author's attempt returned “Service not available or temporary down.” A separate 2026 field report records `code=11` at 2 a.m. ET and around 9 a.m. ET. | The two 2026 attempts produced no frame; the 2024 report also describes a failed request. | **Strong evidence it was not exposed in the reported attempts; current and regular-session availability is still unconfirmed.** |
| `TIMESALE_OPTIONS` | No | No live Schwab acknowledgement or rejection found. | No live Schwab data found. | **Unknown.** The wire request and field schema in this project are inherited and tested with mocks, not live Schwab traffic. |
| `TIMESALE_FUTURES` | No | No live Schwab acknowledgement or rejection found. | No live Schwab data found. | **Unknown.** Do not infer support from the equity service or predecessor API. |
| `FOREX_BOOK`, `FUTURES_BOOK`, `FUTURES_OPTIONS_BOOK` | No | The upstream library's streaming guide says experiments with these services refused to connect, typically with unavailable-service errors. | No populated Schwab data was reported there. | **Reported unavailable by upstream experiments.** The guide does not include raw response captures or test dates, so confidence is moderate. |

The project guide itself distinguishes the time-and-sales implementation from
live support: request construction and decoding are tested, but it says this
project has not captured a live Schwab time-and-sales frame. Its feed overview
currently lists those services under “supported feeds,” so that heading should
not be read as evidence of confirmed server support. See the
[time-and-sales caveat and feed overview](https://github.com/neusse/Schwab-py-NG/blob/main/docs/streaming.rst#L136-L158)
and the [live-capture caveat](https://github.com/neusse/Schwab-py-NG/blob/main/docs/streaming.rst#L734-L770).

## Evidence and confidence

### Schwab's service table and response codes

The [Schwab Developer Portal's Market Data Production documentation](https://developer.schwab.com/products/trader-api--individual/details/documentation/Market%20Data%20Production)
is the official endpoint. It rendered no readable lines in this review, so the
service list was checked against a
[GitHub transcript of the saved portal HTML](https://github.com/pashpashpash/schwab-cli/blob/main/docs/schwab-api/streamer.md).
That file names `market-data-production-docs.html` as its source and lists
these thirteen services: `LEVELONE_EQUITIES`, `LEVELONE_OPTIONS`,
`LEVELONE_FUTURES`, `LEVELONE_FUTURES_OPTIONS`, `LEVELONE_FOREX`, `NYSE_BOOK`,
`NASDAQ_BOOK`, `OPTIONS_BOOK`, `CHART_EQUITY`, `CHART_FUTURES`,
`SCREENER_EQUITY`, `SCREENER_OPTION`, and `ACCT_ACTIVITY`. Neither news nor
time-and-sales appears. Its response table defines `0 SUCCESS` and says
`11 SERVICE_NOT_AVAILABLE` can mean either an unsupported service or a service
not running from the source.

**Confidence:** Moderate for what the captured service table says; low for
claims about undocumented services being impossible. The transcript is
third-party hosted rather than a directly accessible Schwab page, and the
portal did not expose its text during this review.

### `NEWS_HEADLINE`

The project guide records the service as absent from Schwab's thirteen-service
list, but says a live account returned `code: 0` for a subscription and
delivered headlines. It reports 416 items, 191 distinct identifiers, 30
symbols, and 80 minutes in one morning. The project changelog documented this
finding by 2026-09-17, but the guide does not state the capture's calendar date;
the raw capture is not checked into the repository. These are the project's
documented first-hand measurements, not an independently repeated test. See
the [project's measured service notes](https://github.com/neusse/Schwab-py-NG/blob/main/docs/streaming.rst#L1353-L1408)
and its [2026-09-17 changelog entry](https://github.com/neusse/Schwab-py-NG/blob/main/CHANGELOG.md#L445-L458).

There is conflicting earlier evidence: in
[upstream issue #169](https://github.com/alexgolec/schwab-py/issues/169), opened
2024-07-25, maintainer Alex Golec commented on 2024-08-10 that the stream was
“not available in the Schwab API, as best as we can tell.” This was a
maintainer's investigation, not a statement from Schwab. The project
measurement documented by 2026-09-17 is evidence that the undocumented service can deliver headlines under
at least one account/session configuration; it does not establish a service
guarantee or explain the difference from the 2024 result.

**Confidence:** Moderate that the service populated in the account and period
recorded by this project; low that its current availability is universal or
stable.

### `TIMESALE_*`

The first-hand field report in
[`davidsvaughn/alpaca-news`'s tick collector notes](https://github.com/davidsvaughn/alpaca-news/blob/trader/docs/TICK-COLLECTOR.md#phase-1-findings-2026-03-10-pre-market-9-am-et)
records `TIMESALE_EQUITY` returning `code=11` both at 2 a.m. ET and at roughly
9 a.m. ET pre-market on 2026-03-10. Its issue summary says no time-and-sales
frames arrived during either attempt. This is a direct user-reported live
observation, but the public note is a summary rather than a raw WebSocket
transcript, and it does not report an in-session regular-hours test.

Earlier corroboration appears in
[upstream issue #115](https://github.com/alexgolec/schwab-py/issues/115),
opened 2024-05-31. The reporter says Schwab told them that a “Timesale” or
“Trade” stream was not in the development plan, and reports their own
`TIMESALE_EQUITY` attempt returned “Service not available or temporary down.”
On 2024-06-03, Alex Golec said he was waiting for the official streaming
documentation before making major streaming changes. This is a user's summary
of a Schwab support exchange, not a published Schwab statement or a raw
response capture, but it is stronger corroboration than an issue request alone.

There is also a mismatch in inherited library material. The
[upstream `schwab-py` guide](https://schwab-py.readthedocs.io/en/stable/streaming.html)
opens with a claim that time-of-sale data is provided, but its confirmed-working
list omits all time-and-sales services and the same guide warns that copied
services may not work. The open
[upstream issue #215](https://github.com/alexgolec/schwab-py/issues/215), opened
2025-11-24, asks for streaming live trades; that request indicates user demand,
not proof of feed availability or unavailability.

This project's
[time-and-sales documentation](https://github.com/neusse/Schwab-py-NG/blob/main/docs/streaming.rst#L734-L770)
states that it has not captured a live Schwab frame. Its tests establish the
client's request formatting, response handling, and relabeling using synthetic
responses; they do not establish that Schwab accepts or populates the services.

**Confidence:** Moderate-to-high that `TIMESALE_EQUITY` was unavailable in the
reported attempts and not planned as of the 2024 support exchange; low on
whether it is unavailable during regular hours or for every user today. **No
evidence found** to classify `TIMESALE_OPTIONS` or `TIMESALE_FUTURES` beyond
their absence from the captured service list.

### Other reported unavailable services

The
[upstream guide's Level Two section](https://schwab-py.readthedocs.io/en/stable/streaming.html#level-two-order-book)
says `FOREX_BOOK`, `FUTURES_BOOK`, and `FUTURES_OPTIONS_BOOK` are listed in
older/reference documentation but experiments refused to connect, typically
with unavailable-service errors. It concludes those services are not
implemented. The current project guide repeats that report and excludes them
from its API. The report has no raw responses or dates, so it should be treated
as a useful prior rather than an independent current retest. This does not
apply to the documented `NYSE_BOOK`, `NASDAQ_BOOK`, or `OPTIONS_BOOK` services.

**Confidence:** Moderate that the upstream experiments observed refusals;
low-to-moderate that the services remain unavailable for all accounts today.

## Project documentation decision

- Describe `NEWS_HEADLINE` as **undocumented and observed to deliver headlines**,
  with the account/session and stability caveats above. Do not call it dead.
- Describe all three `TIMESALE_*` names as **unsupported and not implemented by
  Schwab**. Retained client methods are predecessor compatibility stubs, not
  usable feeds, and must not appear in runnable examples or supported-feed
  counts.
- Preserve the evidence distinction in research material: only equity has a
  recorded rejection, while options and futures have no independently captured
  result. A future successful subscription plus populated data frames would be
  grounds to revisit the policy; an acknowledgement alone would not be enough.
- Distinguish a server rejection (`code=11`) from an accepted-but-empty
  subscription, and distinguish both from a populated feed in documentation
  and issue reports.
