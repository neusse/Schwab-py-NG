'''Preview-first order construction with an explicit live-placement gate.

This example is safe in its checked-in form: ``CONFIRM_LIVE_ORDER`` is false,
so it stops after Schwab's preview response. Preview is validation, not paper
trading, and says nothing about a future fill.
'''

from schwab.auth import client_from_token_file
from schwab.orders.easy import EasyOrders
from schwab.utils import find_account_hash


API_KEY = 'XXXXXX'
APP_SECRET = 'XXXXXX'
TOKEN_PATH = './token.json'
ACCOUNT_NUMBER = 'XXXXXXXX'

SYMBOL = 'AAPL'
QUANTITY = 1
LIMIT_PRICE = '1.00'

# Change this only after reviewing the built order and preview. True sends a
# real order to a funded Schwab account.
CONFIRM_LIVE_ORDER = False


def main():
    client = client_from_token_file(
            TOKEN_PATH, api_key=API_KEY, app_secret=APP_SECRET)

    # Recover bounded read-only 429s. Returned order mutations are never
    # repeated automatically.
    client.set_rate_limit_retry(
            max_retries=3, backoff_factor=1.0, max_delay=30.0)

    accounts = client.get_account_numbers()
    accounts.raise_for_status()
    account_hash = find_account_hash(accounts.json(), ACCOUNT_NUMBER)

    orders = EasyOrders(client, account_hash)
    order = orders.buy(SYMBOL, QUANTITY, limit_price=LIMIT_PRICE)

    preview = orders.preview(order)
    preview.raise_for_status()
    print(preview.json())

    if not CONFIRM_LIVE_ORDER:
        print('preview complete; no order was placed')
        return

    submission = orders.place(order, confirm_live_order=True)
    if not submission.placed:
        submission.preview_response.raise_for_status()
    submission.place_response.raise_for_status()
    print('placement request accepted')


if __name__ == '__main__':
    main()
