"""Small explicit configuration; no cloud credentials required."""
from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('NEXUS_DATA_DIR', str(ROOT / 'data'))).resolve())
    frontend_dir: Path = ROOT / 'frontend' / 'dist'
    model: str = field(default_factory=lambda: os.getenv('NEXUS_MODEL', 'qwen3:1.7b'))
    context_size: int = field(default_factory=lambda: int(os.getenv('NEXUS_CONTEXT', '2048')))
    model_timeout: int = field(default_factory=lambda: int(os.getenv('NEXUS_MODEL_TIMEOUT', '120')))
    model_threads: int = field(default_factory=lambda: int(os.getenv('NEXUS_MODEL_THREADS', '4')))
    model_batch: int = field(default_factory=lambda: int(os.getenv('NEXUS_MODEL_BATCH', '64')))
    task_timeout: int = field(default_factory=lambda: int(os.getenv('NEXUS_TASK_TIMEOUT', '300')))
    max_steps: int = 12
    max_upload: int = 5_000_000
    max_task_bytes: int = 15_000_000
    max_user_bytes: int = 250_000_000
    daily_tasks: int = 40
    queue_limit: int = 8
    browser_enabled: bool = field(default_factory=lambda: os.getenv('NEXUS_BROWSER', '0') == '1')
    secure_cookies: bool = field(default_factory=lambda: os.getenv('NEXUS_SECURE_COOKIES', '0') == '1')
    allowed_hosts: list[str] = field(default_factory=lambda: os.getenv('NEXUS_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(','))

    def __post_init__(self):
        if not 2048 <= self.context_size <= 8192:
            raise ValueError('NEXUS_CONTEXT must be 2048â€“8192')
        if not 10 <= self.model_timeout <= 180 or not 30 <= self.task_timeout <= 900:
            raise ValueError('Invalid timeout configuration')
        if not 1 <= self.model_threads <= 8 or not 16 <= self.model_batch <= 256:
            raise ValueError('Model threads must be 1-8 and batch must be 16-256')
        self.data_dir.mkdir(parents=True, exist_ok=True)
