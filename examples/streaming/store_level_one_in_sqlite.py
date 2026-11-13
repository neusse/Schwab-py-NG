'''Store level-one equity updates without blocking the stream reader.'''

import asyncio
import json
import os
import sqlite3

from schwab.auth import client_from_token_file
from schwab.contrib.streaming import AsyncMessageConsumer
from schwab.streaming import StreamClient


class SqliteSink:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS stream_messages (
                id INTEGER PRIMARY KEY,
                service TEXT NOT NULL,
                symbol TEXT,
                received_timestamp INTEGER,
                payload_json TEXT NOT NULL
            )''')

    def __call__(self, message):
        service = str(message.get('service') or '')
        timestamp = message.get('timestamp')
        content = message.get('content') or [None]
        for item in content:
            symbol = item.get('key') if isinstance(item, dict) else None
            self.connection.execute(
                'INSERT INTO stream_messages '
                '(service, symbol, received_timestamp, payload_json) '
                'VALUES (?, ?, ?, ?)',
                (service, symbol, timestamp,
                 json.dumps(item, sort_keys=True, separators=(',', ':'))))
        self.connection.commit()

    def close(self):
        self.connection.close()


async def main():
    client = client_from_token_file(
        os.environ['SCHWAB_TOKEN_PATH'],
        os.environ['SCHWAB_API_KEY'],
        os.environ['SCHWAB_APP_SECRET'])
    stream = StreamClient(client)
    sink = SqliteSink('schwab-stream.sqlite3')
    consumer = AsyncMessageConsumer(
        sink, max_queue_size=1000, overflow='drop_oldest')
    worker = asyncio.create_task(consumer.run())
    stream.add_level_one_equity_handler(consumer.handler)

    try:
        await stream.login()
        await stream.level_one_equity_subs(['AAPL', 'MSFT'])
        while True:
            await stream.handle_message()
    finally:
        await stream.close()
        await consumer.close()
        await worker
        sink.close()


if __name__ == '__main__':
    asyncio.run(main())
