from fastapi import APIRouter, Form, Request
from core.db import db
from core.web import render, redirect, today

manifest = dict(name='Habits', icon='🌱', description='Build a rhythm with small, daily wins.')
router = APIRouter()


def init_db(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS habits_items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS habits_checks (habit_id INTEGER NOT NULL, day TEXT NOT NULL, PRIMARY KEY(habit_id, day))')


@router.get('/')
def index(request: Request):
    with db() as conn:
        items = conn.execute('SELECT h.*, EXISTS(SELECT 1 FROM habits_checks c WHERE c.habit_id=h.id AND c.day=?) AS done FROM habits_items h ORDER BY h.id', (today(),)).fetchall()
    return render(request, 'habits/index.html', items=items)


@router.post('/add')
def add(name: str = Form(min_length=1, max_length=200)):
    if name.strip():
        with db() as conn:
            conn.execute('INSERT INTO habits_items(name) VALUES (?)', (name.strip(),))
    return redirect('/habits/')


@router.post('/{item_id}/toggle')
def toggle(item_id: int):
    with db() as conn:
        if conn.execute('SELECT 1 FROM habits_items WHERE id=?', (item_id,)).fetchone():
            result = conn.execute('DELETE FROM habits_checks WHERE habit_id=? AND day=?', (item_id, today()))
            if not result.rowcount:
                conn.execute('INSERT INTO habits_checks VALUES (?, ?)', (item_id, today()))
    return redirect('/habits/')


@router.post('/{item_id}/delete')
def delete(item_id: int):
    with db() as conn:
        conn.execute('DELETE FROM habits_checks WHERE habit_id=?', (item_id,))
        conn.execute('DELETE FROM habits_items WHERE id=?', (item_id,))
    return redirect('/habits/')
