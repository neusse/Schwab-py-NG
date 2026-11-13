'''Poll and print normalized positions with no pandas or Rich dependency.'''

import argparse
import os
import time

from schwab.auth import client_from_token_file
from schwab.contrib.account import iter_position_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=float, default=60)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error('--interval must be positive')

    client = client_from_token_file(
        os.environ['SCHWAB_TOKEN_PATH'],
        os.environ['SCHWAB_API_KEY'],
        os.environ['SCHWAB_APP_SECRET'])
    while True:
        response = client.get_accounts(fields=[client.Account.Fields.POSITIONS])
        response.raise_for_status()
        print('\nAccount      Symbol                 Quantity       Market value')
        for row in iter_position_rows(response.json()):
            print('{account:<12} {symbol:<20} {net_quantity:>12} '
                  '{market_value:>18}'.format(**row))
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
