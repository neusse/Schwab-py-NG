'''A guided, safety-first workflow around Schwab-py-NG order builders.

This module adapts the useful workflow ideas from the MIT-licensed
``neusse/Schwab_EZ_Orders`` project. It deliberately reuses this package's
existing order builders and raw-response contract instead of maintaining a
second order schema.
'''

from collections.abc import Mapping
from dataclasses import dataclass, field
import asyncio
import json
import os
from pathlib import Path
import tempfile
import time

from .common import (StopPriceLinkBasis, StopPriceLinkType,
                     first_triggers_second, one_cancels_other)
from .equities import (equity_buy_limit, equity_buy_market, equity_sell_limit,
                       equity_sell_market, equity_sell_stop,
                       equity_sell_trailing_stop)
from .generic import OrderBuilder
from ..utils import SchwabError


class LiveOrderConfirmationError(SchwabError):
    '''Raised when a caller tries to mutate a live order without confirmation.'''


class OrderTemplateError(SchwabError):
    '''Raised when a saved order template has an unsupported or invalid shape.'''


@dataclass(frozen=True)
class OrderSubmission:
    '''The responses from a preview-before-place workflow.

    ``place_response`` is ``None`` when Schwab refused the preview, so callers
    can inspect ``preview_response`` without wondering whether an order was
    sent. A successful preview is not a fill simulation and does not mean the
    eventual order will be accepted or executed.
    '''

    preview_response: object | None
    place_response: object | None
    placed: bool = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'placed', self.place_response is not None)


def _order_spec(order):
    if isinstance(order, OrderBuilder):
        return order.build()
    if isinstance(order, Mapping):
        return dict(order)
    raise TypeError('order must be an OrderBuilder or mapping')


def save_order_template(path, order, *, name=None, description=None):
    '''Atomically save an order specification to an explicit JSON path.

    The caller owns the path and the file's lifecycle. The library does not
    create a global template directory or silently retain order history.
    '''
    path = Path(path)
    document = {
        'schemaVersion': 1,
        'name': name,
        'description': description,
        'order': _order_spec(order),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', dir=path.parent,
                prefix='.' + path.name + '.', suffix='.tmp',
                delete=False) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(document, temporary, indent=2)
            temporary.write('\n')
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        raise


def load_order_template(path):
    '''Load and validate an order specification saved by this module.'''
    with Path(path).open('r', encoding='utf-8') as template_file:
        document = json.load(template_file)

    if not isinstance(document, dict):
        raise OrderTemplateError('order template must be a JSON object')
    if document.get('schemaVersion') != 1:
        raise OrderTemplateError('unsupported order template schema version')
    order = document.get('order')
    if not isinstance(order, dict):
        raise OrderTemplateError('order template must contain an order object')
    return order


class EasyOrders:
    '''Build, preview and deliberately place orders for one account.

    The client and account hash are accepted rather than created, so this
    module never owns credentials, tokens or sessions. Low-level callers can
    continue using :class:`~schwab.client.Client` directly.
    '''

    def __init__(self, client, account_hash):
        self.client = client
        self.account_hash = account_hash

    def buy(self, symbol, quantity, *, limit_price=None):
        '''Build a market buy, or a limit buy when ``limit_price`` is set.'''
        if limit_price is None:
            return equity_buy_market(symbol, quantity)
        return equity_buy_limit(symbol, quantity, limit_price)

    def sell(self, symbol, quantity, *, limit_price=None):
        '''Build a market sell, or a limit sell when ``limit_price`` is set.'''
        if limit_price is None:
            return equity_sell_market(symbol, quantity)
        return equity_sell_limit(symbol, quantity, limit_price)

    def stop_loss(self, symbol, quantity, stop_price):
        '''Build a sell stop for an existing long equity position.'''
        return equity_sell_stop(symbol, quantity, stop_price)

    def trailing_stop_loss(
            self, symbol, quantity, offset, *,
            offset_type=StopPriceLinkType.VALUE,
            basis=StopPriceLinkBasis.LAST):
        '''Build a trailing sell stop for an existing long equity position.'''
        return equity_sell_trailing_stop(
                symbol, quantity, offset, offset_type, basis)

    def bracket(self, symbol, quantity, *, entry_price, profit_price,
                stop_price):
        '''Build a limit entry which triggers profit-target/stop-loss OCO exits.'''
        entry = equity_buy_limit(symbol, quantity, entry_price)
        exits = one_cancels_other(
                equity_sell_limit(symbol, quantity, profit_price),
                equity_sell_stop(symbol, quantity, stop_price))
        return first_triggers_second(entry, exits)

    def preview(self, order):
        '''Ask Schwab to validate an order without placing it.'''
        return self.client.preview_order(self.account_hash, _order_spec(order))

    def preview_many(self, orders, *, pause_between=0.0):
        '''Preview orders sequentially, optionally pausing between requests.'''
        pause_between = self._validated_pause(pause_between)
        orders = list(orders)
        responses = []
        for index, order in enumerate(orders):
            responses.append(self.preview(order))
            if pause_between and index + 1 < len(orders):
                time.sleep(pause_between)
        return responses

    def place(self, order, *, confirm_live_order=False, preview=True):
        '''Preview and place one order after explicit live-order confirmation.

        When ``preview`` is true and Schwab refuses the preview, placement is
        skipped and the returned :class:`OrderSubmission` contains only the
        preview response. The placement response is returned raw and is never
        automatically retried by this workflow.
        '''
        self._require_live_confirmation(confirm_live_order)
        order_spec = _order_spec(order)

        preview_response = None
        if preview:
            preview_response = self.client.preview_order(
                    self.account_hash, order_spec)
            if not preview_response.is_success:
                return OrderSubmission(preview_response, None)

        place_response = self.client.place_order(self.account_hash, order_spec)
        return OrderSubmission(preview_response, place_response)

    def place_many(self, orders, *, confirm_live_order=False, preview=True,
                   pause_between=0.0, stop_on_error=True):
        '''Place orders sequentially under one explicit confirmation.

        A failed preview or placement response stops the sequence by default.
        No failed mutation is repeated automatically.
        '''
        self._require_live_confirmation(confirm_live_order)
        pause_between = self._validated_pause(pause_between)
        orders = list(orders)
        submissions = []

        for index, order in enumerate(orders):
            submission = self.place(
                    order, confirm_live_order=True, preview=preview)
            submissions.append(submission)
            response = (submission.place_response
                        if submission.place_response is not None
                        else submission.preview_response)
            if (stop_on_error and response is not None
                    and not response.is_success):
                break
            if pause_between and index + 1 < len(orders):
                time.sleep(pause_between)
        return submissions

    @staticmethod
    def _require_live_confirmation(confirm_live_order):
        if confirm_live_order is not True:
            raise LiveOrderConfirmationError(
                    'live Schwab order placement requires '
                    'confirm_live_order=True')

    @staticmethod
    def _validated_pause(pause_between):
        if (isinstance(pause_between, bool)
                or not isinstance(pause_between, (int, float))
                or pause_between < 0):
            raise ValueError('pause_between must be a non-negative number')
        return float(pause_between)


class AsyncEasyOrders(EasyOrders):
    '''The non-blocking ``asyncio`` counterpart to :class:`EasyOrders`.'''

    async def preview(self, order):
        '''Ask Schwab to validate an order without placing it.'''
        return await self.client.preview_order(
                self.account_hash, _order_spec(order))

    async def preview_many(self, orders, *, pause_between=0.0):
        '''Preview orders sequentially, optionally pausing between requests.'''
        pause_between = self._validated_pause(pause_between)
        orders = list(orders)
        responses = []
        for index, order in enumerate(orders):
            responses.append(await self.preview(order))
            if pause_between and index + 1 < len(orders):
                await asyncio.sleep(pause_between)
        return responses

    async def place(self, order, *, confirm_live_order=False, preview=True):
        '''Preview and place one order after explicit live-order confirmation.'''
        self._require_live_confirmation(confirm_live_order)
        order_spec = _order_spec(order)

        preview_response = None
        if preview:
            preview_response = await self.client.preview_order(
                    self.account_hash, order_spec)
            if not preview_response.is_success:
                return OrderSubmission(preview_response, None)

        place_response = await self.client.place_order(
                self.account_hash, order_spec)
        return OrderSubmission(preview_response, place_response)

    async def place_many(self, orders, *, confirm_live_order=False,
                         preview=True, pause_between=0.0,
                         stop_on_error=True):
        '''Place orders sequentially under one explicit confirmation.'''
        self._require_live_confirmation(confirm_live_order)
        pause_between = self._validated_pause(pause_between)
        orders = list(orders)
        submissions = []

        for index, order in enumerate(orders):
            submission = await self.place(
                    order, confirm_live_order=True, preview=preview)
            submissions.append(submission)
            response = (submission.place_response
                        if submission.place_response is not None
                        else submission.preview_response)
            if (stop_on_error and response is not None
                    and not response.is_success):
                break
            if pause_between and index + 1 < len(orders):
                await asyncio.sleep(pause_between)
        return submissions
