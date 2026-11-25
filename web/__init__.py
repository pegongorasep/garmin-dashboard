"""Ahí la Llevas: la web (FastAPI) que guarda los datos de cada persona y sirve su dashboard."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
# El motor usa imports planos (`import metrics`): dashboard/ y plan/ van en sys.path.
for _p in (ROOT / "dashboard", ROOT / "plan"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
