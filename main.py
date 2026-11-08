"""Production entry point: one process, one local model task worker."""
from nexus.app import create_app

app = create_app()
