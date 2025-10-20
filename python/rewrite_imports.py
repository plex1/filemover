#!/usr/bin/env python
import json
import os
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: rewrite_imports.py '{\"repo_root\": \"/path\", \"renames\": [{\"oldUri\": \"/old\", \"newUri\": \"/new\"}]}'", file=sys.stderr)
        sys.exit(2)

    try:
        payload = json.loads(sys.argv[1])
        repo_root = Path(payload["repo_root"]).resolve()
        renames = payload["renames"]
    except Exception as e:
        print(f"Invalid payload: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        # Import here so extension fails gracefully if user hasn't installed filemover yet
        from filemover.mover import compute_module_path, update_imports
    except Exception as e:
        print("Could not import 'filemover'. Make sure it is installed in the selected Python environment.", file=sys.stderr)
        print(str(e), file=sys.stderr)
        sys.exit(3)

    # For each rename, compute dotted module names from old/new paths and update imports once.
    for item in renames:
        old_path = Path(item["oldUri"])
        new_path = Path(item["newUri"])

        # We rely on dotted-name computation only; existence not required
        old_module = compute_module_path(repo_root, old_path)
        new_module = compute_module_path(repo_root, new_path)

        # Rewrite absolute imports throughout the repo
        update_imports(repo_root, old_module, new_module)

    sys.exit(0)

if __name__ == "__main__":
    main()
