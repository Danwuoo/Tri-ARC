from pathlib import Path
text = Path("arc/dsl/runtime/primitives.py").read_text()
start = text.index("metadata={\"position\"")
print(repr(text[start:start+60]))
