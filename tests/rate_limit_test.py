import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest

from schwab.client import AsyncClient, Client
from schwab.utils import TokenRefreshError


API_KEY = 'rate-limit-test-key'


def response(status_code, *, retry_after=None):
    headers = {}
    if retry_after is not None:
        headers['Retry-After'] = retry_after
    return httpx2.Response(
            status_code, headers=headers, json={},
            request=httpx2.Request('GET', 'https://api.schwabapi.com/test'))


def test_rate_limit_retry_is_disabled_by_default():
    session = MagicMock()
    session.get.return_value = response(429)
    client = Client(API_KEY, session)

    result = client.get_account_numbers()

    assert result.status_code == 429
    session.get.assert_called_once()


def test_get_retries_429_and_honors_retry_after():
    session = MagicMock()
    session.get.side_effect = [response(429, retry_after='3'), response(200)]
    client = Client(API_KEY, session)
    client.set_rate_limit_retry(2, backoff_factor=0.25, max_delay=10)

    with patch('schwab.client.synchronous.time.sleep') as sleep:
        result = client.get_account_numbers()

    assert result.status_code == 200
    assert session.get.call_count == 2
    sleep.assert_called_once_with(3.0)


def test_get_retry_is_bounded_and_uses_capped_backoff():
    session = MagicMock()
    session.get.return_value = response(429)
    client = Client(API_KEY, session)
    client.set_rate_limit_retry(2, backoff_factor=2, max_delay=3)

    with patch('schwab.client.synchronous.time.sleep') as sleep:
        result = client.get_account_numbers()

    assert result.status_code == 429
    assert session.get.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [2.0, 3.0]


def test_mutation_response_is_never_retried():
    session = MagicMock()
    session.post.return_value = response(429)
    client = Client(API_KEY, session)
    client.set_rate_limit_retry(3, backoff_factor=0)

    result = client.place_order('hash', {'order': 'spec'})

    assert result.status_code == 429
    session.post.assert_called_once()


def test_rate_limited_token_refresh_is_safe_to_retry_before_mutation():
    session = MagicMock()
    session.post.side_effect = [
        TokenRefreshError(
                'rate limited', status_code=429, endpoint_answered=True),
        response(201),
    ]
    client = Client(API_KEY, session)
    client.set_rate_limit_retry(1, backoff_factor=0)

    with patch('schwab.client.synchronous.time.sleep') as sleep:
        result = client.place_order('hash', {'order': 'spec'})

    assert result.status_code == 201
    assert session.post.call_count == 2
    sleep.assert_called_once_with(0.0)


@pytest.mark.parametrize(
        'arguments',
        [(-1,), (True,), (1.5,), (1, -1), (1, float('inf'))])
def test_rate_limit_retry_rejects_invalid_configuration(arguments):
    client = Client(API_KEY, MagicMock())
    max_retries = arguments[0]
    kwargs = {}
    if len(arguments) > 1:
        kwargs['backoff_factor'] = arguments[1]
    if len(arguments) > 2:
        kwargs['max_delay'] = arguments[2]

    with pytest.raises(ValueError):
        client.set_rate_limit_retry(max_retries, **kwargs)


def test_async_get_has_equivalent_rate_limit_recovery():
    async def run():
        session = MagicMock()
        session.get = AsyncMock(
                side_effect=[response(429, retry_after='0'), response(200)])
        client = AsyncClient(API_KEY, session)
        client.set_rate_limit_retry(1)

        with patch('schwab.client.asynchronous.asyncio.sleep',
                   new=AsyncMock()) as sleep:
            result = await client.get_account_numbers()

        assert result.status_code == 200
        assert session.get.call_count == 2
        sleep.assert_awaited_once_with(0.0)

    asyncio.run(run())


def test_async_token_refresh_429_recovers_before_get_and_mutation():
    async def run():
        session = MagicMock()
        rate_limited = TokenRefreshError(
                'rate limited', status_code=429, endpoint_answered=True)
        session.get = AsyncMock(side_effect=[rate_limited, response(200)])
        session.post = AsyncMock(side_effect=[rate_limited, response(201)])
        client = AsyncClient(API_KEY, session)
        client.set_rate_limit_retry(1, backoff_factor=0)

        with patch('schwab.client.asynchronous.asyncio.sleep',
                   new=AsyncMock()) as sleep:
            get_result = await client.get_account_numbers()
            post_result = await client.place_order('hash', {'order': 'spec'})

        assert get_result.status_code == 200
        assert post_result.status_code == 201
        assert sleep.await_count == 2

    asyncio.run(run())
