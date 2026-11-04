from fastapi import APIRouter, Request
from core.web import render

# Copy this folder, rename templates/_template to your slug, and update below.
SLUG = '_template'
manifest = dict(name='My app', icon='✨', description='Describe what this app tracks.')
router = APIRouter()


def init_db(conn):
    # Prefix all tables with your app slug. Existing data must survive restarts.
    pass


@router.get('/')
def index(request: Request):
    return render(request, f'{SLUG}/index.html')
