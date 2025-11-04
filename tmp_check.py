from pathlib import Path
text = Path("arc/dsl/runtime/primitives.py").read_text()
print(text.find("\\\"position\\\""))
