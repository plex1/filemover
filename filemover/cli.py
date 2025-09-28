"""
Command‑line interface for the filemover package.

This module exposes two top‑level commands using :mod:`click`:

* ``move‑file`` – move a single Python file and update import statements.
* ``move‑folder`` – move an entire directory (including subfolders) and
  update import statements for all modules within it.

Both commands accept a ``--repo‑root`` option which defaults to the current
working directory.  The repository root determines how files are converted
into dotted import paths.  For example, if your repository root is the
directory containing ``package/__init__.py``, then the file
``package/module.py`` has the import path ``package.module``.
"""

from __future__ import annotations

import pathlib
import sys

import click

from .mover import move_file, move_folder


def resolve_paths(
    src: str, dst: str, repo_root: str | None
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Resolve source, destination and repository root paths.

    ``src`` and ``dst`` are interpreted relative to the current working
    directory unless they are absolute.  ``repo_root`` defaults to the
    current working directory.  All returned paths are absolute and
    normalised.

    Parameters
    ----------
    src: str
        The path to the file or folder to move.
    dst: str
        The desired destination path for the file or folder.  Intermediate
        directories will be created if necessary.
    repo_root: str | None
        The root of the repository.  If ``None`` then ``Path.cwd()`` is
        used.

    Returns
    -------
    tuple[pathlib.Path, pathlib.Path, pathlib.Path]
        A tuple of ``(src_path, dst_path, repo_root)``.  All three are
        absolute ``Path`` objects.  ``src_path`` and ``dst_path`` are
        normalised (no ``..`` components) and relative to ``repo_root``.
    """
    cwd = pathlib.Path.cwd()
    root = pathlib.Path(repo_root) if repo_root else cwd
    if not root.is_dir():
        raise click.UsageError(f"Repository root {root!s} does not exist or is not a directory")
    src_path = (root / src).resolve() if not pathlib.Path(src).is_absolute() else pathlib.Path(src).resolve()
    dst_path = (root / dst).resolve() if not pathlib.Path(dst).is_absolute() else pathlib.Path(dst).resolve()
    return src_path, dst_path, root


@click.group()
@click.version_option()
def cli() -> None:
    """Move Python files or folders and update import statements.

    Use one of the subcommands to relocate code within your repository
    while automatically rewriting absolute import statements in all
    affected Python files.
    """


@cli.command("move-file", help="Move a single Python file and update imports.")
@click.argument("src", type=click.Path(exists=True))
@click.argument("dst", type=click.Path())
@click.option(
    "--repo-root", "repo_root", type=click.Path(), default=None,
    help="Root directory of the repository (defaults to current working directory).",
)
def move_file_cmd(src: str, dst: str, repo_root: str | None) -> None:
    """Move a Python source file and fix imports in the repository.

    ``SRC`` is the path to the file that should be moved.  ``DST`` is the
    desired destination path for the file.  Both paths are resolved
    relative to the repository root unless they are absolute.  After
    moving the file, all absolute import statements in other Python
    files that refer to the moved module will be updated to refer to its
    new location.
    """
    src_path, dst_path, root = resolve_paths(src, dst, repo_root)
    # Ensure the source is a Python file
    if src_path.suffix != ".py":
        raise click.UsageError("move-file expects SRC to be a .py file")
    # Determine whether the destination should be treated as a directory.  If the
    # argument string ends with a path separator or points to an existing
    # directory, interpret it as a directory and append the source file name.
    dest_is_dir_hint = False
    try:
        import os as _os
        if isinstance(dst, str) and dst.endswith(_os.path.sep):
            dest_is_dir_hint = True
    except Exception:
        pass
    if (dst_path.exists() and dst_path.is_dir()) or dest_is_dir_hint:
        dst_path = (dst_path / src_path.name).resolve()
    click.echo(
        f"Moving {src_path.relative_to(root)} to {dst_path.relative_to(root)} and updating imports…"
    )
    try:
        move_file(src_path, dst_path, root)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("Done.")


@cli.command("move-folder", help="Move an entire folder of Python files and update imports.")
@click.argument("src", type=click.Path(exists=True, file_okay=False))
@click.argument("dst", type=click.Path())
@click.option(
    "--repo-root", "repo_root", type=click.Path(), default=None,
    help="Root directory of the repository (defaults to current working directory).",
)
def move_folder_cmd(src: str, dst: str, repo_root: str | None) -> None:
    """Move a directory tree and fix imports in the repository.

    ``SRC`` must be a directory path.  It will be moved to the ``DST``
    location, including all subdirectories and files.  After moving the
    directory, all absolute import statements that refer to any module
    inside the moved directory will be updated to point to the new
    package path.
    """
    src_path, dst_path, root = resolve_paths(src, dst, repo_root)
    if not src_path.is_dir():
        raise click.UsageError("move-folder expects SRC to be a directory")
    if dst_path.exists() and dst_path.is_file():
        raise click.UsageError("Destination for move-folder may not be an existing file")
    click.echo(f"Moving folder {src_path.relative_to(root)} to {dst_path.relative_to(root)} and updating imports…")
    try:
        move_folder(src_path, dst_path, root)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("Done.")


def main(argv: list[str] | None = None) -> None:
    """Entrypoint for console_scripts.

    Allows the CLI to be executed via ``python -m filemover`` or when
    installed through a ``console_scripts`` entry point.
    """
    cli.main(args=argv, standalone_mode=False)


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])