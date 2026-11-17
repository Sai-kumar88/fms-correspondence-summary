import sys
from pathlib import Path

# Add project root directory to Python path for serverless environment
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app
from mangum import Mangum

# Support both ASGI (app) and Serverless AWS Lambda (handler)
handler = Mangum(app, lifespan="off")

__all__ = ["app", "handler"]
