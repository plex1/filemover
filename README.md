# FileMover

FileMover is a simple Python package that helps you restructure code by moving
Python files or entire directory trees within a repository while
automatically updating import statements. It rewrites absolute imports to
reflect the new locations of modules and packages. Relative imports are
preserved whenever possible. This tool can save time when refactoring
large projects by preventing broken imports after renaming or relocating
modules.

## Features

- **Move a single file**: relocate a `.py` file anywhere within your
  repository and automatically update all absolute import statements that
  reference it.
- **Move entire folders**: relocate a directory (including all
  subpackages and modules) and update imports across your code base.
- Supports both `import pkg.module` and `from pkg import module` forms.
- Automatically rewrites `from` imports into equivalent `import`
  statements when a module is moved to the top level.
- Relative imports (those starting with a leading dot) are left
  unchanged.
- Accepts relative paths for source and destination; if you omit
  `--repo‑root`, the current working directory is used as the repository
  root.

## Installation

Clone this repository and install it in editable mode using pip:

```bash
git clone <repository-url>
cd filemover
pip install -e .
```

Alternatively, install it as a regular package:

```bash
pip install .
```

This will provide a `filemover` console command via the `console_scripts`
entry point.

## Usage

Once installed, invoke the CLI with the `filemover` command. It
exposes two subcommands.

### Move a single file

Use the `move-file` command to move a single `.py` file. Provide the
source file and the destination path. If the destination is a directory
(or ends with a path separator), the original file name will be
appended. Import statements in other files will be rewritten to
reflect the new module path.

```bash
# Move a file into a subpackage (source and destination relative to the
# current directory)
filemover move-file module.py package/

# Move a file into a new module with a different name
filemover move-file old/module.py new/package/renamed_module.py --repo-root /path/to/repo

# If the repository root is different from the current directory,
# specify it explicitly
filemover move-file src/pkg/foo.py lib/pkg/foo.py --repo-root /home/user/project
```

### Move a directory

Use the `move-folder` command to move an entire directory tree. Import
statements referencing any module within the moved tree will be updated
accordingly.

```bash
# Move an entire package into another package within the repository
filemover move-folder old_pkg new_pkg

# Move a subpackage into a new parent
filemover move-folder src/util/strings core/strings --repo-root /path/to/repo
```

In both commands, if `--repo-root` is not provided, the current working
directory is used. All paths supplied to `move-file` or
`move-folder` that are not absolute will be interpreted relative to the
repository root.

## Examples

Assume you are in the root of a repository that contains a file
`module.py` and a package directory `subpackage`. To move
`module.py` into the `subpackage` directory and update imports:

```bash
# Change into your repository root
cd /path/to/your/repo

# Move the file into subpackage/ and update imports across the repo
filemover move-file module.py subpackage/
```

After running this command, the file is moved to
`subpackage/module.py`, and any absolute imports like
`import module` or `from module import …` elsewhere in the
project become `import subpackage.module` and
`from subpackage import module`.

To move a whole package:

```bash
# Move the entire 'plugins' package into 'extensions'
filemover move-folder plugins extensions
```

Imports such as `import plugins.foo` will be rewritten to
`import extensions.foo`.

## Caveats

- Only absolute imports are updated. Relative imports (e.g.,
  `from .sub import foo`) are preserved.
- The tool is conservative when rewriting `from pkg import name` where
  the new module becomes top-level: only single-name imports are
  rewritten; multiple names are left unchanged to avoid generating
  invalid code.
- Files containing syntax errors are skipped.

## Contributing

Contributions and bug reports are welcome! Please open an issue or
submit a pull request if you find a problem or have suggestions for
improvements.

## License

This project is provided for educational and refactoring purposes and
does not include a specific license. Use it at your own risk.