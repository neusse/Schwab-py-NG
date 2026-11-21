## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `neusse/Schwab-py-NG`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five default triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repository uses the single-context domain-doc layout. See `docs/agents/domain.md`.

### HTTP transport tests

New or changed HTTP client behavior must reuse `MockSchwab` from
`tests/http_transport.py`. Cover sync and async clients when both expose the
behavior, and assert the method, URL, headers, serialized body, and relevant
response or error handling. Never contact Schwab from tests. Pure order-builder
logic should continue to use ordinary unit tests and does not need a transport
test.
