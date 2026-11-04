import os
import tempfile
import unittest
from fastapi.testclient import TestClient
from core.main import app
from core.db import db
from core.web import today


class LifeHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.previous = os.environ.get('DATA_DIR')
        os.environ['DATA_DIR'] = cls.directory.name
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        if cls.previous is None:
            os.environ.pop('DATA_DIR', None)
        else:
            os.environ['DATA_DIR'] = cls.previous
        cls.directory.cleanup()

    def test_discovery_and_pages(self):
        self.assertEqual({x['slug'] for x in app.state.apps}, {'habits', 'journal', 'expenses', 'duncan'})
        for url in ('/', '/habits/', '/journal/', '/expenses/', '/duncan/', '/health', '/static/style.css'):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_habit_check_toggle_and_delete(self):
        self.client.post('/habits/add', data={'name': 'Read a book'})
        with db() as conn:
            item_id = conn.execute('SELECT id FROM habits_items').fetchone()[0]
        self.client.post(f'/habits/{item_id}/toggle')
        self.assertIn('✓ Done today', self.client.get('/habits/').text)
        self.client.post(f'/habits/{item_id}/toggle')
        self.assertNotIn('✓ Done today', self.client.get('/habits/').text)
        self.client.post(f'/habits/{item_id}/delete')
        self.assertNotIn('Read a book', self.client.get('/habits/').text)

    def test_journal_persistence_escaping_and_validation(self):
        body = '<script>alert(1)</script>'
        self.client.post('/journal/add', data={'day': today(), 'body': body})
        page = self.client.get('/journal/').text
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn(body, page)
        with db() as conn:
            entry = conn.execute('SELECT * FROM journal_entries').fetchone()
            self.assertEqual(entry['body'], body)
        self.assertEqual(self.client.post('/journal/add', data={'day': 'bad', 'body': 'x'}).status_code, 422)
        self.client.post(f"/journal/{entry['id']}/delete")
        self.assertNotIn('&lt;script&gt;', self.client.get('/journal/').text)

    def test_expense_exact_cents_and_validation(self):
        fields = {'day': today(), 'description': 'Coffee', 'category': 'Food', 'amount': '4.29'}
        self.assertEqual(self.client.post('/expenses/add', data=fields).status_code, 200)
        with db() as conn:
            item = conn.execute('SELECT * FROM expenses_items').fetchone()
            self.assertEqual(item['cents'], 429)
        for amount in ('-1', 'NaN', 'Infinity', '0', '1.001', '100000001'):
            self.assertEqual(self.client.post('/expenses/add', data={**fields, 'amount': amount}).status_code, 422)
        self.assertIn('$4.29', self.client.get('/expenses/').text)
        self.client.post(f"/expenses/{item['id']}/delete")
        self.assertNotIn('Coffee', self.client.get('/expenses/').text)


if __name__ == '__main__':
    unittest.main()
