from pathlib import Path
path = Path("arc/dsl/runtime/primitives.py")
text = path.read_text(encoding="utf-8")
while '\\"' in text:
    text = text.replace('\"', '"')
path.write_text(text, encoding="utf-8")
