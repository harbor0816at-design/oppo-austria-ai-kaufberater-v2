import os
import sys
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
