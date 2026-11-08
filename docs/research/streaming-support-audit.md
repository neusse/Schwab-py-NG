# Schwab streaming service support audit

**Research date:** 2026-11-08  
**Scope:** Services named in the current Schwab Streamer API service table and feeds currently documented or exposed by Schwab-py-NG. This audits service existence and evidence that data is delivered; it does not guarantee entitlement for every Schwab account or symbol.

## Summary

Schwab's service table defines futures streams, and Schwab-py-NG has first-hand live-account observations for `LEVELONE_FUTURES` (as well as futures options and forex level-one feeds). Thus, “Schwab has no futures streaming” is too broad. Although NG's earlier `VIEW` experiment did not receive a `CHART_FUTURES` payload during its measurement window, an independent December 2025 live capture contains populated `CHART_FUTURES` OHLCV data. The absence of a frame in one bounded experiment is not evidence that the service is unavailable.

`NEWS_HEADLINE` has produced live headline payloads but is absent from Schwab's published service table; treat it as undocumented and liable to change. The `TIMESALE_*` names are inherited compatibility methods and are absent from that table; an equity time-and-sales request has returned an unavailable-service response. Three additional book names found in older material (`FOREX_BOOK`, `FUTURES_BOOK`, `FUTURES_OPTIONS_BOOK`) are not in the current thirteen-service table and this library has no subscriptions for them.

The separate live-service summary in `docs/streaming.rst` should distinguish populated payloads from acknowledgements, and should identify the three extra book names as inherited from older predecessor material rather than part of Schwab's current thirteen-service table.

## Service-by-service evidence

“Listed” means present in the Schwab Market Data Production Streamer service table. “Observed” means the NG documentation/history records actual live-account frames or a measured server response. Mock websocket tests verify request construction and dispatch behavior; they do not establish Schwab-side availability.

| Service | Schwab table | NG live evidence | Assessment |
| --- | --- | --- | --- |
| `LEVELONE_EQUITIES` | Listed | Included in the project's confirmed Level One streams; documented with live quote behavior | Documented and confirmed working, subject to market-data entitlement |
| `LEVELONE_OPTIONS` | Listed | Included in the project's confirmed Level One streams; documented with live quote behavior | Documented and confirmed working, subject to symbol/entitlement |
| `LEVELONE_FUTURES` | Listed | Live test measured field `VIEW` affecting multiple futures symbols and received frames | Documented and live-observed. Futures quote streaming exists; that does not imply futures order entry or futures-chart support |
| `LEVELONE_FUTURES_OPTIONS` | Listed | Live test measured a `VIEW` field taking effect on the futures-options service | Documented and live-observed, with contract/entitlement dependence |
| `LEVELONE_FOREX` | Listed | Live test measured field `VIEW` affecting multiple currency pairs and received frames | Documented and live-observed, with entitlement dependence |
| `NYSE_BOOK` | Listed | Included in confirmed Level Two streams; live book captures are documented | Documented and confirmed working, subject to available symbol/entitlement |
| `NASDAQ_BOOK` | Listed | Included in confirmed Level Two streams; live book captures are documented | Documented and confirmed working, subject to available symbol/entitlement |
| `OPTIONS_BOOK` | Listed | NG docs say the feed was tested to deliver data; a later capture did not include per-exchange entries | Listed and observed working, but do not promise per-exchange breakdowns; exact depth/entitlement behavior remains limited |
| `CHART_EQUITY` | Listed | Included in confirmed chart streams; live minute bars are documented | Documented and confirmed working |
| `CHART_FUTURES` | Listed | NG's bounded VIEW experiment received no frame, but an independent December 2025 live capture contains a populated `/ES` minute OHLCV payload | Documented and live-observed; keep in runnable examples, subject to instrument, market-hours, and entitlement caveats |
| `SCREENER_EQUITY` | Listed | Extensive live measurements documented, including cadence and rejection behavior | Documented and confirmed working |
| `SCREENER_OPTION` | Listed | Extensive live measurements documented, including cadence and rejection behavior | Documented and confirmed working |
| `ACCT_ACTIVITY` | Listed | Long-running live observation and payload examples documented | Documented and confirmed working, but many message-body details remain reverse-engineered rather than contractual |
| `NEWS_HEADLINE` | **Not listed** | Live `SUBS` returned success and delivered headlines; observations are recorded in NG docs and changelog | Live-observed, undocumented. Keep a prominent caveat; do not call it an officially supported Schwab service |
| `TIMESALE_EQUITY` | **Not listed** | A reported live request received an unavailable-service response; NG preserves only compatibility request/decoding behavior | Unsupported. No live trades should be expected |
| `TIMESALE_OPTIONS` | **Not listed** | No NG live payload evidence; service absent from Schwab's table | Unsupported compatibility surface; not independently tested live |
| `TIMESALE_FUTURES` | **Not listed** | No NG live payload evidence; service absent from Schwab's table | Unsupported compatibility surface; not independently tested live |
| `FOREX_BOOK` | Not in current table | NG docs report unavailable-service refusals when attempted; no NG public subscription method | Unavailable/unsupported; no client feed API |
| `FUTURES_BOOK` | Not in current table | NG docs report unavailable-service refusals when attempted; no NG public subscription method | Unavailable/unsupported; no client feed API |
| `FUTURES_OPTIONS_BOOK` | Not in current table | NG docs report unavailable-service refusals when attempted; no NG public subscription method | Unavailable/unsupported; no client feed API |

Schwab's table is a service definition, not proof that each stream is currently active, entitled, or returning data. Likewise, a `code: 0` acknowledgement alone is not proof of a usable feed; the project's live screener audit includes malformed keys that received success and then delivered no frames.

## Evidence and sources

### Schwab-owned source

- [Schwab Developer Portal — Trader API Individual, Market Data Production documentation](https://developer.schwab.com/products/trader-api--individual/details/documentation/Market%20Data%20Production). The portal page is JavaScript/login gated to anonymous retrieval, so the browser/search tool returned no readable body during this audit.

### Portal documentation transcription

- [Saved transcription of Schwab's Streamer API document](https://github.com/pashpashpash/schwab-cli/blob/main/docs/schwab-api/streamer.md). The file identifies its source as `market-data-production-docs.html` saved from the Schwab portal and states it is a cleaned transcript. Its thirteen-service table includes the five level-one services, `NYSE_BOOK`, `NASDAQ_BOOK`, `OPTIONS_BOOK`, both chart services, both screeners, and `ACCT_ACTIVITY`; it does not include news, time-and-sales, or futures/forex book feeds. This is a source-derived copy, not a Schwab-hosted URL, so use the portal link above as the authority and the transcript for inspectable service names/fields.

### Independent populated Schwab payload captures

- [Schwabdev streaming guide and captured payloads](https://github.com/tylerebowers/Schwabdev/blob/main/docs/pages-raw/stream.md) publishes actual Schwab websocket data examples for every service in the current thirteen-service table. The December 2025 captures include populated `LEVELONE_FUTURES`, `LEVELONE_FUTURES_OPTIONS`, `LEVELONE_FOREX`, and `CHART_FUTURES` responses, as well as equities, options, all three implemented books, both screeners, both chart feeds, and account activity. The file history records the capture/documentation work in December 2025, including [commit `1324c3394d80`](https://github.com/tylerebowers/Schwabdev/commit/1324c3394d800538165f33e7401326f9142f2934) and follow-up streamer documentation commits.
- The `CHART_FUTURES` example contains an on-wire Schwab payload for `/ES` with chart time, open, high, low, close, volume, and sequence fields. This outweighs the earlier NG `VIEW` experiment's failure to receive a frame during its limited observation window.

### Upstream maintainer documentation

- [Alex Golec's schwab-py streaming guide — Stream Statuses](https://schwab-py.readthedocs.io/en/latest/streaming.html#stream-statuses) says carried-over stream methods may not work and identifies charts, level one, level two, screeners, and account activity as confirmed categories. It is useful corroboration, but does not independently establish each individual service's current status.

### Schwab-py-NG first-hand records

- [`docs/streaming.rst`](../streaming.rst): lines/sections “Stream Statuses,” “Changing the fields of a live subscription,” the individual feed guides, the `NEWS_HEADLINE` caveat, and the unsupported time-and-sales page. The live VIEW section says it measured futures, futures options, and forex data, while explicitly stating `CHART_FUTURES` delivered nothing to measure.
- [`CHANGELOG.md`](../../CHANGELOG.md): version 4.8.0 records `NEWS_HEADLINE` as a live-observed undocumented service and the live `VIEW` findings; version 5.0.0 records `OPTIONS_BOOK`'s lack of per-exchange entries in that capture.
- [`schwab/streaming.py`](../../schwab/streaming.py): `_KNOWN_SERVICES` lists the implemented feeds plus the three compatibility-only `TIMESALE_*` names. There are no handler APIs for the additional `*_BOOK` services.
- [`tests/streaming_test.py`](../../tests/streaming_test.py): local protocol tests use fixtures/mock websocket responses. These establish client behavior only; they are not evidence that Schwab's production streamer provides a service.

## Documentation recommendation

1. Keep `LEVELONE_FUTURES`, `LEVELONE_FUTURES_OPTIONS`, and `LEVELONE_FOREX` documented as observed quote services, with a sentence clarifying that the service names do not promise trading support and availability depends on the user's Schwab entitlements.
2. Keep `CHART_FUTURES` in the live-observed set and runnable example, citing the independent populated payload. State that a quiet bounded test does not establish unavailability and that delivery still depends on a valid instrument, market activity, and entitlement.
3. Correct the current guide's assertion that Schwab's current table lists `FOREX_BOOK`, `FUTURES_BOOK`, and `FUTURES_OPTIONS_BOOK`; the inspectable Schwab-derived thirteen-service table does not list them.
4. Continue to label `NEWS_HEADLINE` live-observed but undocumented, and all `TIMESALE_*` methods compatibility-only/unsupported.
5. Describe any feed as confirmed only when a live `SUBS` is followed by useful production data for a valid symbol, not solely because the SDK accepts the call, mock tests pass, or Schwab replies with an acknowledgement.
