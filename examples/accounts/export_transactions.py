'''Export all account transactions for a requested date range.'''

import argparse
import datetime
import os

from schwab.auth import client_from_token_file
from schwab.contrib.export import iter_transaction_rows, write_csv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('start', type=datetime.date.fromisoformat)
    parser.add_argument('end', type=datetime.date.fromisoformat)
    parser.add_argument('--output', default='schwab-transactions.csv')
    args = parser.parse_args()

    client = client_from_token_file(
        os.environ['SCHWAB_TOKEN_PATH'],
        os.environ['SCHWAB_API_KEY'],
        os.environ['SCHWAB_APP_SECRET'])
    collected = []
    accounts = client.get_account_numbers()
    accounts.raise_for_status()
    for account in accounts.json():
        response = client.get_transactions(
            account['hashValue'], start_date=args.start, end_date=args.end)
        response.raise_for_status()
        # The response does not carry the account number. Add it to a private
        # copy so the exporter can produce a masked account label.
        for transaction in response.json():
            transaction = dict(transaction)
            transaction['accountNumber'] = account['accountNumber']
            collected.append(transaction)

    count = write_csv(args.output, iter_transaction_rows(collected))
    print('wrote {} rows to {}'.format(count, args.output))


if __name__ == '__main__':
    main()
