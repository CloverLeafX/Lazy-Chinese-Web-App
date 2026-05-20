import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "Lazy Chinese Web App"))
from server import app  # noqa: E402


