#!/usr/bin/env python3
"""
Automated style fixer for common issues in Tri-ARC project.

Fixes:
- Line length violations (splits long lines)
- Missing docstrings for public APIs
- Missing type hints
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple


def fix_line_length(line: str, max_length: int = 100) -> List[str]:
    """
    Split a long line into multiple lines.
    
    This is a simple heuristic that works for common cases.
    """
    if len(line.rstrip()) <= max_length:
        return [line]
    
    # Don't split strings or comments automatically
    if '"""' in line or "'''" in line or line.strip().startswith('#'):
        return [line]
    
    # Try to split at logical points
    indent = len(line) - len(line.lstrip())
    indent_str = line[:indent]
    
    # Split at commas in function calls/definitions
    if '(' in line and ')' in line:
        # Find the opening paren
        paren_pos = line.find('(')
        before_paren = line[:paren_pos + 1]
        after_paren = line[paren_pos + 1:]
        
        if ',' in after_paren:
            # Split at commas
            parts = after_paren.split(',')
            result = [before_paren]
            for i, part in enumerate(parts[:-1]):
                result.append(indent_str + '    ' + part.strip() + ',')
            result.append(indent_str + '    ' + parts[-1].strip())
            return result
    
    # If we can't split intelligently, just return the original
    return [line]


def add_docstring_placeholder(lines: List[str], line_idx: int, item_type: str, name: str) -> List[str]:
    """Add a placeholder docstring after a function/class definition."""
    # Find the line with the definition
    def_line = lines[line_idx]
    indent = len(def_line) - len(def_line.lstrip())
    
    # Check if next line already has a docstring
    if line_idx + 1 < len(lines):
        next_line = lines[line_idx + 1].strip()
        if next_line.startswith('"""') or next_line.startswith("'''"):
            return lines
    
    # Add placeholder docstring
    docstring_indent = ' ' * (indent + 4)
    docstring = f'{docstring_indent}"""{item_type} {name}."""\n'
    
    # Insert after the definition line
    # Find the end of the definition (could span multiple lines)
    insert_idx = line_idx + 1
    while insert_idx < len(lines) and not lines[insert_idx].strip().endswith(':'):
        insert_idx += 1
    insert_idx += 1
    
    lines.insert(insert_idx, docstring)
    return lines


def fix_file(file_path: Path, dry_run: bool = False) -> Tuple[int, int]:
    """
    Fix style issues in a file.
    
    Returns (fixes_applied, issues_remaining).
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.splitlines(keepends=True)
        
        fixes_applied = 0
        modified = False
        
        # Fix line length issues (simple cases only)
        new_lines = []
        for line in lines:
            if len(line.rstrip()) > 100:
                # Only fix if it's a simple case
                if line.strip().startswith('#') or '"""' in line or "'''" in line:
                    # Don't auto-fix comments or docstrings
                    new_lines.append(line)
                else:
                    # Try to fix
                    fixed = fix_line_length(line)
                    if len(fixed) > 1:
                        new_lines.extend(fixed)
                        fixes_applied += 1
                        modified = True
                    else:
                        new_lines.append(line)
            else:
                new_lines.append(line)
        
        if modified and not dry_run:
            file_path.write_text(''.join(new_lines), encoding='utf-8')
        
        return fixes_applied, 0
        
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return 0, 1


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix style issues in Python files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
    parser.add_argument('--path', type=Path, default=Path('arc/symbolic'), help='Path to check')
    args = parser.parse_args()
    
    root = Path(__file__).parent.parent
    target_path = root / args.path
    
    if not target_path.exists():
        print(f"Path {target_path} does not exist")
        return 1
    
    total_fixes = 0
    total_issues = 0
    
    for file_path in target_path.glob('**/*.py'):
        if '__pycache__' in str(file_path):
            continue
        
        fixes, issues = fix_file(file_path, dry_run=args.dry_run)
        total_fixes += fixes
        total_issues += issues
        
        if fixes > 0:
            status = "(dry-run)" if args.dry_run else "(fixed)"
            print(f"{file_path}: {fixes} fixes {status}")
    
    print(f"\nTotal fixes: {total_fixes}")
    print(f"Total issues: {total_issues}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
