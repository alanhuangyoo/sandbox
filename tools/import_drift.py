#!/usr/bin/env python3
"""Resolve every `from <pkg>... import name` in a tree against the installed package.

Useful when a dependency renames or removes something and the downstream import only
fails at runtime. Skips sites guarded by try/except or a version conditional, since
those are deliberate.

    python tools/import_drift.py /path/to/repo transformers
"""
import argparse
import ast
import importlib
import pathlib

VERSIONISH = ("version", "_ver", "is_")


def _guard(stack):
    """Why an import is excused, or '' if nothing excuses it."""
    for node in stack:
        if isinstance(node, ast.Try):
            return "try"
        if isinstance(node, ast.If) and any(k in ast.dump(node.test) for k in VERSIONISH):
            return "version-if"
    return ""


def scan(root: pathlib.Path, pkg: str):
    findings = []
    for path in sorted(root.rglob("*.py")):
        if any(p in path.parts for p in (".git", "build", "node_modules", ".venv")):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue

        stack = []

        def walk(node):
            stack.append(node)
            if (isinstance(node, ast.ImportFrom) and node.module and node.level == 0
                    and (node.module == pkg or node.module.startswith(pkg + "."))
                    and not _guard(stack[:-1])):
                try:
                    module = importlib.import_module(node.module)
                except Exception as exc:
                    findings.append((path, node.lineno, node.module, "<module>", type(exc).__name__))
                else:
                    for alias in node.names:
                        if alias.name != "*" and not hasattr(module, alias.name):
                            findings.append((path, node.lineno, node.module, alias.name, "missing"))
            for child in ast.iter_child_nodes(node):
                walk(child)
            stack.pop()

        walk(tree)
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=pathlib.Path)
    parser.add_argument("package")
    args = parser.parse_args()

    version = getattr(importlib.import_module(args.package), "__version__", "?")
    print(f"{args.root.name} against {args.package} {version}\n")
    findings = scan(args.root, args.package)
    for path, line, module, name, why in findings:
        print(f"{path.relative_to(args.root)}:{line}\n    from {module} import {name}  -> {why}")
    print(f"\n{len(findings)} unguarded")


if __name__ == "__main__":
    main()
