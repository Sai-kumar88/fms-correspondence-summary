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
    ASGI middleware that strips /api/index.py or /index.py prefixes
    added when Vercel serverless rewrites or routes forward requests.
    This guarantees FastAPI matches defined routes regardless of proxy rewriting.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            for prefix in ("/api/index.py", "/index.py", "/api/index", "api/index.py"):
                if path.startswith(prefix):
                    path = path[len(prefix):]
                    if not path.startswith("/"):
                        path = "/" + path
                    scope["path"] = path
                    break
        await self.app(scope, receive, send)


# Wrap FastAPI application with the normalizer
app = VercelPathNormalizer(base_app)

# Expose Mangum AWS Lambda-compatible handler for Vercel Serverless
handler = Mangum(app, lifespan="off")

__all__ = ["app", "handler"]
