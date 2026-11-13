'''Print normalized positions without exposing account numbers.'''

import os

from schwab.auth import client_from_token_file
from schwab.contrib.account import iter_position_rows


def main():
    client = client_from_token_file(
        os.environ['SCHWAB_TOKEN_PATH'],
        os.environ['SCHWAB_API_KEY'],
        os.environ['SCHWAB_APP_SECRET'])
    response = client.get_accounts(fields=[client.Account.Fields.POSITIONS])
    response.raise_for_status()

    for row in iter_position_rows(response.json()):
        print('{account} {symbol} {net_quantity} @ {average_price}'.format(
            **row))


if __name__ == '__main__':
    main()
