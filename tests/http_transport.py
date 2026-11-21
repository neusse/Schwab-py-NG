'''A deterministic Schwab HTTP adapter for public-client tests.

The adapter keeps the real Authlib/``httpx2`` session and Schwab client in the
test. Only the final network hop is replaced. Queue the responses Schwab would
have returned, call public client methods, then inspect ``requests`` for the
actual method, URL, headers and serialized body that crossed the transport
seam.

This proves client-side HTTP behavior. It deliberately does not emulate
Schwab's private validation, order routing, fills or account state.
'''

from collections import deque
from contextlib import asynccontextmanager, contextmanager
import time

from authlib.integrations.httpx_client import AsyncOAuth2Client, OAuth2Client
import httpx2

from schwab.client import AsyncClient, Client


class MockSchwab:
    '''Queue responses behind a real OAuth session and capture its requests.'''

    def __init__(self):
        self.requests = []
        self._responses = deque()

    def respond_json(self, status_code, payload, *, headers=None):
        self._responses.append(
                (status_code, {'json': payload}, headers or {}))
        return self

    def respond(self, status_code, *, headers=None, content=b''):
        self._responses.append(
                (status_code, {'content': content}, headers or {}))
        return self

    def fail(self, exception):
        self._responses.append(exception)
        return self

    def _dispatch(self, request):
        self.requests.append(request)
        if not self._responses:
            raise AssertionError(
                    'the client made a request with no queued response: '
                    '{} {}'.format(request.method, request.url))
        response = self._responses.popleft()
        if isinstance(response, BaseException):
            raise response
        status_code, body, headers = response
        return httpx2.Response(
                status_code, headers=headers, request=request, **body)

    def _session(self, session_class):
        return session_class(
                'test-app-key', client_secret='test-app-secret',
                token={
                    'access_token': 'test-access-token',
                    'refresh_token': 'test-refresh-token',
                    'token_type': 'Bearer',
                    'expires_at': time.time() + 3600,
                },
                transport=httpx2.MockTransport(self._dispatch),
                trust_env=False)

    @contextmanager
    def sync_client(self):
        session = self._session(OAuth2Client)
        try:
            yield Client('test-app-key', session)
        finally:
            session.close()

    @asynccontextmanager
    async def async_client(self):
        session = self._session(AsyncOAuth2Client)
        try:
            yield AsyncClient('test-app-key', session)
        finally:
            await session.aclose()
