from .base import BaseClient
from ..utils import LazyLog, TokenRefreshError
from ..debug import register_redactions_from_response

import httpx2
import json
import time


class Client(BaseClient):
    '''
    The HTTP client: one method per endpoint Schwab publishes, each returning
    the raw ``httpx2`` response. Make one with :ref:`the auth functions
    <auth>` rather than directly, since they manage the token.
    :class:`AsyncClient` is the same client for ``asyncio``.
    '''

    def close_session(self):
        '''Closes the underlying HTTP session and the connections it is
        holding.

        Only worth calling if you are creating clients repeatedly -- one client
        held for the life of the process needs nothing. Without it, connections
        are released whenever the session is garbage collected, which is not a
        moment anything guarantees.

        The client cannot be used after this.
        :meth:`AsyncClient.close_async_session` is the equivalent for the
        asyncio client.
        '''
        self.session.close()

    def revoke(self):
        '''Permanently revoke this client's refresh token at Schwab.

        On HTTP 200, replaces the stored token with a secretless revoked
        marker and returns ``None``. Calling this method again on the same
        client is a local no-op. A client loaded directly from the marker
        raises :class:`~schwab.utils.TokenRevokedError`; ``easy_client`` starts
        a full authorization flow instead.

        This is irreversible. Use it when retiring or losing a credential,
        not as a way to refresh an access token. RFC 7009 says an authorization
        server should also invalidate access tokens from the same grant when
        it supports that operation; it does not make that cascade universal.

        :raises TokenRevocationError: The request could not be sent, Schwab
            returned a status other than 200, the client has no usable refresh
            token or persistent metadata, or the revoked marker could not be
            stored. Inspect ``endpoint_answered``, ``status_code``,
            ``retryable`` and ``server_revoked``; the exception deliberately
            carries no credential-bearing request or response.
        '''
        request = self._token_revocation_request()
        if request is None:
            return None
        try:
            response = self.session.request(
                    'POST', **request)
        except httpx2.HTTPError:
            raise self._token_revocation_transport_error() from None
        self._persist_token_revocation(response)

    def _get_request(self, path, params):
        dest = 'https://api.schwabapi.com' + path

        retry_number = 0
        while True:
            req_num = self._req_num()
            self.logger.debug('Req %s: GET to %s, params=%s',
                    req_num, dest,
                    LazyLog(lambda: json.dumps(params, indent=4)))

            try:
                with self._translate_token_errors():
                    resp = self.session.get(dest, params=params)
            except TokenRefreshError as exc:
                if (exc.rate_limited
                        and self._can_retry_rate_limit(retry_number)):
                    delay = self._rate_limit_retry_delay(retry_number)
                    self._log_rate_limit_retry(
                            delay, retry_number, token_refresh=True)
                    time.sleep(delay)
                    retry_number += 1
                    continue
                raise

            self._log_response(resp, req_num)
            register_redactions_from_response(resp)
            if (resp.status_code == 429
                    and self._can_retry_rate_limit(retry_number)):
                delay = self._rate_limit_retry_delay(retry_number, resp)
                self._log_rate_limit_retry(
                        delay, retry_number, token_refresh=False)
                time.sleep(delay)
                retry_number += 1
                continue
            return resp

    def _post_request(self, path, data):
        dest = 'https://api.schwabapi.com' + path

        req_num = self._req_num()
        self.logger.debug('Req %s: POST to %s, json=%s',
            req_num, dest, LazyLog(lambda: json.dumps(data, indent=4)))

        resp = self._mutation_request_with_token_retry(
                lambda: self.session.post(dest, json=data))
        self._log_response(resp, req_num)
        register_redactions_from_response(resp)
        return resp

    def _put_request(self, path, data):
        dest = 'https://api.schwabapi.com' + path

        req_num = self._req_num()
        self.logger.debug('Req %s: PUT to %s, json=%s',
            req_num, dest, LazyLog(lambda: json.dumps(data, indent=4)))

        resp = self._mutation_request_with_token_retry(
                lambda: self.session.put(dest, json=data))
        self._log_response(resp, req_num)
        register_redactions_from_response(resp)
        return resp

    def _delete_request(self, path):
        dest = 'https://api.schwabapi.com' + path

        req_num = self._req_num()
        self.logger.debug('Req %s: DELETE to %s', req_num, dest)

        resp = self._mutation_request_with_token_retry(
                lambda: self.session.delete(dest))
        self._log_response(resp, req_num)
        register_redactions_from_response(resp)
        return resp

    def _mutation_request_with_token_retry(self, send):
        '''Retry only a rate-limited token refresh, never a mutation response.'''
        retry_number = 0
        while True:
            try:
                with self._translate_token_errors():
                    return send()
            except TokenRefreshError as exc:
                if (exc.rate_limited
                        and self._can_retry_rate_limit(retry_number)):
                    delay = self._rate_limit_retry_delay(retry_number)
                    self._log_rate_limit_retry(
                            delay, retry_number, token_refresh=True)
                    time.sleep(delay)
                    retry_number += 1
                    continue
                raise
