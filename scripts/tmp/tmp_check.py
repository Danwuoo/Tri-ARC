from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "arc" / "symbolic" / "dsl" / "runtime" / "primitives.py"

text = TARGET.read_text()
print(text.find("\\\"position\\\""))
