import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.db import db
from core.web import render, redirect, today
from . import banking

manifest = dict(name='Money', icon='💳', description='Track income, spending, and connected bank activity.')
router = APIRouter()


def init_db(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS expenses_items (id INTEGER PRIMARY KEY, day TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, cents INTEGER NOT NULL CHECK(cents > 0))')
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(expenses_items)')}
    if 'kind' not in columns:
        conn.execute("ALTER TABLE expenses_items ADD COLUMN kind TEXT NOT NULL DEFAULT 'expense'")
    banking.init_bank_db(conn)


@router.get('/')
def index(request: Request, month: str | None = None):
    month = month or today()[:7]
    try:
        parsed = date.fromisoformat(month + '-01')
        if parsed.strftime('%Y-%m') != month:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, 'Select a valid month (YYYY-MM).')
    with db() as conn:
        manual = conn.execute('SELECT * FROM expenses_items WHERE substr(day, 1, 7)=?', (month,)).fetchall()
        imported = conn.execute('''SELECT t.* FROM expenses_bank_transactions t
            JOIN expenses_bank_items b ON b.item_id=t.item_id
            WHERE substr(t.day, 1, 7)=? AND b.environment=?''', (month, banking.environment())).fetchall()
        connections = conn.execute('SELECT item_id, environment, last_sync, error FROM expenses_bank_items WHERE environment=?', (banking.environment(),)).fetchall()
    items = [{**dict(row), 'source': 'Manual', 'pending': False, 'currency': 'USD', 'key': str(row['id'])} for row in manual]
    items += [{**dict(row), 'source': 'Bank', 'kind': row['override_kind'] or row['kind'],
               'cents': abs(row['cents']), 'key': row['transaction_id']} for row in imported]
    items.sort(key=lambda row: (row['day'], row['key']), reverse=True)
    posted = [row for row in items if not row['pending'] and row['currency'] == 'USD']
    income = sum(row['cents'] for row in posted if row['kind'] == 'income')
    spending = sum(row['cents'] for row in posted if row['kind'] == 'expense') - sum(row['cents'] for row in posted if row['kind'] == 'refund')
    return render(request, 'expenses/index.html', items=items, month=month,
                  income=income, spending=spending, net=income-spending,
                  connections=connections, setup_problem=banking.setup_problem(), environment=banking.environment())


@router.post('/add')
def add(day: date = Form(), description: str = Form(min_length=1, max_length=200),
        category: str = Form(min_length=1, max_length=80), amount: str = Form(max_length=30),
        kind: Literal['expense', 'income', 'transfer', 'refund'] = Form('expense')):
    try:
        value = Decimal(amount)
        if not value.is_finite() or value <= 0 or value > Decimal('100000000') or value != value.quantize(Decimal('.01')):
            raise ValueError()
        cents = int(value * 100)
    except (InvalidOperation, ValueError):
        raise HTTPException(422, 'Amount must be positive and have at most two decimal places.')
    if not description.strip() or not category.strip():
        raise HTTPException(422, 'Description and category are required.')
    with db() as conn:
        conn.execute('INSERT INTO expenses_items(day, description, category, cents, kind) VALUES (?, ?, ?, ?, ?)',
                     (day.isoformat(), description.strip(), category.strip(), cents, kind))
    return redirect('/expenses/')


@router.post('/{item_id}/delete')
def delete(item_id: int):
    with db() as conn:
        conn.execute('DELETE FROM expenses_items WHERE id=?', (item_id,))
    return redirect('/expenses/')


def bank_request(request):
    if request.headers.get('x-lifehub') != '1':
        raise HTTPException(403, 'Open this action from LifeHub.')
    if problem := banking.setup_problem():
        raise HTTPException(503, problem)


def bank_error(exc):
    messages = {
        'ITEM_LOGIN_REQUIRED': 'Your bank needs you to reconnect. Use Reconnect below.',
        'ENCRYPTION_KEY_MISMATCH': 'The encryption key cannot unlock this connection. Restore the original key.',
        'PRODUCT_NOT_READY': 'Bank history is still being prepared. Try Sync again in a few minutes.',
        'CONNECTION_FAILED': 'Could not reach Plaid. Your existing records are unchanged; try again later.',
        'RATE_LIMIT_EXCEEDED': 'Plaid has temporarily limited requests. Try again later.',
    }
    return JSONResponse({'error': messages.get(exc.code, 'The bank action could not complete. Check your Plaid setup and try again.')}, status_code=502)


class LinkRequest(BaseModel):
    item_id: str | None = Field(default=None, max_length=200)


class CompleteRequest(BaseModel):
    public_token: str | None = Field(default=None, max_length=1000)


@router.post('/bank/link')
def link(request: Request, body: LinkRequest):
    bank_request(request)
    try:
        token = banking.create_link_token(body.item_id)
    except banking.BankError as exc:
        return bank_error(exc)
    request.session.clear()
    request.session.update(link_token=token, item_id=body.item_id, started=time.time())
    return {'link_token': token}


@router.get('/oauth')
def oauth(request: Request):
    return render(request, 'expenses/oauth.html')


@router.post('/bank/resume')
def resume(request: Request):
    bank_request(request)
    if time.time() - request.session.get('started', 0) > 3600 or not request.session.get('link_token'):
        raise HTTPException(400, 'Bank connection expired. Return to Money and start again.')
    return {'link_token': request.session['link_token']}


@router.post('/bank/complete')
def complete(request: Request, body: CompleteRequest, tasks: BackgroundTasks):
    bank_request(request)
    if time.time() - request.session.get('started', 0) > 3600 or not request.session.get('link_token'):
        raise HTTPException(400, 'Bank connection expired. Start again.')
    try:
        if request.session.get('item_id'):
            with db() as conn:
                conn.execute('UPDATE expenses_bank_items SET error=NULL WHERE item_id=?', (request.session['item_id'],))
        else:
            if not body.public_token:
                raise HTTPException(400, 'Missing bank connection token.')
            banking.exchange(body.public_token)
    except banking.BankError as exc:
        return bank_error(exc)
    request.session.clear()
    tasks.add_task(banking.sync_all)
    return {'status': 'connected'}


@router.post('/bank/sync')
def sync(request: Request):
    bank_request(request)
    banking.sync_all()
    with db() as conn:
        failed = conn.execute('SELECT 1 FROM expenses_bank_items WHERE environment=? AND error IS NOT NULL', (banking.environment(),)).fetchone()
    if failed:
        return JSONResponse({'error': 'Some accounts could not sync. Reload Money to see their connection status. Existing records are retained.'}, 502)
    return {'status': 'synced'}


@router.post('/bank/disconnect')
def disconnect(request: Request, body: LinkRequest):
    bank_request(request)
    if not body.item_id:
        raise HTTPException(400, 'Choose a connection.')
    try:
        banking.disconnect(body.item_id)
    except banking.BankError as exc:
        return bank_error(exc)
    return {'status': 'disconnected'}


@router.post('/bank/classify')
def classify(transaction_id: str = Form(max_length=200),
             kind: Literal['expense', 'income', 'transfer', 'refund'] = Form()):
    with db() as conn:
        conn.execute('UPDATE expenses_bank_transactions SET override_kind=? WHERE transaction_id=?', (kind, transaction_id))
    return redirect('/expenses/')
