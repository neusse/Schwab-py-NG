from .base import BaseClient
from ..debug import register_redactions_from_response
from ..utils import LazyLog, TokenRefreshError

import asyncio
import json


async def _mutation_request_with_token_retry(client, send):
    '''Retry only a rate-limited token refresh, never a mutation response.'''
    retry_number = 0
    while True:
        try:
            with client._translate_token_errors():
                return await send()
        except TokenRefreshError as exc:
            if (exc.rate_limited
                    and client._can_retry_rate_limit(retry_number)):
                delay = client._rate_limit_retry_delay(retry_number)
                client._log_rate_limit_retry(
                        delay, retry_number, token_refresh=True)
                await asyncio.sleep(delay)
                retry_number += 1
                continue
            raise


class AsyncClient(BaseClient):
    '''
    :class:`Client` for ``asyncio``: the same methods, each a coroutine to be
    awaited. Made by the auth functions when given ``asyncio=True``.
    '''

    async def close_async_session(self):
        '''Closes the underlying HTTP session and the connections it is
        holding. The ``asyncio`` counterpart of
        :meth:`Client.close_session`; the client cannot be used after it.
        '''
        await self.session.aclose()

    async def _get_request(self, path, params):
        dest = 'https://api.schwabapi.com' + path

        retry_number = 0
        while True:
            req_num = self._req_num()
            self.logger.debug('Req %s: GET to %s, params=%s',
                    req_num, dest,
                    LazyLog(lambda: json.dumps(params, indent=4)))

            try:
                with self._translate_token_errors():
                    resp = await self.session.get(dest, params=params)
            except TokenRefreshError as exc:
                if (exc.rate_limited
                        and self._can_retry_rate_limit(retry_number)):
                    delay = self._rate_limit_retry_delay(retry_number)
                    self._log_rate_limit_retry(
                            delay, retry_number, token_refresh=True)
                    await asyncio.sleep(delay)
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
                await asyncio.sleep(delay)
                retry_number += 1
                continue
            return resp

    async def _post_request(self, path, data):
        dest = 'https://api.schwabapi.com' + path

        req_num = self._req_num()
        self.logger.debug('Req %s: POST to %s, json=%s',
                req_num, dest, LazyLog(lambda: json.dumps(data, indent=4)))

        resp = await _mutation_request_with_token_retry(
                self, lambda: self.session.post(dest, json=data))
        self._log_response(resp, req_num)
        register_redactions_from_response(resp)
        return resp

    async def _put_request(self, path, data):
        dest = 'https://api.schwabapi.com' + path

        req_num = self._req_num()
        self.logger.debug('Req %s: PUT to %s, json=%s',
                req_num, dest, LazyLog(lambda: json.dumps(data, indent=4)))

        resp = await _mutation_request_with_token_retry(
                self, lambda: self.session.put(dest, json=data))
        self._log_response(resp, req_num)
        register_redactions_from_response(resp)
        return resp

    async def _delete_request(self, path):
        dest = 'https://api.schwabapi.com' + path

        req_num = self._req_num()
        self.logger.debug('Req %s: DELETE to %s', req_num, dest)

        resp = await _mutation_request_with_token_retry(
                self, lambda: self.session.delete(dest))
        self._log_response(resp, req_num)
        register_redactions_from_response(resp)
        return resp
