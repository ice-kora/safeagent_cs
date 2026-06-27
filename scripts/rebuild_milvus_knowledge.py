import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ingest_knowledge_to_milvus import main


if __name__ == "__main__":
    if "--reset" not in sys.argv:
        sys.argv.append("--reset")
    raise SystemExit(main())
