'''Convert price history to dependency-free rows and optional DataFrame input.'''

import os

from schwab.auth import client_from_token_file
from schwab.contrib.market_data import iter_candle_rows


def main():
    client = client_from_token_file(
        os.environ['SCHWAB_TOKEN_PATH'],
        os.environ['SCHWAB_API_KEY'],
        os.environ['SCHWAB_APP_SECRET'])
    response = client.get_price_history_every_hour('AAPL')
    response.raise_for_status()
    rows = list(iter_candle_rows(response.json()))
    for row in rows[-5:]:
        print(row)

    # pandas is intentionally not an NG dependency. Applications which use it
    # can construct a DataFrame directly:
    # import pandas as pd
    # frame = pd.DataFrame(rows).set_index('datetime_utc')


if __name__ == '__main__':
    main()
