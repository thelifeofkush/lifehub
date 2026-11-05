import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from apps.expenses import banking, init_db
from core.db import db
from core.main import app
from core.web import today


def transaction(tid, amount=10, primary='FOOD_AND_DRINK', detailed='FOOD_AND_DRINK_GROCERIES', **extra):
    return dict(transaction_id=tid, account_id='account-1', date=today(),
                name='Test merchant', amount=amount, pending=False, iso_currency_code='USD',
                personal_finance_category={'primary': primary, 'detailed': detailed}, **extra)


def page(added=(), modified=(), removed=(), cursor='next', more=False):
    return dict(added=list(added), modified=list(modified),
                removed=[{'transaction_id': tid} for tid in removed],
                next_cursor=cursor, has_more=more)


class BankTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'DATA_DIR': self.directory.name, 'LIFEHUB_USERNAME': 'owner',
            'LIFEHUB_PASSWORD': 'test-password', 'LIFEHUB_ENCRYPTION_KEY': Fernet.generate_key().decode(),
            'PLAID_CLIENT_ID': 'test-client', 'PLAID_SECRET': 'test-secret',
            'PLAID_ENV': 'sandbox', 'LIFEHUB_PUBLIC_URL': 'http://testserver',
        })
        self.env.start()
        with db() as conn:
            init_db(conn)
        self.seed_item()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def seed_item(self):
        with db() as conn:
            conn.execute('INSERT INTO expenses_bank_items(item_id, token, environment, cursor) VALUES (?, ?, ?, ?)',
                         ('item-1', banking.cipher().encrypt(b'secret-access-token').decode(), 'sandbox', 'original'))

    def stored(self):
        with db() as conn:
            return conn.execute('SELECT * FROM expenses_bank_transactions ORDER BY transaction_id').fetchall()

    def test_pagination_updates_removals_and_idempotency(self):
        first, second = transaction('a'), transaction('b', -500, 'INCOME')
        with patch.object(banking, 'call', side_effect=[page([first], cursor='middle', more=True), page([second])]) as api:
            banking.sync_item('item-1')
        self.assertEqual(api.call_args_list[1].kwargs['cursor'], 'middle')
        self.assertEqual(len(self.stored()), 2)
        with db() as conn:
            conn.execute("UPDATE expenses_bank_transactions SET override_kind='transfer' WHERE transaction_id='a'")
        with patch.object(banking, 'call', return_value=page([first], modified=[{**first, 'amount': 15}], removed=['b'])):
            banking.sync_item('item-1')
            banking.sync_item('item-1')
        rows = self.stored()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['cents'], 1500)
        self.assertEqual(rows[0]['override_kind'], 'transfer')

    def test_failed_page_never_commits_partial_data_or_cursor(self):
        with patch.object(banking, 'call', side_effect=[page([transaction('a')], more=True), banking.BankError('CONNECTION_FAILED')]):
            with self.assertRaises(banking.BankError):
                banking.sync_item('item-1')
        self.assertEqual(self.stored(), [])
        with db() as conn:
            item = conn.execute('SELECT * FROM expenses_bank_items').fetchone()
        self.assertEqual(item['cursor'], 'original')
        self.assertEqual(item['error'], 'CONNECTION_FAILED')
        self.assertIsNone(item['last_sync'])

    def test_pagination_mutation_restarts_from_committed_cursor(self):
        with patch.object(banking, 'call', side_effect=[
            page([transaction('discard')], cursor='middle', more=True),
            banking.BankError('TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION'),
            page([transaction('keep')]),
        ]) as api:
            banking.sync_item('item-1')
        self.assertEqual(api.call_args_list[2].kwargs['cursor'], 'original')
        self.assertEqual([row['transaction_id'] for row in self.stored()], ['keep'])

    def test_tokens_encrypted_and_exchange_retries_deduplicated(self):
        with patch.object(banking, 'call', return_value={'item_id': 'item-2', 'access_token': 'new-private-token'}) as api:
            self.assertEqual(banking.exchange('public-test'), 'item-2')
            self.assertEqual(banking.exchange('public-test'), 'item-2')
        self.assertEqual(api.call_count, 1)
        with db() as conn:
            item = conn.execute("SELECT * FROM expenses_bank_items WHERE item_id='item-2'").fetchone()
        self.assertNotIn('new-private-token', item['token'])
        self.assertEqual(banking.access_token(item), 'new-private-token')
        with patch.dict(os.environ, {'LIFEHUB_ENCRYPTION_KEY': Fernet.generate_key().decode()}):
            with self.assertRaises(banking.BankError) as error:
                banking.access_token(item)
        self.assertEqual(error.exception.code, 'ENCRYPTION_KEY_MISMATCH')

    def test_pending_replaced_by_posted(self):
        pending = {**transaction('pending'), 'pending': True}
        with patch.object(banking, 'call', return_value=page([pending])):
            banking.sync_item('item-1')
        with patch.object(banking, 'call', return_value=page([transaction('posted', 11)], removed=['pending'])):
            banking.sync_item('item-1')
        self.assertEqual([row['transaction_id'] for row in self.stored()], ['posted'])

    def test_disconnect_revokes_before_deleting_and_failure_retains(self):
        with patch.object(banking, 'call', side_effect=banking.BankError('CONNECTION_FAILED')):
            with self.assertRaises(banking.BankError):
                banking.disconnect('item-1')
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM expenses_bank_items').fetchone()[0], 1)
        with patch.object(banking, 'call', return_value={}) as api:
            banking.disconnect('item-1')
        self.assertEqual(api.call_args.args[0], '/item/remove')
        with db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM expenses_bank_items').fetchone()[0], 0)

    def test_old_expenses_migrate_without_data_loss(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('CREATE TABLE expenses_items (id INTEGER PRIMARY KEY, day TEXT, description TEXT, category TEXT, cents INTEGER)')
            conn.execute("INSERT INTO expenses_items VALUES (1, '2026-01-01', 'Old record', 'Food', 1234)")
            init_db(conn)
            init_db(conn)
            row = conn.execute('SELECT * FROM expenses_items').fetchone()
            self.assertEqual((row['description'], row['cents'], row['kind']), ('Old record', 1234, 'expense'))
        finally:
            conn.close()

    def test_bank_of_america_oauth_link_configuration(self):
        with patch.object(banking, 'call', return_value={'link_token': 'link-test'}) as api:
            banking.create_link_token()
        payload = api.call_args.kwargs
        self.assertEqual(payload['country_codes'], ['US'])
        self.assertEqual(payload['products'], ['transactions'])
        self.assertEqual(payload['redirect_uri'], 'http://testserver/expenses/oauth')
        with patch.dict(os.environ, {'PLAID_ENV': 'production'}):
            self.assertIn('HTTPS', banking.setup_problem())

    def test_authenticated_api_session_and_cash_flow(self):
        # No real provider requests: mock the scheduled sync for the client lifespan.
        with patch.object(banking, 'sync_all'), TestClient(app) as client:
            self.assertEqual(client.get('/expenses/').status_code, 401)
            self.assertEqual(client.get('/health').status_code, 200)
            client.auth = ('owner', 'test-password')
            self.assertEqual(client.post('/expenses/bank/link', json={}).status_code, 403)
            headers = {'X-LifeHub': '1'}
            self.assertEqual(client.post('/expenses/bank/link', json={}, headers={**headers, 'Origin': 'https://evil.test'}).status_code, 403)
            with patch.object(banking, 'create_link_token', return_value='link-test'):
                self.assertEqual(client.post('/expenses/bank/link', json={}, headers=headers).status_code, 200)
            self.assertEqual(client.post('/expenses/bank/resume', json={}, headers=headers).json()['link_token'], 'link-test')
            with patch.object(banking, 'exchange', return_value='item-1'):
                self.assertEqual(client.post('/expenses/bank/complete', json={'public_token': 'public-test'}, headers=headers).status_code, 200)
            self.assertEqual(client.post('/expenses/bank/resume', json={}, headers=headers).status_code, 400)
            data = [transaction('pay', -1000, 'INCOME'), transaction('food', 20),
                    transaction('credit', 100, 'LOAN_PAYMENTS', 'LOAN_PAYMENTS_CREDIT_CARD_PAYMENT'),
                    transaction('refund', -5), {**transaction('pending', 10), 'pending': True},
                    {**transaction('eur', 80), 'iso_currency_code': 'EUR'}]
            with patch.object(banking, 'call', return_value=page(data)):
                banking.sync_item('item-1')
            html = client.get('/expenses/').text
            self.assertIn('<h2>$1000.00</h2>', html)
            self.assertIn('<h2>$15.00</h2>', html)
            self.assertIn('<h2>$985.00</h2>', html)
            self.assertNotIn('secret-access-token', html)
            self.assertIn('Pending (excluded from totals)', html)
            with patch.dict(os.environ, {'PLAID_ENV': 'production', 'LIFEHUB_PUBLIC_URL': 'https://lifehub.test'}):
                self.assertNotIn('Test merchant', client.get('/expenses/').text)
            with patch.dict(os.environ, {'LIFEHUB_USERNAME': '', 'LIFEHUB_PASSWORD': '',
                                         'PLAID_CLIENT_ID': '', 'PLAID_SECRET': '', 'LIFEHUB_ENCRYPTION_KEY': ''}):
                self.assertEqual(client.get('/expenses/').status_code, 503)


if __name__ == '__main__':
    unittest.main()
