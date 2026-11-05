"""Single-owner authentication for this self-hosted hub."""
import base64
import os
import secrets

from core.db import db

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse


class OwnerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == '/health':
            return await call_next(request)
        username = os.getenv('LIFEHUB_USERNAME', '')
        password = os.getenv('LIFEHUB_PASSWORD', '')
        bank_configured = any(os.getenv(key) for key in ('PLAID_CLIENT_ID', 'PLAID_SECRET', 'LIFEHUB_ENCRYPTION_KEY'))
        with db() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='expenses_bank_items'").fetchone():
                bank_configured = bank_configured or bool(conn.execute('SELECT 1 FROM expenses_bank_items LIMIT 1').fetchone())
        if bank_configured and (not username or not password):
            return PlainTextResponse('Bank data is locked. Set LIFEHUB_USERNAME and LIFEHUB_PASSWORD.', 503)
        if username or password:
            if not username or not password:
                return PlainTextResponse('Set both LIFEHUB_USERNAME and LIFEHUB_PASSWORD.', 503)
            try:
                scheme, encoded = request.headers.get('authorization', '').split(' ', 1)
                supplied = base64.b64decode(encoded, validate=True).decode()
                valid = scheme.lower() == 'basic' and secrets.compare_digest(
                    supplied.encode(), f'{username}:{password}'.encode())
            except (ValueError, UnicodeError):
                valid = False
            if not valid:
                return PlainTextResponse('Sign in to LifeHub.', 401, headers={
                    'WWW-Authenticate': 'Basic realm="LifeHub", charset="UTF-8"'})
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            expected = os.getenv('LIFEHUB_PUBLIC_URL', '').rstrip('/') or str(request.base_url).rstrip('/')
            if origin and origin != expected:
                return PlainTextResponse('Cross-origin requests are not allowed.', 403)
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return PlainTextResponse('Cross-site requests are not allowed.', 403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response
