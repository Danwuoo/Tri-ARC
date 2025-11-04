from pathlib import Path
text = Path("arc/dsl/runtime/primitives.py").read_bytes()
print(text.count(b"\\\"") )
