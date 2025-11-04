from pathlib import Path
text = Path("arc/dsl/runtime/primitives.py").read_text()
index = text.find("\\\"")
print(index)
print(repr(text[index:index+4]))
