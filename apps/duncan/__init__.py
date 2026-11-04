from fastapi import APIRouter, Request
from core.web import render

manifest = dict(name='Duncan', icon='📋', description='Plan your day with your existing Duncan planner.')
router = APIRouter()


@router.get('/')
def index(request: Request):
    return render(request, 'duncan/index.html')
