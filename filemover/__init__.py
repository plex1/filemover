"""
Utilities for moving Python files and folders while updating import statements.

This package provides a command‑line interface (CLI) that can relocate a single
Python source file or an entire directory of Python files within a repository.
During a move it automatically rewrites import statements in other files so
that they continue to refer to the relocated code.  The update targets only
absolute imports, leaving relative imports untouched.  It also rewrites
``from x import y`` statements when ``y`` refers to a module that has been
moved to a new package.

Example::

    # Move a module and rewrite imports
    filemover move‑file src/old_pkg/util.py src/new_pkg/utilities.py

    # Move a package and rewrite imports
    filemover move‑folder src/old_pkg src/new_namespace/old_pkg

The CLI is built on top of :mod:`click` and exposes two subcommands
``move‑file`` and ``move‑folder``.  See ``filemover.cli`` for details.
"""

__all__ = [
    "move_file",
    "move_folder",
    "update_imports",
]

from .mover import move_file, move_folder, update_imports  # noqa: F401