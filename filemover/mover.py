"""
Core routines for moving Python files and directories and updating imports.

This module implements the functionality behind the CLI exposed in
``filemover.cli``.  It provides functions to move an individual Python
module or an entire directory tree to a new location within a repository.
After moving code, it rewrites import statements in every ``.py`` file
under the repository root so that absolute imports continue to refer to
the relocated modules.

The import rewriting logic is intentionally conservative: only absolute
imports are updated.  Relative imports (those beginning with one or more
leading dots) are left untouched.  When relocating a module, both
``import a.b.c`` and ``from a.b import c`` forms are supported.

Note that the rewriting operates on AST nodes rather than simple text
search/replace; this avoids accidentally touching strings and comments.
However, rewriting may simplify the formatting of an import statement (for
instance by collapsing multi‑line imports onto a single line).  The
semantics of the code will be preserved even if the exact style changes.
"""

from __future__ import annotations

import ast
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "move_file",
    "move_folder",
    "update_imports",
    "compute_module_path",
]


def compute_module_path(repo_root: Path, file_path: Path) -> str:
    """Return the dotted module path for a Python file relative to the repository root.

    The returned string is derived by removing the ``repo_root`` prefix from
    ``file_path``, stripping the ``.py`` suffix and replacing path
    separators with dots.  For example::

        compute_module_path(Path('/repo'), Path('/repo/pkg/sub/m.py'))
        # -> 'pkg.sub.m'

    Parameters
    ----------
    repo_root: Path
        The root directory of the repository.
    file_path: Path
        The path to a Python file within the repository.

    Returns
    -------
    str
        The module's dotted import path.
    """
    relative = file_path.relative_to(repo_root)
    # Remove trailing .py if present; allow .pyw as well
    if relative.suffix in {".py", ".pyw"}:
        relative = relative.with_suffix("")
    parts = relative.parts
    return ".".join(parts)


def move_file(src_path: Path, dst_path: Path, repo_root: Path) -> None:
    """Move a single Python file to a new location and update imports.

    After moving the file, any absolute import statements that referred to
    the old module path are rewritten to point at the new module path.  The
    source file at ``src_path`` is removed (as part of the move).  If the
    destination's parent directory does not exist it will be created.

    Parameters
    ----------
    src_path: Path
        Absolute path to the source ``.py`` file.
    dst_path: Path
        Absolute path where the file should be moved.  The ``.py`` suffix
        should be included.
    repo_root: Path
        Root of the repository for computing module paths.

    Raises
    ------
    FileNotFoundError
        If ``src_path`` does not exist.
    ValueError
        If ``src_path`` or ``dst_path`` are not within ``repo_root``.
    """
    if not src_path.exists():
        raise FileNotFoundError(src_path)
    if not src_path.is_file():
        raise ValueError(f"Source path {src_path} must be a file")
    if repo_root not in src_path.parents:
        raise ValueError(f"Source path {src_path} is not inside repository root {repo_root}")
    if repo_root not in dst_path.parents:
        raise ValueError(f"Destination path {dst_path} must reside within repository root {repo_root}")
    if not dst_path.suffix:
        # If no suffix, assume .py to maintain module semantics
        dst_path = dst_path.with_suffix(src_path.suffix)
    # Compute module paths for import rewriting
    old_module = compute_module_path(repo_root, src_path)
    new_module = compute_module_path(repo_root, dst_path)
    # Ensure destination directory exists
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    # Move the file on disk
    shutil.move(str(src_path), str(dst_path))
    # Update imports in all python files under repo_root
    update_imports(repo_root, old_module, new_module, exclude_paths={dst_path})


def move_folder(src_dir: Path, dst_dir: Path, repo_root: Path) -> None:
    """Move an entire directory tree to a new location and update imports.

    This operation moves ``src_dir`` (and everything under it) to ``dst_dir``.
    After relocation, import statements are rewritten so that absolute
    references to modules within ``src_dir`` now refer to their new dotted
    names.  For example, moving ``package/foo`` to ``new_pkg/bar`` will
    change ``import package.foo.baz`` to ``import new_pkg.bar.baz``.

    Parameters
    ----------
    src_dir: Path
        Absolute path to the directory to be moved.
    dst_dir: Path
        Absolute path of the new directory location.  Intermediate
        directories will be created if necessary.
    repo_root: Path
        Root of the repository for computing module paths.

    Raises
    ------
    FileNotFoundError
        If ``src_dir`` does not exist.
    ValueError
        If either path is not within the repository root.
    """
    if not src_dir.exists():
        raise FileNotFoundError(src_dir)
    if not src_dir.is_dir():
        raise ValueError(f"Source path {src_dir} must be a directory")
    if repo_root not in src_dir.parents and src_dir != repo_root:
        raise ValueError(f"Source directory {src_dir} is not inside repository root {repo_root}")
    if repo_root not in dst_dir.parents and dst_dir != repo_root:
        raise ValueError(f"Destination directory {dst_dir} must reside within repository root {repo_root}")
    # Determine old and new base module paths
    old_base = compute_module_path(repo_root, src_dir)
    new_base = compute_module_path(repo_root, dst_dir)
    # Create destination directory if necessary
    dst_dir.parent.mkdir(parents=True, exist_ok=True)
    # Move the directory
    shutil.move(str(src_dir), str(dst_dir))
    # After moving, update imports referencing anything under old_base
    update_imports(repo_root, old_base, new_base)


def update_imports(
    repo_root: Path,
    old_module: str,
    new_module: str,
    exclude_paths: Optional[Sequence[Path]] = None,
) -> None:
    """Rewrite import statements that reference one module path with another.

    This function walks the repository tree rooted at ``repo_root`` and
    rewrites absolute import statements that reference ``old_module`` or
    dotted names beginning with ``old_module.`` so that they instead refer
    to ``new_module``.  Additionally, ``from x import y`` statements are
    updated when ``x.y`` matches ``old_module``, rewriting the import to
    refer to the new module's package and name.  Relative imports (those
    with ``level > 0``) are not modified.

    Parameters
    ----------
    repo_root: Path
        The root directory of the repository.
    old_module: str
        The fully qualified name of the module or package being moved.
    new_module: str
        The fully qualified name of the module or package after the move.
    exclude_paths: Sequence[Path], optional
        A sequence of file paths to skip when rewriting imports.  Use this
        when the moved file or directory has already been relocated on
        disk; rewriting it at this point would modify the newly moved
        source unnecessarily.
    """
    exclude_set = {p.resolve() for p in (exclude_paths or [])}
    # Normalise modules for prefix matching
    old_prefix = old_module + "."
    new_prefix = new_module + "."
    for root, _, files in os.walk(repo_root):
        for filename in files:
            if not filename.endswith((".py", ".pyw")):
                continue
            file_path = Path(root) / filename
            if file_path.resolve() in exclude_set:
                continue
            update_file_imports(
                file_path,
                old_module,
                new_module,
                repo_root=repo_root,
                old_prefix=old_prefix,
                new_prefix=new_prefix,
            )


def update_file_imports(
    file_path: Path,
    old_module: str,
    new_module: str,
    *,
    repo_root: Optional[Path] = None,
    old_prefix: Optional[str] = None,
    new_prefix: Optional[str] = None,
) -> None:
    """Update import statements in a single Python file.

    Reads ``file_path``, parses it into an AST, and rewrites any import
    statements that reference ``old_module`` to instead reference
    ``new_module``.  The function will write the modified source back to
    disk only if at least one import has been changed.

    This helper is internal to the module and expects ``old_prefix`` and
    ``new_prefix`` when called from :func:`update_imports` to avoid
    recomputing them repeatedly.

    Parameters
    ----------
    file_path: Path
        The path to the Python source file.
    old_module: str
        The dotted name of the module or package being replaced.
    new_module: str
        The dotted name of the replacement module or package.
    old_prefix: str, optional
        The ``old_module`` plus a trailing dot.  Precomputed for
        efficiency.
    new_prefix: str, optional
        The ``new_module`` plus a trailing dot.  Precomputed for
        efficiency.
    """
    source = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Skip files with syntax errors (e.g. if they contain Python >=3.10 features)
        return
    modifications: List[Tuple[int, int, str]] = []  # (start_line, end_line, replacement)
    prefix = old_prefix if old_prefix is not None else old_module + "."
    newpref = new_prefix if new_prefix is not None else new_module + "."
    old_parts = old_module.split('.')
    new_parts = new_module.split('.')
    # Determine parent and base names for old and new modules for from‑import rewriting
    old_parent = '.'.join(old_parts[:-1]) if len(old_parts) > 1 else ''
    old_name = old_parts[-1]
    new_parent = '.'.join(new_parts[:-1]) if len(new_parts) > 1 else ''
    new_name = new_parts[-1]

    # Compute current module path for relative import resolution
    current_module_path: Optional[str] = None
    if repo_root is not None:
        try:
            current_module_path = compute_module_path(repo_root, file_path)
        except Exception:
            current_module_path = None

    # Helper to convert an alias into a string representation for import statements.
    # If an alias has an ``asname`` that differs from its ``name``, use the
    # ``name as asname`` form.  Otherwise return the name alone.  This avoids
    # producing redundant ``as name`` when the alias does not actually rename
    # the import.
    def alias_to_str(a: ast.alias) -> str:
        if a.asname and a.asname != a.name:
            return f"{a.name} as {a.asname}"
        return a.name

    for node in ast.walk(tree):
        # Skip nodes that are not import statements
        if isinstance(node, ast.Import):
            replaced_any = False
            new_aliases: List[ast.alias] = []
            for alias in node.names:
                name = alias.name
                if name == old_module or name.startswith(prefix):
                    # Compute new name by swapping prefix
                    if name == old_module:
                        new_name_for_alias = new_module
                    else:
                        new_name_for_alias = newpref + name[len(prefix):]
                    new_aliases.append(ast.alias(name=new_name_for_alias, asname=alias.asname))
                    replaced_any = True
                else:
                    new_aliases.append(alias)
            if replaced_any:
                # Build replacement code for the entire import statement
                parts = [alias_to_str(a) for a in new_aliases]
                new_code = f"import {', '.join(parts)}"
                # Preserve indentation for import statements that appear inside indented blocks
                indent = ' ' * getattr(node, 'col_offset', 0)
                modifications.append((node.lineno, getattr(node, 'end_lineno', node.lineno), indent + new_code))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            # Two cases: absolute import (level == 0) or relative import (level > 0)
            if node.level == 0:
                # Absolute import
                # Scenario 1: from old_module[...] import something -> update module prefix
                if module == old_module or module.startswith(prefix):
                    # Replace old_module prefix with new_module
                    if module == old_module:
                        new_module_name = new_module
                    else:
                        new_module_name = newpref + module[len(prefix):]
                    new_names = node.names  # Keep names the same
                    # Build replacement code
                    parts_list = [alias_to_str(a) for a in new_names]
                    new_code = f"from {new_module_name} import {', '.join(parts_list)}"
                    # Preserve indentation for import statements that appear inside indented blocks
                    indent = ' ' * getattr(node, 'col_offset', 0)
                    modifications.append((node.lineno, getattr(node, 'end_lineno', node.lineno), indent + new_code))
                    continue
                # Scenario 2: from old_parent import old_name -> from new_parent import new_name
                if module == old_parent:
                    # Rename aliases matching old_name
                    replaced_any = False
                    new_aliases: List[ast.alias] = []
                    for alias in node.names:
                        if alias.name == old_name:
                            # Preserve the original local name using alias.asname or alias.name
                            local_name = alias.asname or alias.name
                            new_aliases.append(ast.alias(name=new_name, asname=local_name))
                            replaced_any = True
                        else:
                            new_aliases.append(alias)
                    if replaced_any:
                        # If the new module has a parent, we can construct a from-import statement.
                        if new_parent:
                            parts_list = [alias_to_str(a) for a in new_aliases]
                            new_code = f"from {new_parent} import {', '.join(parts_list)}"
                            # Preserve indentation for import statements that appear inside indented blocks
                            indent = ' ' * getattr(node, 'col_offset', 0)
                            modifications.append((node.lineno, getattr(node, 'end_lineno', node.lineno), indent + new_code))
                        else:
                            # new_module is top-level.  We only support rewriting when a single name is imported.
                            # Otherwise we risk generating invalid code for other names.
                            if len(node.names) == 1:
                                alias_obj = new_aliases[0]
                                # alias_obj.name is new_name; alias_obj.asname is local name
                                local_name = alias_obj.asname or alias_obj.name
                                if local_name != alias_obj.name:
                                    new_code = f"import {alias_obj.name} as {local_name}"
                                else:
                                    new_code = f"import {alias_obj.name}"
                                # Preserve indentation for import statements that appear inside indented blocks
                                indent = ' ' * getattr(node, 'col_offset', 0)
                                modifications.append((node.lineno, getattr(node, 'end_lineno', node.lineno), indent + new_code))
                            # For multiple names when new_module is top-level, skip rewriting.
            else:
                # Relative import. We compute the absolute module of the imported names
                # Only proceed if repo_root and current_module_path are available
                if repo_root is None or current_module_path is None:
                    continue
                # Determine current package parts (excluding module name)
                current_parts = current_module_path.split('.')
                if not current_parts:
                    # Top-level module, cannot resolve relative import properly
                    continue
                current_package_parts = current_parts[:-1]
                # Ascend up one level less than the relative level because
                # a single leading dot means "current package", two dots
                # means parent package, etc.  Therefore we remove
                # (node.level - 1) elements from the end if possible.
                if node.level <= len(current_package_parts) + 1:
                    trim = node.level - 1
                    if trim <= 0:
                        ascend_parts = current_package_parts
                    else:
                        ascend_parts = current_package_parts[:-trim]
                else:
                    ascend_parts = []
                module_parts = (node.module.split('.') if node.module else [])
                base_parts = ascend_parts + module_parts
                actual_module = '.'.join(base_parts)
                # Track if modifications should occur
                replaced_any = False
                new_aliases: List[ast.alias] = []
                for alias in node.names:
                    alias_full_parts = base_parts + alias.name.split('.')
                    alias_full = '.'.join(alias_full_parts)
                    if alias_full == old_module or (
                        alias.name == old_name and actual_module == old_parent
                    ):
                        # Replace alias with new_name, preserving original local name via 'as'
                        local_name = alias.asname or alias.name
                        new_aliases.append(ast.alias(name=new_name, asname=local_name))
                        replaced_any = True
                    else:
                        new_aliases.append(alias)
                if replaced_any:
                    # Build new import statement.  If the moved module remains in the same package
                    # (i.e., new_parent == old_parent), we preserve the relative import syntax.
                    # Determine the replacement code string based on the new parent.
                    if new_parent == old_parent:
                        # Keep the original relative import level and module
                        module_str = node.module or ''
                        dot_prefix = '.' * node.level
                        parts_list = [alias_to_str(a) for a in new_aliases]
                        new_code = f"from {dot_prefix}{module_str} import {', '.join(parts_list)}"
                    else:
                        if new_parent:
                            parts_list = [alias_to_str(a) for a in new_aliases]
                            new_code = f"from {new_parent} import {', '.join(parts_list)}"
                        else:
                            # new module at top level: only rewrite when one alias exists
                            if len(node.names) == 1:
                                alias_obj = new_aliases[0]
                                local_name = alias_obj.asname or alias_obj.name
                                if local_name != alias_obj.name:
                                    new_code = f"import {alias_obj.name} as {local_name}"
                                else:
                                    new_code = f"import {alias_obj.name}"
                            else:
                                new_code = None
                    if new_code:
                        # Preserve indentation for import statements that appear inside indented blocks
                        indent = ' ' * getattr(node, 'col_offset', 0)
                        modifications.append((node.lineno, getattr(node, 'end_lineno', node.lineno), indent + new_code))
    # If no modifications, return early
    if not modifications:
        return
    # Sort modifications by starting line
    modifications.sort(key=lambda x: x[0])
    # Apply modifications to the source lines
    lines = source.splitlines()
    new_lines: List[str] = []
    current_line = 1
    idx = 0
    while current_line <= len(lines):
        if idx < len(modifications) and current_line == modifications[idx][0]:
            # Write new import code; ensure it ends with newline
            start_line, end_line, replacement = modifications[idx]
            new_lines.append(replacement)
            current_line = end_line + 1
            idx += 1
        else:
            new_lines.append(lines[current_line - 1])
            current_line += 1
    # Write back if changed
    new_source = "\n".join(new_lines)
    if new_source != source:
        file_path.write_text(new_source, encoding="utf-8")