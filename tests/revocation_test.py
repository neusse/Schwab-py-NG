import asyncio
import base64
import json
import os
import tempfile
import time
import unittest
import urllib.parse
from unittest.mock import patch
from unittest.mock import MagicMock

import httpx2

from schwab import auth
from schwab.client import Client
from schwab.utils import TokenRevocationError, TokenRevokedError


API_KEY = 'revocation-app-key'
APP_SECRET = 'revocation-app-secret'
REFRESH_TOKEN = 'revocation-refresh-token'
CREATED_AT = 1700000000
REVOKE_URL = 'https://api.schwabapi.com/v1/oauth/revoke'


def stored_token():
    return {
        'creation_timestamp': CREATED_AT,
        'token': {
            'access_token': 'revocation-access-token',
            'refresh_token': REFRESH_TOKEN,
            'token_type': 'Bearer',
            'expires_at': int(time.time()) + 1800,
        },
    }


class SyncRevocationTest(unittest.TestCase):
    def test_client_without_token_metadata_is_refused_before_a_request(self):
        session = MagicMock()
        client = Client(API_KEY, session)

        with self.assertRaises(TokenRevocationError) as caught:
            client.revoke()

        error = caught.exception
        self.assertFalse(error.endpoint_answered)
        self.assertFalse(error.retryable)
        self.assertFalse(error.server_revoked)
        session.request.assert_not_called()

    def test_missing_refresh_token_is_refused_before_a_request(self):
        token = stored_token()
        del token['token']['refresh_token']
        client = auth.client_from_access_functions(
                API_KEY, APP_SECRET, lambda: token,
                lambda *args, **kwargs: None)
        requests = []
        client.session._transport = httpx2.MockTransport(
                lambda request: requests.append(request))

        with self.assertRaises(TokenRevocationError) as caught:
            client.revoke()

        error = caught.exception
        self.assertFalse(error.endpoint_answered)
        self.assertFalse(error.retryable)
        self.assertEqual([], requests)

    def test_success_revokes_with_basic_auth_and_persists_a_secretless_tombstone(self):
        stored = []
        requests = []
        client = auth.client_from_access_functions(
                API_KEY, APP_SECRET, stored_token,
                lambda token, *args, **kwargs: stored.append(token))

        def handler(request):
            requests.append(request)
            return httpx2.Response(200, request=request)

        client.session._transport = httpx2.MockTransport(handler)

        result = client.revoke()

        self.assertIsNone(result)
        self.assertEqual([{
            'creation_timestamp': CREATED_AT,
            'revoked': True,
        }], stored)
        self.assertEqual(1, len(requests))
        request = requests[0]
        self.assertEqual('POST', request.method)
        self.assertEqual(REVOKE_URL, str(request.url))
        self.assertEqual(
                '{}:{}'.format(API_KEY, APP_SECRET),
                base64.b64decode(
                    request.headers['Authorization'].split(' ', 1)[1]
                ).decode('ascii'))
        self.assertEqual(
                {'token': [REFRESH_TOKEN],
                 'token_type_hint': ['refresh_token']},
                urllib.parse.parse_qs(request.content.decode('ascii')))

    def test_service_unavailable_is_retryable_and_keeps_the_token_active(self):
        stored = []
        client = auth.client_from_access_functions(
                API_KEY, APP_SECRET, stored_token,
                lambda token, *args, **kwargs: stored.append(token))

        def handler(request):
            return httpx2.Response(
                    503, request=request, json={'echo': REFRESH_TOKEN})

        client.session._transport = httpx2.MockTransport(handler)

        with self.assertRaises(TokenRevocationError) as caught:
            client.revoke()

        error = caught.exception
        self.assertEqual(503, error.status_code)
        self.assertTrue(error.endpoint_answered)
        self.assertTrue(error.retryable)
        self.assertFalse(error.server_revoked)
        self.assertEqual([], stored)
        self.assertEqual(REFRESH_TOKEN, client.token_metadata.token['refresh_token'])
        self.assertNotIn(REFRESH_TOKEN, str(error))
        self.assertNotIn(REFRESH_TOKEN, repr(error))
        self.assertFalse(hasattr(error, 'request'))
        self.assertFalse(hasattr(error, 'response'))

    def test_client_error_is_not_retryable_and_keeps_the_token_active(self):
        stored = []
        client = auth.client_from_access_functions(
                API_KEY, APP_SECRET, stored_token,
                lambda token, *args, **kwargs: stored.append(token))
        client.session._transport = httpx2.MockTransport(
                lambda request: httpx2.Response(401, request=request))

        with self.assertRaises(TokenRevocationError) as caught:
            client.revoke()

        self.assertEqual(401, caught.exception.status_code)
        self.assertTrue(caught.exception.endpoint_answered)
        self.assertFalse(caught.exception.retryable)
        self.assertFalse(caught.exception.server_revoked)
        self.assertEqual([], stored)

    def test_transport_failure_is_sanitized_and_retryable(self):
        stored = []
        client = auth.client_from_access_functions(
                API_KEY, APP_SECRET, stored_token,
                lambda token, *args, **kwargs: stored.append(token))

        def handler(request):
            raise httpx2.ConnectError(
                    'transport exposed {}'.format(REFRESH_TOKEN),
                    request=request)

        client.session._transport = httpx2.MockTransport(handler)

        with self.assertRaises(TokenRevocationError) as caught:
            client.revoke()

        error = caught.exception
        self.assertIsNone(error.status_code)
        self.assertFalse(error.endpoint_answered)
        self.assertTrue(error.retryable)
        self.assertFalse(error.server_revoked)
        self.assertIsNone(error.__cause__)
        self.assertEqual([], stored)
        self.assertNotIn(REFRESH_TOKEN, str(error))
        self.assertNotIn(REFRESH_TOKEN, repr(error))

    def test_persistence_failure_reports_that_schwab_already_revoked(self):
        def fail_to_store(token, *args, **kwargs):
            raise OSError('writer exposed {}'.format(REFRESH_TOKEN))

        client = auth.client_from_access_functions(
                API_KEY, APP_SECRET, stored_token, fail_to_store)
        client.session._transport = httpx2.MockTransport(
                lambda request: httpx2.Response(200, request=request))

        with self.assertRaises(TokenRevocationError) as caught:
            client.revoke()

        error = caught.exception
        self.assertEqual(200, error.status_code)
        self.assertTrue(error.endpoint_answered)
        self.assertTrue(error.retryable)
        self.assertTrue(error.server_revoked)
        self.assertIsNone(error.__cause__)
        self.assertEqual(REFRESH_TOKEN, client.token_metadata.token['refresh_token'])
        self.assertFalse(client.token_metadata.revoked)
        self.assertNotIn(REFRESH_TOKEN, str(error))
        self.assertNotIn(REFRESH_TOKEN, repr(error))

    def test_repeated_revocation_is_a_local_noop(self):
        stored = []
        requests = []
        client = auth.client_from_access_functions(
                API_KEY, APP_SECRET, stored_token,
                lambda token, *args, **kwargs: stored.append(token))

        def handler(request):
            requests.append(request)
            return httpx2.Response(200, request=request)

        client.session._transport = httpx2.MockTransport(handler)

        client.revoke()
        result = client.revoke()

        self.assertIsNone(result)
        self.assertEqual(1, len(requests))
        self.assertEqual(1, len(stored))


class AsyncRevocationTest(unittest.TestCase):
    def test_success_revokes_and_persists_a_secretless_tombstone(self):
        async def run():
            stored = []
            requests = []
            client = auth.client_from_access_functions(
                    API_KEY, APP_SECRET, stored_token,
                    lambda token, *args, **kwargs: stored.append(token),
                    asyncio=True)

            def handler(request):
                requests.append(request)
                return httpx2.Response(200, request=request)

            client.session._transport = httpx2.MockTransport(handler)

            result = await client.revoke()

            self.assertIsNone(result)
            self.assertEqual([{
                'creation_timestamp': CREATED_AT,
                'revoked': True,
            }], stored)
            self.assertEqual(1, len(requests))
            request = requests[0]
            self.assertEqual('POST', request.method)
            self.assertEqual(REVOKE_URL, str(request.url))
            self.assertEqual(
                    '{}:{}'.format(API_KEY, APP_SECRET),
                    base64.b64decode(
                        request.headers['Authorization'].split(' ', 1)[1]
                    ).decode('ascii'))
            self.assertEqual(
                    {'token': [REFRESH_TOKEN],
                     'token_type_hint': ['refresh_token']},
                    urllib.parse.parse_qs(request.content.decode('ascii')))
            await client.close_async_session()

        asyncio.run(run())

    def test_repeated_revocation_is_a_local_noop(self):
        async def run():
            stored = []
            requests = []
            client = auth.client_from_access_functions(
                    API_KEY, APP_SECRET, stored_token,
                    lambda token, *args, **kwargs: stored.append(token),
                    asyncio=True)

            def handler(request):
                requests.append(request)
                return httpx2.Response(200, request=request)

            client.session._transport = httpx2.MockTransport(handler)

            await client.revoke()
            result = await client.revoke()

            self.assertIsNone(result)
            self.assertEqual(1, len(requests))
            self.assertEqual(1, len(stored))
            await client.close_async_session()

        asyncio.run(run())

    def test_transport_failure_is_sanitized_and_retryable(self):
        async def run():
            client = auth.client_from_access_functions(
                    API_KEY, APP_SECRET, stored_token,
                    lambda *args, **kwargs: None, asyncio=True)

            def handler(request):
                raise httpx2.ConnectError(
                        'transport exposed {}'.format(REFRESH_TOKEN),
                        request=request)

            client.session._transport = httpx2.MockTransport(handler)

            with self.assertRaises(TokenRevocationError) as caught:
                await client.revoke()

            error = caught.exception
            self.assertTrue(error.retryable)
            self.assertFalse(error.endpoint_answered)
            self.assertIsNone(error.__cause__)
            self.assertNotIn(REFRESH_TOKEN, repr(error))
            await client.close_async_session()

        asyncio.run(run())


class RevokedTokenReloadTest(unittest.TestCase):
    def test_direct_loader_refuses_a_revoked_tombstone(self):
        tombstone = {
            'creation_timestamp': CREATED_AT,
            'revoked': True,
        }

        with self.assertRaises(TokenRevokedError):
            auth.client_from_access_functions(
                    API_KEY, APP_SECRET, lambda: tombstone,
                    lambda *args, **kwargs: None)

    def test_loader_rejects_a_non_boolean_revoked_marker(self):
        malformed = stored_token()
        malformed['revoked'] = 1

        with self.assertRaisesRegex(ValueError, 'revoked marker'):
            auth.client_from_access_functions(
                    API_KEY, APP_SECRET, lambda: malformed,
                    lambda *args, **kwargs: None)

    def test_loader_refuses_the_upstream_revoked_shape_with_token_retained(self):
        upstream_shape = stored_token()
        upstream_shape['revoked'] = True

        with self.assertRaises(TokenRevokedError):
            auth.client_from_access_functions(
                    API_KEY, APP_SECRET, lambda: upstream_shape,
                    lambda *args, **kwargs: None)

    def test_token_age_monitor_reports_a_revoked_tombstone(self):
        tombstone = {
            'creation_timestamp': CREATED_AT,
            'revoked': True,
        }
        with tempfile.TemporaryDirectory() as directory:
            token_path = os.path.join(directory, 'token.json')
            with open(token_path, 'w') as token_file:
                json.dump(tombstone, token_file)

            with self.assertRaises(TokenRevokedError):
                auth.token_file_age(token_path)

    def test_easy_client_replaces_a_revoked_tombstone_through_full_oauth(self):
        tombstone = {
            'creation_timestamp': CREATED_AT,
            'revoked': True,
        }
        with tempfile.TemporaryDirectory() as directory:
            token_path = os.path.join(directory, 'token.json')
            with open(token_path, 'w') as token_file:
                json.dump(tombstone, token_file)

            replacement = object()
            with patch('schwab.auth.client_from_login_flow',
                       return_value=replacement) as login:
                result = auth.easy_client(
                        API_KEY, APP_SECRET, 'https://127.0.0.1:8182',
                        token_path, max_token_age=0)

            self.assertIs(replacement, result)
            login.assert_called_once()


if __name__ == '__main__':
    unittest.main()
