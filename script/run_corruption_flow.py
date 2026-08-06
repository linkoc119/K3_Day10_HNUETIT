import sys
from pathlib import Path

# Add src to python path dynamically
src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_dir))

from pipelines.corruption_flow import main


if __name__ == "__main__":
    main()
