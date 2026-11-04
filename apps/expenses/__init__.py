from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Form, HTTPException, Request
from core.db import db
from core.web import render, redirect

manifest = dict(name='Expenses', icon='💳', description='Notice where your money goes.')
router = APIRouter()


def init_db(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS expenses_items (id INTEGER PRIMARY KEY, day TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, cents INTEGER NOT NULL CHECK(cents > 0))')


@router.get('/')
def index(request: Request):
    with db() as conn:
        items = conn.execute('SELECT * FROM expenses_items ORDER BY day DESC, id DESC').fetchall()
    return render(request, 'expenses/index.html', items=items, total=sum(row['cents'] for row in items))


@router.post('/add')
def add(day: date = Form(), description: str = Form(min_length=1, max_length=200), category: str = Form(min_length=1, max_length=80), amount: str = Form(max_length=30)):
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
        conn.execute('INSERT INTO expenses_items(day, description, category, cents) VALUES (?, ?, ?, ?)', (day.isoformat(), description.strip(), category.strip(), cents))
    return redirect('/expenses/')


@router.post('/{item_id}/delete')
def delete(item_id: int):
    with db() as conn:
        conn.execute('DELETE FROM expenses_items WHERE id=?', (item_id,))
    return redirect('/expenses/')
