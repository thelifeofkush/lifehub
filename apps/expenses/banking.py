"""Plaid connection and atomic, cursor-based transaction imports."""
import asyncio
import hashlib
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from core.db import db

LOCK = threading.Lock()


class BankError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def environment():
    return os.getenv('PLAID_ENV', 'sandbox')


def cipher():
    try:
        return Fernet(os.environ['LIFEHUB_ENCRYPTION_KEY'].encode())
    except (KeyError, ValueError):
        raise BankError('ENCRYPTION_KEY_REQUIRED') from None


def setup_problem():
    if not os.getenv('LIFEHUB_USERNAME') or not os.getenv('LIFEHUB_PASSWORD'):
        return 'Set a LifeHub username and password before connecting a bank.'
    if environment() not in ('sandbox', 'production'):
        return 'PLAID_ENV must be sandbox or production.'
    if not os.getenv('PLAID_CLIENT_ID') or not os.getenv('PLAID_SECRET'):
        return 'Add your Plaid client ID and secret to the server configuration.'
    try:
        cipher()
    except BankError:
        return 'Set a valid LIFEHUB_ENCRYPTION_KEY before connecting a bank.'
    public_url = os.getenv('LIFEHUB_PUBLIC_URL', '').rstrip('/')
    parsed = urlsplit(public_url)
    if (parsed.scheme not in ('http', 'https') or not parsed.netloc
            or parsed.path or parsed.query or parsed.fragment or parsed.username):
        return 'Set LIFEHUB_PUBLIC_URL to the origin used to open LifeHub.'
    if environment() == 'production' and parsed.scheme != 'https':
        return 'Production bank linking requires an HTTPS LifeHub URL.'
    return None


def call(endpoint, **payload):
    if environment() not in ('sandbox', 'production'):
        raise BankError('INVALID_ENVIRONMENT')
    try:
        response = httpx.post(f'https://{environment()}.plaid.com{endpoint}', json={
            'client_id': os.getenv('PLAID_CLIENT_ID'),
            'secret': os.getenv('PLAID_SECRET'), **payload,
        }, headers={'Plaid-Version': '2020-09-14'}, timeout=40)
        result = response.json()
    except (httpx.HTTPError, ValueError):
        raise BankError('CONNECTION_FAILED') from None
    if response.is_error or result.get('error_code'):
        # Never return provider messages or tokens to logs/browser.
        code = result.get('error_code', 'PROVIDER_ERROR')
        allowed = {'ITEM_LOGIN_REQUIRED', 'TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION',
                   'PRODUCT_NOT_READY', 'RATE_LIMIT_EXCEEDED', 'INVALID_PUBLIC_TOKEN'}
        raise BankError(code if code in allowed else 'PROVIDER_ERROR')
    return result


def init_bank_db(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS expenses_bank_items (
        item_id TEXT PRIMARY KEY, token TEXT NOT NULL, environment TEXT NOT NULL,
        cursor TEXT, last_sync TEXT, error TEXT,
        exchange_hash TEXT UNIQUE)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS expenses_bank_transactions (
        transaction_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, account_id TEXT NOT NULL,
        day TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
        cents INTEGER NOT NULL, currency TEXT NOT NULL, pending INTEGER NOT NULL,
        kind TEXT NOT NULL, override_kind TEXT)''')


def access_token(item):
    try:
        return cipher().decrypt(item['token'].encode()).decode()
    except InvalidToken:
        raise BankError('ENCRYPTION_KEY_MISMATCH') from None


def create_link_token(item_id=None):
    payload = dict(client_name='LifeHub', language='en', country_codes=['US'],
                   user={'client_user_id': hashlib.sha256(os.environ['LIFEHUB_ENCRYPTION_KEY'].encode()).hexdigest()},
                   redirect_uri=os.environ['LIFEHUB_PUBLIC_URL'].rstrip('/') + '/expenses/oauth')
    if item_id:
        with db() as conn:
            item = conn.execute('SELECT * FROM expenses_bank_items WHERE item_id=? AND environment=?',
                                (item_id, environment())).fetchone()
        if not item:
            raise BankError('ITEM_NOT_FOUND')
        payload['access_token'] = access_token(item)
    else:
        payload['products'] = ['transactions']
        payload['transactions'] = {'days_requested': 90}
    return call('/link/token/create', **payload)['link_token']


def exchange(public_token):
    digest = hashlib.sha256(public_token.encode()).hexdigest()
    with LOCK:
        with db() as conn:
            existing = conn.execute('SELECT item_id FROM expenses_bank_items WHERE exchange_hash=?', (digest,)).fetchone()
        if existing:
            return existing['item_id']
        result = call('/item/public_token/exchange', public_token=public_token)
        encrypted = cipher().encrypt(result['access_token'].encode()).decode()
        with db() as conn:
            conn.execute('''INSERT INTO expenses_bank_items(item_id, token, environment, exchange_hash)
                VALUES (?, ?, ?, ?)''', (result['item_id'], encrypted, environment(), digest))
        return result['item_id']


def classify(transaction):
    category = transaction.get('personal_finance_category') or {}
    primary = category.get('primary', '')
    detailed = category.get('detailed', '')
    if primary in ('TRANSFER_IN', 'TRANSFER_OUT') or detailed == 'LOAN_PAYMENTS_CREDIT_CARD_PAYMENT':
        return 'transfer'
    if Decimal(str(transaction['amount'])) < 0:
        return 'income' if primary == 'INCOME' else 'refund'
    return 'expense'


def sync_item(item_id):
    with LOCK:
        with db() as conn:
            item = conn.execute('SELECT * FROM expenses_bank_items WHERE item_id=? AND environment=?',
                                (item_id, environment())).fetchone()
        if not item:
            raise BankError('ITEM_NOT_FOUND')
        try:
            token = access_token(item)
            # Nothing is persisted until all pages have succeeded. A mutation
            # error retries the entire batch from the original committed cursor.
            for attempt in range(3):
                cursor = item['cursor']
                changes, removed = {}, set()
                try:
                    for page_number in range(1000):
                        payload = dict(access_token=token, count=500)
                        if cursor:
                            payload['cursor'] = cursor
                        page = call('/transactions/sync', **payload)
                        for transaction in page['added'] + page['modified']:
                            changes[transaction['transaction_id']] = transaction
                            removed.discard(transaction['transaction_id'])
                        for transaction in page['removed']:
                            tid = transaction['transaction_id']
                            changes.pop(tid, None)
                            removed.add(tid)
                        cursor = page['next_cursor']
                        if not page['has_more']:
                            break
                    else:
                        raise BankError('TOO_MANY_PAGES')
                    break
                except BankError as exc:
                    if exc.code != 'TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION' or attempt == 2:
                        raise
            with db() as conn:
                for tid in removed:
                    conn.execute('DELETE FROM expenses_bank_transactions WHERE transaction_id=? AND item_id=?', (tid, item_id))
                for transaction in changes.values():
                    category = transaction.get('personal_finance_category') or {}
                    conn.execute('''INSERT INTO expenses_bank_transactions
                        (transaction_id, item_id, account_id, day, description, category, cents, currency, pending, kind)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(transaction_id) DO UPDATE SET
                        day=excluded.day, description=excluded.description, category=excluded.category,
                        cents=excluded.cents, currency=excluded.currency, pending=excluded.pending,
                        kind=excluded.kind''', (
                        transaction['transaction_id'], item_id, transaction['account_id'], transaction['date'],
                        transaction.get('merchant_name') or transaction.get('name') or 'Transaction',
                        category.get('detailed') or category.get('primary') or 'Uncategorized',
                        int((Decimal(str(transaction['amount'])) * 100).quantize(Decimal('1'))),
                        transaction.get('iso_currency_code') or transaction.get('unofficial_currency_code') or 'Unknown',
                        bool(transaction['pending']), classify(transaction)))
                conn.execute('UPDATE expenses_bank_items SET cursor=?, last_sync=?, error=NULL WHERE item_id=?',
                             (cursor, datetime.now(timezone.utc).isoformat(timespec='seconds'), item_id))
        except BankError as exc:
            with db() as conn:
                conn.execute('UPDATE expenses_bank_items SET error=? WHERE item_id=?', (exc.code, item_id))
            raise


def sync_all():
    if setup_problem():
        return
    with db() as conn:
        items = conn.execute('SELECT item_id FROM expenses_bank_items WHERE environment=?', (environment(),)).fetchall()
    for item in items:
        try:
            sync_item(item['item_id'])
        except BankError:
            pass  # Safe error code persisted for the dashboard; retry next cycle.


async def background_sync():
    while True:
        try:
            await asyncio.to_thread(sync_all)
        except Exception:
            # Keep the scheduler alive without logging financial payloads.
            import logging
            logging.getLogger(__name__).warning('Bank sync could not complete; will retry.')
        try:
            interval = max(300, int(os.getenv('PLAID_SYNC_INTERVAL_SECONDS', '3600')))
        except ValueError:
            interval = 3600
        await asyncio.sleep(interval)


def disconnect(item_id):
    with LOCK:
        with db() as conn:
            item = conn.execute('SELECT * FROM expenses_bank_items WHERE item_id=? AND environment=?',
                                (item_id, environment())).fetchone()
        if not item:
            raise BankError('ITEM_NOT_FOUND')
        call('/item/remove', access_token=access_token(item))
        with db() as conn:
            conn.execute('DELETE FROM expenses_bank_transactions WHERE item_id=?', (item_id,))
            conn.execute('DELETE FROM expenses_bank_items WHERE item_id=?', (item_id,))
