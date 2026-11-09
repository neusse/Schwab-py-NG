import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from schwab.orders.easy import (AsyncEasyOrders, EasyOrders,
                                LiveOrderConfirmationError,
                                OrderTemplateError, load_order_template,
                                save_order_template)


class Response:
    def __init__(self, status_code):
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300


class Client:
    def __init__(self, preview_status=200, place_status=201):
        self.preview_status = preview_status
        self.place_status = place_status
        self.calls = []

    def preview_order(self, account_hash, order):
        self.calls.append(('preview', account_hash, order))
        return Response(self.preview_status)

    def place_order(self, account_hash, order):
        self.calls.append(('place', account_hash, order))
        return Response(self.place_status)


class AsyncClient(Client):
    async def preview_order(self, account_hash, order):
        self.calls.append(('preview', account_hash, order))
        return Response(self.preview_status)

    async def place_order(self, account_hash, order):
        self.calls.append(('place', account_hash, order))
        return Response(self.place_status)


def test_convenience_builders_use_existing_order_schema():
    easy = EasyOrders(Client(), 'hash')

    assert easy.buy('AAPL', 2).build()['orderType'] == 'MARKET'
    assert easy.buy('AAPL', 2, limit_price='201.25').build()['price'] == '201.25'
    assert easy.stop_loss('AAPL', 2, '180.00').build()['stopPrice'] == '180.00'

    bracket = easy.bracket(
            'AAPL', 2, entry_price='200.00', profit_price='220.00',
            stop_price='180.00').build()
    assert bracket['orderStrategyType'] == 'TRIGGER'
    assert bracket['childOrderStrategies'][0]['orderStrategyType'] == 'OCO'

    assert easy.sell('AAPL', 2).build()['orderType'] == 'MARKET'
    assert easy.sell(
            'AAPL', 2, limit_price='220.00').build()['price'] == '220.00'
    trailing = easy.trailing_stop_loss('AAPL', 2, 5.0).build()
    assert trailing['orderType'] == 'TRAILING_STOP'


def test_preview_accepts_a_built_mapping_and_preview_many_can_pause():
    client = Client()
    easy = EasyOrders(client, 'hash')

    with patch('schwab.orders.easy.time.sleep') as sleep:
        responses = easy.preview_many(
                ({'symbol': symbol} for symbol in ('AAPL', 'MSFT')),
                pause_between=0.25)

    assert len(responses) == 2
    assert client.calls[0][2] == {'symbol': 'AAPL'}
    sleep.assert_called_once_with(0.25)


def test_order_must_be_a_builder_or_mapping():
    with pytest.raises(TypeError):
        EasyOrders(Client(), 'hash').preview('not an order')


def test_place_requires_explicit_confirmation_before_any_request():
    client = Client()
    easy = EasyOrders(client, 'hash')

    with pytest.raises(LiveOrderConfirmationError):
        easy.place(easy.buy('AAPL', 1))

    assert client.calls == []


def test_failed_preview_prevents_placement():
    client = Client(preview_status=400)
    easy = EasyOrders(client, 'hash')

    result = easy.place(
            easy.buy('AAPL', 1), confirm_live_order=True)

    assert result.preview_response.status_code == 400
    assert result.place_response is None
    assert result.placed is False
    assert [call[0] for call in client.calls] == ['preview']


def test_successful_preview_is_followed_by_one_placement():
    client = Client()
    easy = EasyOrders(client, 'hash')

    result = easy.place(
            easy.buy('AAPL', 1), confirm_live_order=True)

    assert result.placed is True
    assert result.place_response.status_code == 201
    assert [call[0] for call in client.calls] == ['preview', 'place']


def test_preview_can_be_explicitly_skipped():
    client = Client()
    easy = EasyOrders(client, 'hash')

    result = easy.place(
            {'order': 'spec'}, confirm_live_order=True, preview=False)

    assert result.preview_response is None
    assert result.placed is True
    assert [call[0] for call in client.calls] == ['place']


def test_place_many_stops_after_first_failed_response():
    client = Client(place_status=429)
    easy = EasyOrders(client, 'hash')

    results = easy.place_many(
            (easy.buy(symbol, 1) for symbol in ('AAPL', 'MSFT')),
            confirm_live_order=True, preview=False)

    assert len(results) == 1
    assert [call[0] for call in client.calls] == ['place']


def test_place_many_can_continue_and_pause_between_independent_orders():
    client = Client(place_status=429)
    easy = EasyOrders(client, 'hash')

    with patch('schwab.orders.easy.time.sleep') as sleep:
        results = easy.place_many(
                [easy.buy('AAPL', 1), easy.buy('MSFT', 1)],
                confirm_live_order=True, preview=False,
                pause_between=0.5, stop_on_error=False)

    assert len(results) == 2
    assert [call[0] for call in client.calls] == ['place', 'place']
    sleep.assert_called_once_with(0.5)


@pytest.mark.parametrize('pause', [-1, True, 'one second'])
def test_batch_pause_must_be_a_non_negative_number(pause):
    with pytest.raises(ValueError):
        EasyOrders(Client(), 'hash').preview_many([], pause_between=pause)


def test_order_template_round_trip(tmp_path):
    path = tmp_path / 'orders' / 'aapl.json'
    order = EasyOrders(Client(), 'hash').buy(
            'AAPL', 2, limit_price='201.25')

    save_order_template(
            path, order, name='AAPL entry', description='Example')

    assert load_order_template(path) == order.build()
    document = json.loads(path.read_text(encoding='utf-8'))
    assert document['schemaVersion'] == 1
    assert document['name'] == 'AAPL entry'


def test_order_template_rejects_unknown_schema(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text(
            json.dumps({'schemaVersion': 2, 'order': {}}), encoding='utf-8')

    with pytest.raises(OrderTemplateError):
        load_order_template(path)


@pytest.mark.parametrize(
        'document',
        [[], {'schemaVersion': 1}, {'schemaVersion': 1, 'order': []}])
def test_order_template_rejects_invalid_document_shapes(tmp_path, document):
    path = tmp_path / 'bad-shape.json'
    path.write_text(json.dumps(document), encoding='utf-8')

    with pytest.raises(OrderTemplateError):
        load_order_template(path)


def test_async_workflow_previews_then_places():
    async def run():
        client = AsyncClient()
        easy = AsyncEasyOrders(client, 'hash')

        result = await easy.place(
                easy.buy('AAPL', 1), confirm_live_order=True)

        assert result.placed is True
        assert [call[0] for call in client.calls] == ['preview', 'place']

    asyncio.run(run())


def test_async_failed_preview_blocks_placement():
    async def run():
        client = AsyncClient(preview_status=400)
        easy = AsyncEasyOrders(client, 'hash')

        result = await easy.place(
                easy.buy('AAPL', 1), confirm_live_order=True)

        assert result.placed is False
        assert [call[0] for call in client.calls] == ['preview']

    asyncio.run(run())


def test_async_batches_pause_without_blocking_and_can_continue():
    async def run():
        client = AsyncClient(place_status=429)
        easy = AsyncEasyOrders(client, 'hash')
        orders = [easy.buy('AAPL', 1), easy.buy('MSFT', 1)]

        with patch('schwab.orders.easy.asyncio.sleep',
                   new=AsyncMock()) as sleep:
            previews = await easy.preview_many(orders, pause_between=0.25)
            placements = await easy.place_many(
                    orders, confirm_live_order=True, preview=False,
                    pause_between=0.5, stop_on_error=False)

        assert len(previews) == 2
        assert len(placements) == 2
        assert [call.args[0] for call in sleep.await_args_list] == [0.25, 0.5]

    asyncio.run(run())


def test_async_batch_stops_after_failed_placement():
    async def run():
        client = AsyncClient(place_status=429)
        easy = AsyncEasyOrders(client, 'hash')

        placements = await easy.place_many(
                [easy.buy('AAPL', 1), easy.buy('MSFT', 1)],
                confirm_live_order=True, preview=False)

        assert len(placements) == 1

    asyncio.run(run())
