'''Installation, dependency, token, and live-account diagnostics.'''

import argparse
import datetime
import importlib.metadata
import json
import os
import platform
import re
import stat
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx2

from . import auth
from .contrib.account import account_suffix
from .version import version as package_version


RUNTIME_REQUIREMENTS = (
    ('authlib', '1.8'),
    ('httpx2', '2.12.0'),
    ('websockets', '14.0'),
    ('flask', None),
    ('multiprocess', None),
    ('psutil', None),
    ('cryptography', None),
)


@dataclass(frozen=True)
class DoctorCheck:
    '''One diagnostic result which contains no credential characters.'''

    name: str
    status: str
    detail: str


def _environment(name):
    return os.getenv(name) or os.getenv(name.lower())


def _version_key(value):
    parts = []
    for part in re.split(r'[._+-]', value):
        match = re.match(r'\d+', part)
        if match is None:
            break
        parts.append(int(match.group()))
    return tuple(parts)


def _distribution_checks():
    installed = {}
    for name in ('schwab-py-ng', 'schwab-py'):
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    names = set(installed)
    if names == {'schwab-py-ng', 'schwab-py'}:
        distribution = DoctorCheck(
            'distribution', 'FAIL',
            'schwab-py and schwab-py-ng are both installed; uninstall '
            'schwab-py and reinstall schwab-py-ng')
    elif 'schwab-py' in names:
        distribution = DoctorCheck(
            'distribution', 'FAIL',
            'schwab-py owns the schwab import; install schwab-py-ng instead')
    else:
        distribution = DoctorCheck(
            'distribution', 'PASS', 'schwab-py-ng {}'.format(
                installed.get('schwab-py-ng', package_version)))
    return (
        distribution,
        DoctorCheck('schwab import', 'PASS', str(Path(__file__).parent)),
    )


def _runtime_checks():
    checks = []
    for name, minimum in RUNTIME_REQUIREMENTS:
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            checks.append(DoctorCheck(
                'package {}'.format(name), 'FAIL', 'not installed'))
            continue
        if minimum is not None and _version_key(installed) < _version_key(minimum):
            checks.append(DoctorCheck(
                'package {}'.format(name), 'FAIL',
                '{} installed; NG requires >= {}'.format(installed, minimum)))
        else:
            requirement = ' (required >= {})'.format(minimum) if minimum else ''
            checks.append(DoctorCheck(
                'package {}'.format(name), 'PASS', installed + requirement))
    return tuple(checks)


def _format_timestamp(value):
    try:
        return datetime.datetime.fromtimestamp(
            float(value), datetime.timezone.utc).isoformat()
    except (OSError, OverflowError, TypeError, ValueError):
        return 'invalid timestamp'


def _token_checks(token_path):
    if token_path in (None, ''):
        return (DoctorCheck(
            'token file', 'WARN',
            'no token path supplied; use --token-path or SCHWAB_TOKEN_PATH'),)
    path = Path(token_path).expanduser()
    if not path.is_file():
        return (DoctorCheck('token file', 'FAIL',
                            '{} is not a readable file'.format(path)),)
    try:
        with path.open(encoding='utf-8') as token_file:
            data = json.load(token_file)
        age = auth.token_file_age(path)
        token = data['token']
        if not isinstance(token, dict):
            raise ValueError('token must be an object')
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return (DoctorCheck(
            'token file', 'FAIL',
            'token file cannot be read as an NG token; contents were not '
            'displayed'),)

    checks = [DoctorCheck('token file', 'PASS', str(path))]
    created = data.get('creation_timestamp')
    if created is not None:
        checks.append(DoctorCheck(
            'token created', 'PASS', _format_timestamp(created)))
    days = age / (24 * 60 * 60)
    status = 'FAIL' if days >= 7 else 'WARN' if days >= 6.5 else 'PASS'
    expiry = (_format_timestamp(float(created) + 7 * 86400)
              if created is not None else 'unknown')
    checks.append(DoctorCheck(
        'refresh token age', status,
        '{:.2f} days; estimated seven-day expiry {}'.format(days, expiry)))

    expires_at = token.get('expires_at')
    if expires_at is not None:
        remaining = float(expires_at) - time.time()
        checks.append(DoctorCheck(
            'access token', 'WARN' if remaining <= 0 else 'PASS',
            'expires {}; {} seconds remaining'.format(
                _format_timestamp(expires_at), int(remaining))))
    token_type = token.get('token_type')
    scope = token.get('scope')
    if token_type or scope:
        checks.append(DoctorCheck(
            'token metadata', 'PASS', 'type={}; scope={}'.format(
                token_type or 'unknown', scope or 'unknown')))
    writable = os.access(path, os.W_OK)
    checks.append(DoctorCheck(
        'token writable', 'PASS' if writable else 'WARN',
        'token refresh can update this file' if writable
        else 'token file is not writable'))

    if os.name == 'posix':
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
            exposed = mode & (stat.S_IRWXG | stat.S_IRWXO)
            checks.append(DoctorCheck(
                'token permissions', 'WARN' if exposed else 'PASS',
                ('token file is accessible outside its owner'
                 if exposed else 'token file is owner-only')))
        except OSError:
            checks.append(DoctorCheck(
                'token permissions', 'WARN',
                'token file permissions could not be inspected'))
    return tuple(checks)


def _credential_check(token_path, api_key, app_secret):
    present = []
    missing = []
    for name, value in (
            ('SCHWAB_TOKEN_PATH', token_path),
            ('SCHWAB_API_KEY', api_key),
            ('SCHWAB_APP_SECRET', app_secret)):
        (present if value else missing).append(name)
    detail = 'present: {}'.format(', '.join(present) or 'none')
    if missing:
        detail += '; missing: {}'.format(', '.join(missing))
    return DoctorCheck(
        'environment', 'WARN' if missing else 'PASS', detail)


def _latest_version(name, timeout):
    response = httpx2.get(
        'https://pypi.org/pypi/{}/json'.format(name), timeout=timeout)
    response.raise_for_status()
    return response.json()['info']['version']


def _update_checks(timeout):
    checks = []
    names = ('schwab-py-ng',) + tuple(
        name for name, _ in RUNTIME_REQUIREMENTS)
    for name in names:
        try:
            installed = importlib.metadata.version(name)
            latest = _latest_version(name, timeout)
        except Exception as exc:
            checks.append(DoctorCheck(
                'update {}'.format(name), 'WARN',
                '{} while checking PyPI; details suppressed'.format(
                    type(exc).__name__)))
            continue
        checks.append(DoctorCheck(
            'update {}'.format(name),
            'WARN' if _version_key(latest) > _version_key(installed) else 'PASS',
            'installed {}; latest {}'.format(installed, latest)))
    return tuple(checks)


def _quote_price(body, symbol):
    quote = body.get(symbol, {}) if isinstance(body, dict) else {}
    for section, field in (
            ('quote', 'lastPrice'),
            ('regular', 'regularMarketLastPrice')):
        value = quote.get(section, {}).get(field)
        if value is not None:
            return value
    return quote.get('lastPrice')


def _live_checks(token_path, api_key, app_secret, symbol):
    path = Path(token_path)
    try:
        before = path.stat().st_mtime_ns
    except OSError:
        before = None
    try:
        client = auth.client_from_token_file(token_path, api_key, app_secret)
        started = time.perf_counter()
        quote_response = client.get_quote(symbol)
        quote_response.raise_for_status()
        latency_ms = (time.perf_counter() - started) * 1000
        price = _quote_price(quote_response.json(), symbol)
        detail = '{} quote succeeded in {:.0f} ms'.format(symbol, latency_ms)
        if price is not None:
            detail += '; last price {}'.format(price)
        quote_check = DoctorCheck('quote connectivity', 'PASS', detail)

        accounts_response = client.get_account_numbers()
        accounts_response.raise_for_status()
        accounts = accounts_response.json()
        suffixes = sorted(account_suffix(item.get('accountNumber'))
                          for item in accounts)
        account_check = DoctorCheck(
            'linked accounts', 'PASS', '{} account(s): {}'.format(
                len(accounts), ', '.join('...{}'.format(value)
                                         for value in suffixes if value)))
    except Exception as exc:
        response = getattr(exc, 'response', None)
        status = getattr(response, 'status_code', None)
        detail = type(exc).__name__
        if status is not None:
            detail += ' HTTP {}'.format(status)
        detail += '; sensitive details suppressed'
        return (DoctorCheck('live connectivity', 'FAIL', detail),)

    try:
        after = path.stat().st_mtime_ns
    except OSError:
        after = None
    refresh_check = DoctorCheck(
        'token persistence', 'PASS',
        'token file was refreshed during live checks'
        if before != after else 'token file was not rewritten')
    return quote_check, account_check, refresh_check


def run_checks(*, token_path=None, connect=None, api_key=None,
               app_secret=None, symbol='AAPL', check_updates=False,
               timeout=10):
    '''Run diagnostics and return sanitized :class:`DoctorCheck` values.

    Live quote and linked-account checks run by default when all three Schwab
    environment values are present. Set ``connect=False`` for offline-only
    diagnostics. A live check may refresh and rewrite the caller's token file.
    '''
    token_path = token_path or _environment('SCHWAB_TOKEN_PATH')
    api_key = api_key or _environment('SCHWAB_API_KEY')
    app_secret = app_secret or _environment('SCHWAB_APP_SECRET')
    local = datetime.datetime.now().astimezone()
    results = [
        DoctorCheck('python', 'PASS', '{}.{}.{} at {}'.format(
            *sys.version_info[:3], sys.executable)),
        DoctorCheck('platform', 'PASS', '{} {}; {}'.format(
            platform.system(), platform.machine(), platform.platform())),
        DoctorCheck('local timezone', 'PASS', '{} ({})'.format(
            local.tzname(), local.strftime('%z'))),
    ]
    results.extend(_distribution_checks())
    results.extend(_runtime_checks())
    results.append(_credential_check(token_path, api_key, app_secret))
    results.extend(_token_checks(token_path))
    if check_updates:
        results.extend(_update_checks(timeout))

    ready = bool(token_path and api_key and app_secret)
    if connect is None:
        connect = ready
    if connect and ready:
        results.extend(_live_checks(token_path, api_key, app_secret, symbol))
    elif connect:
        results.append(DoctorCheck(
            'live connectivity', 'FAIL',
            'token path, API key, and app secret are required'))
    else:
        results.append(DoctorCheck(
            'live connectivity', 'SKIP', 'offline mode requested'))
    return tuple(results)


def configure_parser(parser):
    '''Add Doctor command-line arguments to an ``argparse`` parser.'''
    parser.add_argument('--token-path')
    live = parser.add_mutually_exclusive_group()
    live.add_argument('--offline', action='store_true',
                      help='skip quote and linked-account checks')
    live.add_argument('--connect', action='store_true',
                      help='require live checks even when credentials are missing')
    parser.add_argument('--symbol', default='AAPL',
                        help='quote symbol used for live checks (default: AAPL)')
    parser.add_argument('--check-updates', action='store_true',
                        help='compare runtime packages with current PyPI releases')
    parser.add_argument('--timeout', type=float, default=10,
                        help='PyPI request timeout in seconds (default: 10)')
    parser.add_argument('--json', action='store_true',
                        help='emit machine-readable JSON')
    return parser


def run_cli(args):
    '''Run Doctor from parsed arguments and return its process exit status.'''
    connect = False if args.offline else True if args.connect else None
    checks = run_checks(
        token_path=args.token_path, connect=connect, symbol=args.symbol,
        check_updates=args.check_updates, timeout=args.timeout)
    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        for check in checks:
            print('[{}] {}: {}'.format(check.status, check.name, check.detail))
    return 1 if any(check.status == 'FAIL' for check in checks) else 0


def main(argv=None):
    '''Run the ``schwab-ng-doctor`` command and return its exit status.'''
    parser = configure_parser(argparse.ArgumentParser(
        prog='schwab-ng-doctor',
        description='Diagnose a Schwab-py-NG installation and live access.'))
    return run_cli(parser.parse_args(argv))
