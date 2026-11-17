import sys
from pathlib import Path

# Add project root directory to Python path for serverless environment
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app as base_app
from mangum import Mangum


class VercelPathNormalizer:
    """
    ASGI middleware that inspects Vercel's x-matched-path header.
    When Vercel rewrites requests to /api/index.py, this normalizer restores the
    original client path (e.g. /api/v1/upload or /health) so FastAPI routing matches perfectly.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            
            # 1. Check for Vercel's x-matched-path (injected during URL rewrites)
            matched_path = headers.get(b"x-matched-path")
            if matched_path:
                original = matched_path.decode("utf-8")
                if original in ("/api/index.py", "/api/index", "/index.py", "/api", "/api/"):
                    scope["path"] = "/"
                else:
                    scope["path"] = original
            # 2. If no x-matched-path but path is an index alias, normalize to root
            elif scope.get("path") in ("/api/index.py", "/api/index", "/index.py", "/api", "/api/"):
                scope["path"] = "/"

        await self.app(scope, receive, send)


app = VercelPathNormalizer(base_app)
handler = Mangum(app, lifespan="off")

__all__ = ["app", "handler"]
