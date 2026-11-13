'''Normalize Schwab account and position payloads without owning a client.

The functions in this module accept already-decoded response bodies.  They do
not authenticate, make requests, retain a token, or require a dataframe
library.  That keeps the seam between fetching account data and interpreting
it explicit and makes the same normalization useful to synchronous and
asynchronous callers.
'''

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Mapping


ZERO = Decimal('0')


def _decimal(value, field):
    if value is None:
        return ZERO
    if isinstance(value, bool):
        raise ValueError('{} must be a number, not bool'.format(field))
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('{} must be a finite number'.format(field)) from exc
    if not result.is_finite():
        raise ValueError('{} must be a finite number'.format(field))
    return result


def account_suffix(account_number, visible=3):
    '''Return the trailing characters used to identify an account safely.

    The Schwab web interface convention is the final three account-number
    characters. ``visible`` exists for callers with a different local
    convention; it must be a positive integer.
    '''
    if account_number in (None, ''):
        return ''
    if isinstance(visible, bool) or not isinstance(visible, int) or visible < 1:
        raise ValueError('visible must be a positive integer')
    return str(account_number)[-visible:]


def mask_account_number(account_number, visible=3):
    '''Mask an account number, leaving at most ``visible`` trailing characters.

    ``None`` and the empty string produce ``'Unknown'``.  The complete value is
    never returned, even when it is shorter than ``visible``.
    '''
    if account_number in (None, ''):
        return 'Unknown'
    if isinstance(visible, bool) or not isinstance(visible, int) or visible < 1:
        raise ValueError('visible must be a positive integer')
    value = str(account_number)
    shown_length = min(visible, max(0, len(value) - 1))
    shown = value[-shown_length:] if shown_length else ''
    return '...' + shown


@dataclass(frozen=True)
class AccountIdentity:
    '''Stable join key and safe display label for one Schwab account.'''

    account_key: str
    display_label: str
    account_suffix: str = ''


@dataclass(frozen=True, order=True)
class PositionIdentity:
    '''Fields which distinguish one held instrument from another.'''

    asset_type: str
    symbol: str
    cusip: str
    instrument_id: str
    put_call: str
    underlying_symbol: str


@dataclass(frozen=True)
class Position:
    '''A normalized position whose quantities retain their long/short signs.'''

    account_key: str | None
    identity: PositionIdentity
    description: str
    long_quantity: Decimal
    short_quantity: Decimal
    market_value: Decimal
    average_price: Decimal
    day_profit_loss: Decimal
    long_open_profit_loss: Decimal
    short_open_profit_loss: Decimal

    @property
    def net_quantity(self):
        '''Long quantity minus short quantity.'''
        return self.long_quantity - self.short_quantity


@dataclass(frozen=True)
class AccountSnapshot:
    '''One account identity and its positions at one response instant.'''

    identity: AccountIdentity
    positions: tuple[Position, ...]


@dataclass(frozen=True)
class PositionChange:
    '''Before/after values for one instrument in one account.'''

    account_key: str | None
    identity: PositionIdentity
    before: Position | None
    after: Position | None

    @property
    def quantity_change(self):
        '''Signed change in net quantity.'''
        before = self.before.net_quantity if self.before else ZERO
        after = self.after.net_quantity if self.after else ZERO
        return after - before

    @property
    def market_value_change(self):
        '''Change in reported market value.'''
        before = self.before.market_value if self.before else ZERO
        after = self.after.market_value if self.after else ZERO
        return after - before


def _account_info(account):
    if not isinstance(account, Mapping):
        raise ValueError('each account must be an object')
    info = account.get('securitiesAccount', account)
    if not isinstance(info, Mapping):
        raise ValueError('securitiesAccount must be an object')
    return info


def _identity(account, info):
    key = (account.get('hashValue') or info.get('hashValue')
           or info.get('accountId') or info.get('accountNumber'))
    if key in (None, ''):
        raise ValueError('account payload has no stable identifier')
    number = info.get('accountNumber', account.get('accountNumber'))
    return AccountIdentity(
        str(key), mask_account_number(number), account_suffix(number))


def _position(account_key, raw):
    if not isinstance(raw, Mapping):
        raise ValueError('each position must be an object')
    instrument = raw.get('instrument', {})
    if not isinstance(instrument, Mapping):
        raise ValueError('position instrument must be an object')
    identity = PositionIdentity(
        str(instrument.get('assetType') or instrument.get('assetMainType') or ''),
        str(instrument.get('symbol') or ''),
        str(instrument.get('cusip') or ''),
        str(instrument.get('instrumentId') or ''),
        str(instrument.get('putCall') or ''),
        str(instrument.get('underlyingSymbol') or ''),
    )
    if not any((identity.symbol, identity.cusip, identity.instrument_id)):
        raise ValueError('position instrument has no symbol, CUSIP, or id')
    return Position(
        account_key=account_key,
        identity=identity,
        description=str(instrument.get('description') or ''),
        long_quantity=_decimal(raw.get('longQuantity'), 'longQuantity'),
        short_quantity=_decimal(raw.get('shortQuantity'), 'shortQuantity'),
        market_value=_decimal(raw.get('marketValue'), 'marketValue'),
        average_price=_decimal(raw.get('averagePrice'), 'averagePrice'),
        day_profit_loss=_decimal(
            raw.get('currentDayProfitLoss'), 'currentDayProfitLoss'),
        long_open_profit_loss=_decimal(
            raw.get('longOpenProfitLoss'), 'longOpenProfitLoss'),
        short_open_profit_loss=_decimal(
            raw.get('shortOpenProfitLoss'), 'shortOpenProfitLoss'),
    )


def account_snapshots(payload):
    '''Return normalized snapshots from ``get_account(s)`` response JSON.'''
    accounts = payload if isinstance(payload, (list, tuple)) else [payload]
    snapshots = []
    for account in accounts:
        info = _account_info(account)
        identity = _identity(account, info)
        positions = info.get('positions') or ()
        if not isinstance(positions, (list, tuple)):
            raise ValueError('positions must be an array')
        normalized = tuple(_position(identity.account_key, p)
                           for p in positions)
        snapshots.append(AccountSnapshot(identity, normalized))
    return tuple(snapshots)


def _combine(left, right):
    description = left.description or right.description
    return replace(
        left,
        description=description,
        long_quantity=left.long_quantity + right.long_quantity,
        short_quantity=left.short_quantity + right.short_quantity,
        market_value=left.market_value + right.market_value,
        # Average price is meaningful per source position.  Across accounts or
        # duplicate lots, weight it by absolute quantity rather than adding it.
        average_price=_weighted_average(left, right),
        day_profit_loss=left.day_profit_loss + right.day_profit_loss,
        long_open_profit_loss=(left.long_open_profit_loss
                               + right.long_open_profit_loss),
        short_open_profit_loss=(left.short_open_profit_loss
                                + right.short_open_profit_loss),
    )


def _weighted_average(left, right):
    left_q = left.long_quantity + left.short_quantity
    right_q = right.long_quantity + right.short_quantity
    total = left_q + right_q
    if not total:
        return ZERO
    return ((left.average_price * left_q + right.average_price * right_q)
            / total)


def aggregate_positions(snapshots):
    '''Aggregate equal instruments across snapshots without collapsing symbols.

    The returned positions have ``account_key=None`` to make the loss of the
    per-account dimension explicit.
    '''
    combined = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, AccountSnapshot):
            raise TypeError('snapshots must contain AccountSnapshot values')
        for position in snapshot.positions:
            value = replace(position, account_key=None)
            previous = combined.get(value.identity)
            combined[value.identity] = (
                value if previous is None else _combine(previous, value))
    return tuple(combined[key] for key in sorted(combined))


def _positions_by_key(snapshots):
    indexed = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, AccountSnapshot):
            raise TypeError('snapshots must contain AccountSnapshot values')
        for position in snapshot.positions:
            key = (position.account_key, position.identity)
            previous = indexed.get(key)
            indexed[key] = (position if previous is None
                            else _combine(previous, position))
    return indexed


def diff_positions(before, after):
    '''Return position changes between two collections of account snapshots.'''
    old = _positions_by_key(before)
    new = _positions_by_key(after)
    changes = []
    for key in sorted(set(old) | set(new), key=lambda item: (
            '' if item[0] is None else item[0], item[1])):
        if old.get(key) != new.get(key):
            changes.append(PositionChange(key[0], key[1], old.get(key),
                                          new.get(key)))
    return tuple(changes)


def iter_position_rows(payload, *, include_account_key=False):
    '''Yield plain dictionaries suitable for CSV or dataframe construction.

    Account identifiers are excluded by default; the masked ``account`` label
    is still present. Set ``include_account_key=True`` only for a private
    export which needs to join back to another Schwab response.
    '''
    for snapshot in account_snapshots(payload):
        for index, position in enumerate(snapshot.positions):
            identity = position.identity
            row = {
                'account': snapshot.identity.display_label,
                'account_suffix': snapshot.identity.account_suffix,
                'position_index': index,
                'asset_type': identity.asset_type,
                'symbol': identity.symbol,
                'cusip': identity.cusip,
                'instrument_id': identity.instrument_id,
                'put_call': identity.put_call,
                'underlying_symbol': identity.underlying_symbol,
                'description': position.description,
                'long_quantity': position.long_quantity,
                'short_quantity': position.short_quantity,
                'net_quantity': position.net_quantity,
                'market_value': position.market_value,
                'average_price': position.average_price,
                'day_profit_loss': position.day_profit_loss,
                'long_open_profit_loss': position.long_open_profit_loss,
                'short_open_profit_loss': position.short_open_profit_loss,
            }
            if include_account_key:
                row['account_key'] = snapshot.identity.account_key
            yield row
