import importlib
import logging
import re
import asyncio
import os
import hashlib
import secrets
from contextlib import suppress
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from core.db import db
from core.web import ROOT, render
from core.security import OwnerAuthMiddleware
from starlette.middleware.sessions import SessionMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    app.state.apps = []
    for folder in sorted((ROOT / 'apps').iterdir()):
        if not folder.is_dir() or not re.fullmatch('[a-z][a-z0-9_]*', folder.name):
            continue
        try:
            module = importlib.import_module(f'apps.{folder.name}')
            manifest = module.manifest
            for field in ('name', 'icon', 'description'):
                if not isinstance(manifest[field], str):
                    raise ValueError(f'Invalid manifest field: {field}')
            router = module.router
            with db() as connection:
                if hasattr(module, 'init_db'):
                    module.init_db(connection)
            if folder.name not in getattr(app.state, 'mounted_apps', set()):
                app.include_router(router, prefix=f'/{folder.name}')
                app.state.mounted_apps = getattr(app.state, 'mounted_apps', set()) | {folder.name}
            app.state.apps.append({**manifest, 'slug': folder.name})
        except Exception:
            logger.exception('Skipping broken app %s', folder.name)
    task = None
    if any(entry['slug'] == 'expenses' for entry in app.state.apps):
        from apps.expenses.banking import background_sync
        task = asyncio.create_task(background_sync())
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title='LifeHub', lifespan=lifespan)
app.add_middleware(OwnerAuthMiddleware)
app.add_middleware(SessionMiddleware,
    secret_key=hashlib.sha256(os.getenv('LIFEHUB_ENCRYPTION_KEY', secrets.token_hex(32)).encode()).hexdigest(),
    session_cookie='lifehub_link', same_site='lax', max_age=3600,
    https_only=os.getenv('LIFEHUB_PUBLIC_URL', '').startswith('https://'))
app.mount('/static', StaticFiles(directory=ROOT / 'core' / 'static'), name='static')


@app.get('/')
def home(request: Request):
    return render(request, 'home.html')


@app.get('/health')
def health():
    with db() as connection:
        connection.execute('SELECT 1')
    return {'status': 'ok'}
