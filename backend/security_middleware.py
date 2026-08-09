from __future__ import annotations

import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Same-origin CSRF defense for cookie-authenticated state-changing API calls.
        if request.method.upper() in {'POST','PUT','PATCH','DELETE'} and request.url.path.startswith('/api/'):
            origin = request.headers.get('origin', '').strip()
            if origin:
                try:
                    parsed = urlparse(origin)
                    origin_host = parsed.netloc.lower()
                    request_host = request.headers.get('host', '').lower()
                    if origin_host and request_host and origin_host != request_host:
                        return JSONResponse({'detail': 'Requête intersite refusée (CSRF).'}, status_code=403)
                except Exception:
                    return JSONResponse({'detail': 'Origine de requête invalide.'}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=(), usb=()')
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        if request.url.path.startswith('/api/'):
            response.headers.setdefault('Cache-Control', 'no-store')
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small single-instance limiter; durable login lockout is implemented in auth_service."""
    def __init__(self, app):
        super().__init__(app)
        self.buckets = defaultdict(deque)

    def _rule(self, path: str):
        if path == '/api/login': return (12, 60)
        if path == '/api/register': return (6, 60)
        if '/files' in path and path.startswith('/api/rooms/'): return (20, 60)
        if path.startswith('/api/game-studio/import'): return (20, 60)
        return (360, 60)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith('/api/'):
            return await call_next(request)
        ip = (request.headers.get('x-forwarded-for','').split(',',1)[0].strip()
              or (request.client.host if request.client else 'unknown'))
        limit, window = self._rule(request.url.path)
        key = (ip, request.url.path if limit < 360 else '*')
        now = time.monotonic(); q = self.buckets[key]
        while q and q[0] < now - window: q.popleft()
        if len(q) >= limit:
            return JSONResponse({'detail': 'Trop de requêtes. Réessaie dans quelques instants.'}, status_code=429,
                                headers={'Retry-After': str(window)})
        q.append(now)
        return await call_next(request)


class PerformanceHeadersMiddleware(BaseHTTPMiddleware):
    """Mesure le temps ASGI et rend les assets versionnés réellement cacheables."""
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000.0
        response.headers.setdefault('Server-Timing', f'app;dur={duration_ms:.1f}')
        response.headers.setdefault('X-PiChat-Performance', '3.5')
        path = request.url.path
        if path.startswith(('/css/','/js/','/assets/')):
            q = request.url.query
            if 'v=3500' in q:
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            else:
                response.headers.setdefault('Cache-Control', 'public, max-age=3600')
        elif path.endswith(('.html','/login','/register','/admin','/spaces','/status','/setup')) or path == '/':
            response.headers.setdefault('Cache-Control', 'no-cache')
        return response
