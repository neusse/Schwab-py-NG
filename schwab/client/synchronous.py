from .base import BaseClient
from ..utils import LazyLog, TokenRefreshError
from ..debug import register_redactions_from_response

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
