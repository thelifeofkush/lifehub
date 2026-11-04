from datetime import date
from fastapi import APIRouter, Form, Request
from core.db import db
from core.web import render, redirect

manifest = dict(name='Journal', icon='📖', description='Pause, reflect, and capture the everyday.')
router = APIRouter()


def init_db(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS journal_entries (id INTEGER PRIMARY KEY, day TEXT NOT NULL, body TEXT NOT NULL)')


@router.get('/')
def index(request: Request):
    with db() as conn:
        entries = conn.execute('SELECT * FROM journal_entries ORDER BY day DESC, id DESC').fetchall()
    return render(request, 'journal/index.html', entries=entries)


@router.post('/add')
def add(day: date = Form(), body: str = Form(min_length=1, max_length=20000)):
    if body.strip():
        with db() as conn:
            conn.execute('INSERT INTO journal_entries(day, body) VALUES (?, ?)', (day.isoformat(), body.strip()))
    return redirect('/journal/')


@router.post('/{entry_id}/delete')
def delete(entry_id: int):
    with db() as conn:
        conn.execute('DELETE FROM journal_entries WHERE id=?', (entry_id,))
    return redirect('/journal/')
