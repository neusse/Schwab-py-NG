# Integration provenance

Schwab-py-NG preserves Alex Golec's original Git history and MIT license while
combining the strongest maintained fixes reviewed on 2026-11-02.

| Source | Reviewed tip | Integration decision |
| --- | --- | --- |
| `alexgolec/schwab-py` | `43c4614` | Git-history base, `schwab` import compatibility, and original attribution |
| `Hu1kSmash/schwaby` | `970a0b6` (5.2.0) | Primary hardened runtime and regression suite |
| `jubishop/schwab-py` | `4d6c9d1` | Its Authlib 1.8/httpx2 migration is already present in the hardened runtime |
| `yoshishima/schwab-py` | `5ec39c5` | Reviewed for token, streaming, order, and callback fixes; overlapping Windows/Linux fixes are already represented |

The NG distribution is named `schwab-py-ng`, but it deliberately installs the
`schwab` Python package so existing applications can migrate without changing
imports. It therefore cannot coexist in one environment with `schwab-py`.

macOS-specific callback-server changes from the Yoshishima fork are outside
this project's supported scope. Windows and Linux are the target platforms.

The historical `schwaby` changelog is retained verbatim below an NG provenance
notice so contributor credit and release rationale are not rewritten.
