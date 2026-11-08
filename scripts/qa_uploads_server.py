"""Isolated local acceptance server; never uses the owner's production account."""
from pathlib import Path
import uvicorn
from nexus.app import create_app
from nexus.config import Settings

if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    uvicorn.run(create_app(Settings(data_dir=root/'tmp/uploads-qa-data', frontend_dir=root/'frontend/dist')),
                host='127.0.0.1', port=8005, workers=1, proxy_headers=False, limit_concurrency=32)
