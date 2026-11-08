from pathlib import Path
import uvicorn
from nexus.app import create_app
from nexus.config import Settings

if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    settings = Settings(data_dir=root/'tmp/features-qa-data', frontend_dir=root/'tmp/features-dist', browser_enabled=True)
    uvicorn.run(create_app(settings), host='127.0.0.1', port=8005, workers=1, proxy_headers=False, limit_concurrency=32)
