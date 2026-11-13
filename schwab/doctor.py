'''Safe installation, token-file, and optional connectivity diagnostics.'''

import argparse
import importlib.metadata
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from . import auth
from .version import version as package_version


@dataclass(frozen=True)
class DoctorCheck:
    '''One sanitized diagnostic result.'''

    name: str
    status: str
    detail: str


def _environment(name):
    return os.getenv(name) or os.getenv(name.lower())


def _distribution_check():
    installed = []
    for name in ('schwab-py-ng', 'schwab-py'):
        try:
            installed.append((name, importlib.metadata.version(name)))
        except importlib.metadata.PackageNotFoundError:
            pass
    names = {name for name, _ in installed}
    if names == {'schwab-py-ng', 'schwab-py'}:
        return DoctorCheck(
            'distribution', 'FAIL',
            'schwab-py and schwab-py-ng are both installed; uninstall '
            'schwab-py and reinstall schwab-py-ng')
    if 'schwab-py' in names:
        return DoctorCheck(
            'distribution', 'FAIL',
            'schwab-py owns the schwab import; install schwab-py-ng instead')
    detail = 'schwab-py-ng {}'.format(dict(installed).get(
        'schwab-py-ng', package_version))
    return DoctorCheck('distribution', 'PASS', detail)


def _token_checks(token_path):
    if token_path in (None, ''):
        return (DoctorCheck(
            'token file', 'WARN',
            'no token path supplied; use --token-path or SCHWAB_TOKEN_PATH'),)
    path = Path(token_path).expanduser()
    if not path.is_file():
        return (DoctorCheck('token file', 'FAIL',
                            'token path does not name a readable file'),)
    checks = []
    try:
        age = auth.token_file_age(path)
    except (OSError, ValueError):
        return (DoctorCheck(
            'token file', 'FAIL',
            'token file cannot be read as an NG token; contents were not '
            'displayed'),)
    days = age / (24 * 60 * 60)
    status = 'FAIL' if days >= 7 else 'WARN' if days >= 6.5 else 'PASS'
    detail = 'refresh token age is {:.2f} days'.format(days)
    checks.append(DoctorCheck('token age', status, detail))

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


def run_checks(*, token_path=None, connect=False, api_key=None,
               app_secret=None, symbol='AAPL'):
    '''Run sanitized diagnostics and return :class:`DoctorCheck` values.

    Connectivity is opt-in because it may refresh and rewrite the token file.
    No access-token, refresh-token, app-secret, API-key, account identifier, or
    response body is included in a result.
    '''
    results = [DoctorCheck(
        'python', 'PASS', '{}.{}.{}'.format(*sys.version_info[:3])),
        _distribution_check(),
    ]
    token_path = token_path or _environment('SCHWAB_TOKEN_PATH')
    results.extend(_token_checks(token_path))

    if connect:
        api_key = api_key or _environment('SCHWAB_API_KEY')
        app_secret = app_secret or _environment('SCHWAB_APP_SECRET')
        if not (token_path and api_key and app_secret):
            results.append(DoctorCheck(
                'connectivity', 'FAIL',
                'connectivity requires token path, API key, and app secret'))
        else:
            try:
                client = auth.client_from_token_file(
                    token_path, api_key, app_secret)
                response = client.get_quote(symbol)
                response.raise_for_status()
            except Exception as exc:
                results.append(DoctorCheck(
                    'connectivity', 'FAIL',
                    '{} during quote check; sensitive details suppressed'.format(
                        type(exc).__name__)))
            else:
                results.append(DoctorCheck(
                    'connectivity', 'PASS',
                    'authenticated quote request succeeded'))
    else:
        results.append(DoctorCheck(
            'connectivity', 'SKIP', 'use --connect to make a quote request'))
    return tuple(results)


def main(argv=None):
    '''Run the ``schwab-ng-doctor`` command and return its exit status.'''
    parser = argparse.ArgumentParser(
        prog='schwab-ng-doctor',
        description='Safely diagnose a Schwab-py-NG installation and token.')
    parser.add_argument('--token-path')
    parser.add_argument('--connect', action='store_true',
                        help=('make a harmless quote request using '
                              'SCHWAB_API_KEY and SCHWAB_APP_SECRET'))
    parser.add_argument('--symbol', default='AAPL',
                        help='quote symbol used with --connect (default: AAPL)')
    args = parser.parse_args(argv)
    checks = run_checks(
        token_path=args.token_path,
        connect=args.connect,
        symbol=args.symbol)
    for check in checks:
        print('[{}] {}: {}'.format(check.status, check.name, check.detail))
    return 1 if any(check.status == 'FAIL' for check in checks) else 0
