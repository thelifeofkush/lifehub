from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import os

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(ROOT / 'core' / 'templates'))
templates.env.loader = ChoiceLoader([
    FileSystemLoader(str(ROOT / 'core' / 'templates')),
    FileSystemLoader([str(p) for p in sorted((ROOT / 'apps').glob('*/templates'))]),
])


def today():
    return datetime.now(ZoneInfo(os.environ.get('TZ', 'America/Chicago'))).date().isoformat()


def render(request, template, **context):
    return templates.TemplateResponse(request=request, name=template, context={
        'apps': request.app.state.apps, 'today': today(), **context,
    })


def redirect(url):
    return RedirectResponse(url, status_code=303)
