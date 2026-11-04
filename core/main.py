import importlib
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from core.db import db
from core.web import ROOT, render

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
            app.include_router(router, prefix=f'/{folder.name}')
            app.state.apps.append({**manifest, 'slug': folder.name})
        except Exception:
            logger.exception('Skipping broken app %s', folder.name)
    yield


app = FastAPI(title='LifeHub', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'core' / 'static'), name='static')


@app.get('/')
def home(request: Request):
    return render(request, 'home.html')


@app.get('/health')
def health():
    with db() as connection:
        connection.execute('SELECT 1')
    return {'status': 'ok'}
