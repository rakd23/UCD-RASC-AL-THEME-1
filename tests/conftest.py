import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in ("concept-sizing", "rover-comms", "tests"):
    sys.path.insert(0, str(ROOT / folder))


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: runs notebook 04 end to end (about 2 minutes)")
