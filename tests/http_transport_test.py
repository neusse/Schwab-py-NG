'''Public-client tests that stop at a real ``httpx2`` transport seam.'''

import asyncio
import json

import pytest
import httpx2

from schwab.orders.easy import EasyOrders
from schwab.orders.equities import equity_buy_limit
from schwab.utils import Utils

from .http_transport import MockSchwab


def test_market_data_crosses_the_real_oauth_transport():
    schwab = MockSchwab().respond_json(200, {
        'AAPL': {'quote': {'lastPrice': 210.25}},
    })

    with schwab.sync_client() as client:
        response = client.get_quote('AAPL')

    assert response.json() == {
        'AAPL': {'quote': {'lastPrice': 210.25}},
    }
    assert len(schwab.requests) == 1
    request = schwab.requests[0]
    assert request.method == 'GET'
    assert request.url.path == '/marketdata/v1/AAPL/quotes'
    assert request.headers['Authorization'] == 'Bearer test-access-token'


def test_order_lifecycle_crosses_the_real_oauth_transport():
    account_hash = 'TEST_ACCOUNT_HASH'
    schwab = (MockSchwab()
              .respond_json(200, {'orderStrategy': {'status': 'ACCEPTED'}})
              .respond(201, headers={
                  'Location':
                      'https://api.schwabapi.com/trader/v1/accounts/'
                      'TEST_ACCOUNT_HASH/orders/7001',
              })
              .respond(201, headers={
                  'Location':
                      'https://api.schwabapi.com/trader/v1/accounts/'
                      'TEST_ACCOUNT_HASH/orders/7002',
              })
              .respond(204))
    order = equity_buy_limit('AAPL', 2, '210.25')

    with schwab.sync_client() as client:
        preview = client.preview_order(account_hash, order)
        placed = client.place_order(account_hash, order)
        replaced = client.replace_order(account_hash, 7001, order)
        canceled = client.cancel_order(7002, account_hash)
        placed_id = Utils(client, account_hash).extract_order_id(placed)
        replaced_id = Utils(client, account_hash).extract_order_id(replaced)

    assert preview.json() == {'orderStrategy': {'status': 'ACCEPTED'}}
    assert (placed.status_code, placed_id) == (201, 7001)
    assert (replaced.status_code, replaced_id) == (201, 7002)
    assert canceled.status_code == 204
    calls = [(request.method, request.url.path)
             for request in schwab.requests]
    assert calls == [
                ('POST', '/trader/v1/accounts/TEST_ACCOUNT_HASH/previewOrder'),
                ('POST', '/trader/v1/accounts/TEST_ACCOUNT_HASH/orders'),
                ('PUT', '/trader/v1/accounts/TEST_ACCOUNT_HASH/orders/7001'),
                ('DELETE',
                 '/trader/v1/accounts/TEST_ACCOUNT_HASH/orders/7002'),
            ]
    expected_order = order.build()
    assert [json.loads(request.content) for request in schwab.requests[:3]] \
            == [expected_order, expected_order, expected_order]


def test_async_accounts_and_orders_cross_the_real_oauth_transport():
    async def run():
        schwab = (MockSchwab()
                  .respond_json(200, {
                      'securitiesAccount': {'accountNumber': 'TEST_ACCOUNT'},
                  })
                  .respond_json(200, {
                      'orderStrategy': {'status': 'ACCEPTED'},
                  })
                  .respond(201, headers={
                      'Location':
                          'https://api.schwabapi.com/trader/v1/accounts/'
                          'TEST_ACCOUNT_HASH/orders/8001',
                  }))
        order = equity_buy_limit('MSFT', 1, '500.00')

        async with schwab.async_client() as client:
            account = await client.get_account('TEST_ACCOUNT_HASH')
            preview = await client.preview_order('TEST_ACCOUNT_HASH', order)
            placed = await client.place_order('TEST_ACCOUNT_HASH', order)

        assert account.json()['securitiesAccount']['accountNumber'] \
                == 'TEST_ACCOUNT'
        assert preview.json()['orderStrategy']['status'] == 'ACCEPTED'
        assert placed.headers['Location'].endswith('/orders/8001')
        calls = [(request.method, request.url.path)
                 for request in schwab.requests]
        assert calls == [
                    ('GET', '/trader/v1/accounts/TEST_ACCOUNT_HASH'),
                    ('POST',
                     '/trader/v1/accounts/TEST_ACCOUNT_HASH/previewOrder'),
                    ('POST', '/trader/v1/accounts/TEST_ACCOUNT_HASH/orders'),
                ]
        assert json.loads(schwab.requests[1].content) == order.build()
        assert json.loads(schwab.requests[2].content) == order.build()

    asyncio.run(run())


def test_failed_preview_stops_a_real_transport_order_workflow():
    schwab = MockSchwab().respond_json(400, {
        'errors': [{'message': 'limit price is outside the accepted range'}],
    })

    with schwab.sync_client() as client:
        orders = EasyOrders(client, 'TEST_ACCOUNT_HASH')
        result = orders.place(
                orders.buy('AAPL', 1, limit_price='999.00'),
                confirm_live_order=True)

    assert result.placed is False
    assert result.preview_response.status_code == 400
    assert result.place_response is None
    calls = [(request.method, request.url.path)
             for request in schwab.requests]
    assert calls == [
                ('POST',
                 '/trader/v1/accounts/TEST_ACCOUNT_HASH/previewOrder'),
            ]


def test_transport_failure_reaches_the_public_client_without_network_access():
    schwab = MockSchwab().fail(
            httpx2.ConnectTimeout('the fake Schwab endpoint timed out'))

    with schwab.sync_client() as client:
        with pytest.raises(httpx2.ConnectTimeout, match='fake Schwab'):
            client.get_account_numbers()

    assert len(schwab.requests) == 1
    assert schwab.requests[0].url.path \
            == '/trader/v1/accounts/accountNumbers'
