import sys
from pathlib import Path

# Make `src/` importable when running pytest from the project root.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
