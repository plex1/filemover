import * as vscode from "vscode";
import * as cp from "child_process";
import * as path from "path";
import * as fs from "fs";

function getWorkspaceRootForUri(uri: vscode.Uri): string | undefined {
    const folder = vscode.workspace.getWorkspaceFolder(uri);
    return folder?.uri.fsPath;
}

function runPythonHelper(
    pythonPath: string,
    helperPath: string,
    repoRoot: string,
    renames: { oldUri: string; newUri: string }[],
    extraArgs: string[] = []
): Promise<void> {
    return new Promise((resolve, reject) => {
        const payload = JSON.stringify({
            repo_root: repoRoot,
            renames
        });

        const args = [...extraArgs, helperPath, payload];

        const proc = cp.spawn(pythonPath, args, {
            cwd: repoRoot,
            stdio: ["pipe", "pipe", "pipe"]
        });

        let stderr = "";
        proc.stderr.on("data", (d) => (stderr += d.toString()));

        proc.on("error", (err) => reject(err));
        proc.on("close", (code) => {
            if (code === 0) resolve();
            else reject(new Error(stderr || `Python exited with code ${code}`));
        });
    });
}

export function activate(context: vscode.ExtensionContext) {
    const cfg = vscode.workspace.getConfiguration();
    const pythonPath = cfg.get<string>("filemover.pythonPath", "python");
    const extraArgs = cfg.get<string[]>("filemover.extraArgs", []);

    const helperPath = context.asAbsolutePath(
        path.join("python", "rewrite_imports.py")
    );

    // Ensure helper file is present
    if (!fs.existsSync(helperPath)) {
        vscode.window.showErrorMessage(
            "FileMover: helper script not found in extension."
        );
    }

    // After files/folders have been renamed by VS Code
    const didRename = vscode.workspace.onDidRenameFiles(async (e) => {
        try {
            // Group renames by workspace root
            const renamesByRoot = new Map<string, { oldUri: string; newUri: string }[]>();

            for (const f of e.files) {
                const root = getWorkspaceRootForUri(f.newUri) || getWorkspaceRootForUri(f.oldUri);
                if (!root) continue; // skip if outside workspace
                const list = renamesByRoot.get(root) || [];
                list.push({ oldUri: f.oldUri.fsPath, newUri: f.newUri.fsPath });
                renamesByRoot.set(root, list);
            }

            for (const [repoRoot, renames] of renamesByRoot.entries()) {
                await runPythonHelper(pythonPath, helperPath, repoRoot, renames, extraArgs);
            }
        } catch (err: any) {
            vscode.window.showErrorMessage(`FileMover import update failed: ${err.message || String(err)}`);
        }
    });

    context.subscriptions.push(didRename);
}

export function deactivate() { }
