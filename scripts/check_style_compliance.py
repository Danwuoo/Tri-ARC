#!/usr/bin/env python3
"""
Style compliance checker for Tri-ARC project.

Verifies adherence to project style guidelines:
- PEP 8 naming conventions
- Type hints for public functions
- Proper imports (from __future__ import annotations)
- Line length <= 100 characters
- Docstrings for public APIs
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import List, Tuple


class StyleViolation:
    def __init__(self, file: Path, line: int, message: str, severity: str = "error"):
        self.file = file
        self.line = line
        self.message = message
        self.severity = severity

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.severity}] {self.message}"


class StyleChecker:
    def __init__(self, root: Path):
        self.root = root
        self.violations: List[StyleViolation] = []

    def check_file(self, file_path: Path) -> None:
        """Check a single Python file for style violations."""
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            # Parse AST
            try:
                tree = ast.parse(content, filename=str(file_path))
            except SyntaxError as e:
                self.violations.append(
                    StyleViolation(file_path, e.lineno or 0, f"Syntax error: {e.msg}", "error")
                )
                return
            
            # Check imports
            self._check_future_imports(file_path, tree)
            
            # Check naming conventions
            self._check_naming_conventions(file_path, tree)
            
            # Check type hints
            self._check_type_hints(file_path, tree)
            
            # Check docstrings
            self._check_docstrings(file_path, tree)
            
            # Check line length
            self._check_line_length(file_path, lines)
            
        except Exception as e:
            self.violations.append(
                StyleViolation(file_path, 0, f"Failed to check file: {e}", "warning")
            )

    def _check_future_imports(self, file_path: Path, tree: ast.AST) -> None:
        """Check for 'from __future__ import annotations'."""
        has_future_annotations = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    for alias in node.names:
                        if alias.name == "annotations":
                            has_future_annotations = True
                            break
        
        if not has_future_annotations:
            # Check if file has any type hints that would benefit from it
            has_type_hints = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and (node.returns or any(arg.annotation for arg in node.args.args))
                for node in ast.walk(tree)
            )
            
            if has_type_hints:
                self.violations.append(
                    StyleViolation(
                        file_path, 1,
                        "Missing 'from __future__ import annotations' for type hints",
                        "warning"
                    )
                )

    def _check_naming_conventions(self, file_path: Path, tree: ast.AST) -> None:
        """Check PEP 8 naming conventions."""
        for node in ast.walk(tree):
            # Check class names (PascalCase)
            if isinstance(node, ast.ClassDef):
                # Allow private classes to start with underscore
                if node.name.startswith('_'):
                    # Private class: _ClassName is acceptable
                    if not re.match(r'^_[A-Z][a-zA-Z0-9]*$', node.name):
                        self.violations.append(
                            StyleViolation(
                                file_path, node.lineno,
                                f"Private class '{node.name}' should use _PascalCase",
                                "error"
                            )
                        )
                elif not re.match(r'^[A-Z][a-zA-Z0-9]*$', node.name):
                    self.violations.append(
                        StyleViolation(
                            file_path, node.lineno,
                            f"Class '{node.name}' should use PascalCase",
                            "error"
                        )
                    )
            
            # Check function names (snake_case)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not re.match(r'^[a-z_][a-z0-9_]*$', node.name):
                    # Allow special methods like __init__
                    if not (node.name.startswith('__') and node.name.endswith('__')):
                        self.violations.append(
                            StyleViolation(
                                file_path, node.lineno,
                                f"Function '{node.name}' should use snake_case",
                                "error"
                            )
                        )
            
            # Check constants (UPPER_SNAKE_CASE) - module level only
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        # Check if it's module level
                        if isinstance(node, ast.Assign) and hasattr(node, 'col_offset'):
                            if node.col_offset == 0:  # Module level
                                name = target.id
                                # Constants should be UPPER_SNAKE_CASE
                                if name.isupper() and not re.match(r'^[A-Z_][A-Z0-9_]*$', name):
                                    self.violations.append(
                                        StyleViolation(
                                            file_path, node.lineno,
                                            f"Constant '{name}' should use UPPER_SNAKE_CASE",
                                            "warning"
                                        )
                                    )

    def _check_type_hints(self, file_path: Path, tree: ast.AST) -> None:
        """Check that public functions have type hints."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private functions
                if node.name.startswith('_'):
                    continue
                
                # Check return type hint
                if node.returns is None and node.name != '__init__':
                    self.violations.append(
                        StyleViolation(
                            file_path, node.lineno,
                            f"Public function '{node.name}' missing return type hint",
                            "warning"
                        )
                    )
                
                # Check parameter type hints
                for arg in node.args.args:
                    if arg.arg == 'self' or arg.arg == 'cls':
                        continue
                    if arg.annotation is None:
                        self.violations.append(
                            StyleViolation(
                                file_path, node.lineno,
                                f"Parameter '{arg.arg}' in '{node.name}' missing type hint",
                                "warning"
                            )
                        )

    def _check_docstrings(self, file_path: Path, tree: ast.AST) -> None:
        """Check that public APIs have docstrings."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Skip private items
                if node.name.startswith('_') and not (node.name.startswith('__') and node.name.endswith('__')):
                    continue
                
                # Check for docstring
                docstring = ast.get_docstring(node)
                if docstring is None:
                    item_type = "Class" if isinstance(node, ast.ClassDef) else "Function"
                    self.violations.append(
                        StyleViolation(
                            file_path, node.lineno,
                            f"{item_type} '{node.name}' missing docstring",
                            "warning"
                        )
                    )

    def _check_line_length(self, file_path: Path, lines: List[str]) -> None:
        """Check line length (max 100 characters)."""
        for i, line in enumerate(lines, start=1):
            # Remove trailing whitespace for check
            stripped = line.rstrip()
            if len(stripped) > 100:
                self.violations.append(
                    StyleViolation(
                        file_path, i,
                        f"Line too long ({len(stripped)} > 100 characters)",
                        "warning"
                    )
                )

    def check_directory(self, directory: Path, pattern: str = "**/*.py") -> None:
        """Check all Python files in a directory."""
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                # Skip __pycache__ and other generated files
                if "__pycache__" in str(file_path) or ".pytest_cache" in str(file_path):
                    continue
                self.check_file(file_path)

    def report(self) -> Tuple[int, int]:
        """Print violations and return (errors, warnings) counts."""
        errors = 0
        warnings = 0
        
        # Group by file
        by_file = {}
        for violation in self.violations:
            if violation.file not in by_file:
                by_file[violation.file] = []
            by_file[violation.file].append(violation)
        
        # Print grouped violations
        for file_path in sorted(by_file.keys()):
            print(f"\n{file_path}:")
            for violation in sorted(by_file[file_path], key=lambda v: v.line):
                print(f"  {violation}")
                if violation.severity == "error":
                    errors += 1
                else:
                    warnings += 1
        
        return errors, warnings


def main() -> int:
    """Main entry point."""
    root = Path(__file__).parent.parent
    checker = StyleChecker(root)
    
    # Check symbolic module
    symbolic_dir = root / "arc" / "symbolic"
    if symbolic_dir.exists():
        print(f"Checking {symbolic_dir}...")
        checker.check_directory(symbolic_dir)
    
    # Report results
    errors, warnings = checker.report()
    
    print(f"\n{'='*60}")
    print(f"Style check complete:")
    print(f"  Errors: {errors}")
    print(f"  Warnings: {warnings}")
    print(f"{'='*60}")
    
    # Return non-zero if there are errors
    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
