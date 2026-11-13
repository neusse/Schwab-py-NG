import importlib.metadata
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from schwab import doctor

from tests.utils import no_duplicates


class DoctorTest(unittest.TestCase):

    def token_file(self, *, age=0, expires_in=1800):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / 'token.json'
        created = time.time() - age
        path.write_text(json.dumps({
            'creation_timestamp': created,
            'token': {'access_token': 'never-render-this',
                      'refresh_token': 'nor-this',
                      'expires_at': time.time() + expires_in,
                      'token_type': 'Bearer', 'scope': 'api'},
        }), encoding='utf-8')
        self.addCleanup(directory.cleanup)
        return path

    @no_duplicates
    def test_distribution_collision_and_import_location(self):
        versions = {'schwab-py-ng': '4.0', 'schwab-py': '1.5'}
        with patch.object(importlib.metadata, 'version',
                          side_effect=lambda name: versions[name]):
            checks = doctor._distribution_checks()
        self.assertEqual('FAIL', checks[0].status)
        self.assertEqual('schwab import', checks[1].name)

    @no_duplicates
    def test_runtime_versions_report_missing_old_and_current(self):
        versions = {'authlib': '1.0', 'httpx2': '2.12.0'}

        def version(name):
            if name in versions:
                return versions[name]
            raise importlib.metadata.PackageNotFoundError

        with patch.object(importlib.metadata, 'version', side_effect=version):
            checks = doctor._runtime_checks()
        self.assertEqual('FAIL', checks[0].status)
        self.assertEqual('PASS', checks[1].status)
        self.assertEqual('FAIL', checks[2].status)

    @no_duplicates
    def test_token_details_are_useful_but_never_render_token_values(self):
        path = self.token_file(age=6.75 * 86400, expires_in=-1)
        checks = doctor._token_checks(path)
        age = next(c for c in checks if c.name == 'refresh token age')
        access = next(c for c in checks if c.name == 'access token')
        self.assertEqual('WARN', age.status)
        self.assertEqual('WARN', access.status)
        rendered = ' '.join(c.detail for c in checks)
        self.assertNotIn('never-render-this', rendered)
        self.assertNotIn('nor-this', rendered)

    @no_duplicates
    def test_missing_invalid_and_expired_tokens(self):
        self.assertEqual('WARN', doctor._token_checks(None)[0].status)
        self.assertEqual(
            'FAIL', doctor._token_checks('definitely-missing.json')[0].status)
        path = self.token_file(age=8 * 86400)
        self.assertEqual(
            'FAIL', next(c for c in doctor._token_checks(path)
                         if c.name == 'refresh token age').status)
        path.write_text('{bad json', encoding='utf-8')
        self.assertEqual('FAIL', doctor._token_checks(path)[0].status)

    @no_duplicates
    def test_live_checks_quote_accounts_latency_and_persistence(self):
        path = self.token_file()
        quote = MagicMock()
        quote.json.return_value = {'MSFT': {'quote': {'lastPrice': 412.5}}}
        accounts = MagicMock()
        accounts.json.return_value = [
            {'accountNumber': '123456570', 'hashValue': 'private'}]
        client = MagicMock()
        client.get_quote.return_value = quote
        client.get_account_numbers.return_value = accounts
        with patch('schwab.doctor.auth.client_from_token_file',
                   return_value=client):
            checks = doctor._live_checks(path, 'key', 'secret', 'MSFT')
        self.assertEqual(['PASS', 'PASS', 'PASS'], [c.status for c in checks])
        self.assertIn('...570', checks[1].detail)
        self.assertNotIn('private', ' '.join(c.detail for c in checks))

    @no_duplicates
    def test_live_failure_suppresses_exception_text(self):
        path = self.token_file()
        with patch('schwab.doctor.auth.client_from_token_file',
                   side_effect=RuntimeError('SECRET-TOKEN')):
            result = doctor._live_checks(path, 'key', 'secret', 'AAPL')[0]
        self.assertEqual('FAIL', result.status)
        self.assertIn('RuntimeError', result.detail)
        self.assertNotIn('SECRET-TOKEN', result.detail)

    @no_duplicates
    def test_default_live_offline_and_forced_missing_modes(self):
        path = self.token_file()
        with patch('schwab.doctor._distribution_checks', return_value=()), \
             patch('schwab.doctor._runtime_checks', return_value=()), \
             patch('schwab.doctor._live_checks', return_value=(
                 doctor.DoctorCheck('live', 'PASS', 'ok'),)) as live:
            checks = doctor.run_checks(
                token_path=path, api_key='key', app_secret='secret')
            live.assert_called_once()
            self.assertEqual('PASS', checks[-1].status)
            checks = doctor.run_checks(
                token_path=path, api_key='key', app_secret='secret',
                connect=False)
            self.assertEqual('SKIP', checks[-1].status)
        with patch('schwab.doctor._environment', return_value=None):
            self.assertEqual(
                'FAIL', doctor.run_checks(connect=True)[-1].status)

    @no_duplicates
    def test_update_checks_compare_versions_and_suppress_network_details(self):
        with patch.object(importlib.metadata, 'version', return_value='1.0'), \
             patch('schwab.doctor._latest_version', side_effect=(
                 ['2.0'] + ['1.0'] * len(doctor.RUNTIME_REQUIREMENTS))):
            checks = doctor._update_checks(1)
        self.assertEqual('WARN', checks[0].status)
        self.assertTrue(all(c.status == 'PASS' for c in checks[1:]))
        with patch.object(importlib.metadata, 'version',
                          side_effect=RuntimeError('private')):
            result = doctor._update_checks(1)[0]
        self.assertNotIn('private', result.detail)

    @no_duplicates
    def test_latest_version_and_quote_fallback(self):
        response = MagicMock()
        response.json.return_value = {'info': {'version': '9.0'}}
        with patch('schwab.doctor.httpx2.get', return_value=response) as get:
            self.assertEqual('9.0', doctor._latest_version('pkg', 3))
        get.assert_called_once_with(
            'https://pypi.org/pypi/pkg/json', timeout=3)
        self.assertEqual(10, doctor._quote_price(
            {'AAPL': {'regular': {'regularMarketLastPrice': 10}}}, 'AAPL'))

    @no_duplicates
    def test_main_text_json_and_failure_exit(self):
        checks = (doctor.DoctorCheck('distribution', 'FAIL', 'collision'),)
        with patch('schwab.doctor.run_checks', return_value=checks), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(1, doctor.main(['--offline']))
        self.assertEqual('[FAIL] distribution: collision\n', output.getvalue())
        with patch('schwab.doctor.run_checks', return_value=checks), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(1, doctor.main(['--json']))
        self.assertEqual('distribution', json.loads(output.getvalue())[0]['name'])
