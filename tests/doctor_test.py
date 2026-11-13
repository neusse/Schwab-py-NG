import importlib.metadata
import io
import unittest
from unittest.mock import MagicMock, patch

from schwab import doctor

from tests.utils import no_duplicates


class DoctorTest(unittest.TestCase):

    @no_duplicates
    def test_detects_distribution_collision(self):
        def version(name):
            return {'schwab-py-ng': '4.0', 'schwab-py': '1.5'}[name]

        with patch.object(importlib.metadata, 'version', side_effect=version):
            result = doctor.run_checks()[1]
        self.assertEqual('FAIL', result.status)
        self.assertNotIn('secret', result.detail.lower())

    @no_duplicates
    def test_token_age_is_reported_without_reading_token_fields(self):
        with patch.object(importlib.metadata, 'version',
                          side_effect=importlib.metadata.PackageNotFoundError), \
             patch('schwab.doctor.Path.is_file', return_value=True), \
             patch('schwab.doctor.auth.token_file_age',
                   return_value=6.75 * 24 * 60 * 60):
            checks = doctor.run_checks(token_path='token.json')
        age = next(check for check in checks if check.name == 'token age')
        self.assertEqual('WARN', age.status)
        rendered = ' '.join(check.detail for check in checks)
        self.assertNotIn('access_token', rendered)
        self.assertNotIn('refresh_token', rendered)

    @no_duplicates
    def test_connectivity_is_opt_in_and_suppresses_exception_text(self):
        with patch.object(importlib.metadata, 'version',
                          side_effect=importlib.metadata.PackageNotFoundError), \
             patch('schwab.doctor.Path.is_file', return_value=True), \
             patch('schwab.doctor.auth.token_file_age', return_value=0), \
             patch('schwab.doctor.auth.client_from_token_file',
                   side_effect=RuntimeError('SECRET-TOKEN')):
            checks = doctor.run_checks(
                token_path='token.json', api_key='key', app_secret='secret',
                connect=True)
        result = checks[-1]
        self.assertEqual('FAIL', result.status)
        self.assertNotIn('SECRET-TOKEN', result.detail)
        self.assertIn('RuntimeError', result.detail)

    @no_duplicates
    def test_successful_connectivity_checks_status_only(self):
        response = MagicMock()
        client = MagicMock()
        client.get_quote.return_value = response
        with patch.object(importlib.metadata, 'version',
                          side_effect=importlib.metadata.PackageNotFoundError), \
             patch('schwab.doctor.Path.is_file', return_value=True), \
             patch('schwab.doctor.auth.token_file_age', return_value=0), \
             patch('schwab.doctor.auth.client_from_token_file',
                   return_value=client):
            checks = doctor.run_checks(
                token_path='token.json', api_key='key', app_secret='secret',
                connect=True, symbol='MSFT')
        response.raise_for_status.assert_called_once_with()
        client.get_quote.assert_called_once_with('MSFT')
        self.assertEqual('PASS', checks[-1].status)

    @no_duplicates
    def test_main_returns_failure_and_prints_sanitized_results(self):
        checks = (doctor.DoctorCheck('distribution', 'FAIL', 'collision'),)
        output = io.StringIO()
        with patch('schwab.doctor.run_checks', return_value=checks), \
             patch('sys.stdout', output):
            result = doctor.main([])
        self.assertEqual(1, result)
        self.assertEqual('[FAIL] distribution: collision\n', output.getvalue())

    @no_duplicates
    def test_missing_legacy_distribution_and_token_failures(self):
        def legacy_only(name):
            if name == 'schwab-py':
                return '1.0'
            raise importlib.metadata.PackageNotFoundError

        with patch.object(importlib.metadata, 'version', side_effect=legacy_only):
            self.assertEqual('FAIL', doctor.run_checks()[1].status)
        self.assertEqual('WARN', doctor._token_checks(None)[0].status)
        with patch('schwab.doctor.Path.is_file', return_value=False):
            self.assertEqual('FAIL', doctor._token_checks('missing')[0].status)
        with patch('schwab.doctor.Path.is_file', return_value=True), \
             patch('schwab.doctor.auth.token_file_age',
                   side_effect=ValueError('private')):
            result = doctor._token_checks('invalid')[0]
        self.assertEqual('FAIL', result.status)
        self.assertNotIn('private', result.detail)

    @no_duplicates
    def test_expired_token_missing_connectivity_credentials_and_success_main(self):
        with patch('schwab.doctor.Path.is_file', return_value=True), \
             patch('schwab.doctor.auth.token_file_age',
                   return_value=8 * 24 * 60 * 60):
            self.assertEqual('FAIL', doctor._token_checks('token')[0].status)
        with patch.object(importlib.metadata, 'version',
                          side_effect=importlib.metadata.PackageNotFoundError), \
             patch('schwab.doctor._environment', return_value=None):
            self.assertEqual('FAIL', doctor.run_checks(connect=True)[-1].status)
        checks = (doctor.DoctorCheck('all', 'PASS', 'ok'),)
        with patch('schwab.doctor.run_checks', return_value=checks), \
             patch('sys.stdout', io.StringIO()):
            self.assertEqual(0, doctor.main(['--symbol', 'MSFT']))
