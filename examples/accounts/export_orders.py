'''Export order trees without flattening away child and leg identity.'''

import argparse
import datetime
import os

from schwab.auth import client_from_token_file
from schwab.contrib.export import iter_order_rows, write_csv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--output', default='schwab-orders.csv')
    args = parser.parse_args()
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(days=args.days)

    client = client_from_token_file(
        os.environ['SCHWAB_TOKEN_PATH'],
        os.environ['SCHWAB_API_KEY'],
        os.environ['SCHWAB_APP_SECRET'])
    response = client.get_orders_for_all_linked_accounts(
        from_entered_datetime=start, to_entered_datetime=end)
    response.raise_for_status()
    count = write_csv(args.output, iter_order_rows(response.json()))
    print('wrote {} rows to {}'.format(count, args.output))


if __name__ == '__main__':
    main()
