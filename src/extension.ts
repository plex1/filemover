import * as vscode from "vscode";
import * as cp from "child_process";
import * as path from "path";
import * as fs from "fs";

function now(): string {
    return new Date().toISOString();
}

function log(msg: string) {
    // Visible in: Output → "Log (Extension Host)" and DevTools console
    console.log(`[FileMover] ${now()} ${msg}`);
}

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

        log(
            `Spawning Python helper.\n  pythonPath: ${pythonPath}\n  helperPath: ${helperPath}\n  repoRoot:   ${repoRoot}\n  renames:    ${renames.length}`
        );

        const proc = cp.spawn(pythonPath, args, {
            cwd: repoRoot,
            stdio: ["pipe", "pipe", "pipe"]
        });

        let stdout = "";
        let stderr = "";

        proc.stdout.on("data", (d) => (stdout += d.toString()));
        proc.stderr.on("data", (d) => (stderr += d.toString()));

        proc.on("error", (err) => {
            log(`Python process error: ${err.message}`);
            reject(err);
        });

        proc.on("close", (code) => {
            if (stdout.trim()) log(`Python stdout:\n${stdout.trim()}`);
            if (stderr.trim()) log(`Python stderr:\n${stderr.trim()}`);
            if (code === 0) {
                log("Python helper finished successfully.");
                resolve();
            } else {
                const msg = `Python helper exited with code ${code}`;
                log(msg);
                reject(new Error(stderr || msg));
            }
        });
    });
}

export function activate(context: vscode.ExtensionContext) {
    log("Activating extension…");

    const cfg = vscode.workspace.getConfiguration();
    const pythonPath = cfg.get<string>("filemover.pythonPath", "python");
    const extraArgs = cfg.get<string[]>("filemover.extraArgs", []);

    log(`Config loaded:\n  filemover.pythonPath = ${pythonPath}\n  filemover.extraArgs  = ${JSON.stringify(extraArgs)}`);

    const helperPath = context.asAbsolutePath(path.join("python", "rewrite_imports.py"));
    if (!fs.existsSync(helperPath)) {
        const msg = "Helper script not found: " + helperPath;
        log(msg);
        vscode.window.showErrorMessage("FileMover: " + msg);
    } else {
        log(`Helper script resolved at: ${helperPath}`);
    }

    const didRename = vscode.workspace.onDidRenameFiles(async (e) => {
        try {
            log(`onDidRenameFiles fired with ${e.files.length} item(s).`);
            if (e.files.length === 0) return;

            // Group renames by workspace root so we call the helper once per root
            const renamesByRoot = new Map<string, { oldUri: string; newUri: string }[]>();

            for (const f of e.files) {
                const root =
                    getWorkspaceRootForUri(f.newUri) || getWorkspaceRootForUri(f.oldUri);
                if (!root) {
                    log(`Skipping rename outside workspace:\n  old: ${f.oldUri.fsPath}\n  new: ${f.newUri.fsPath}`);
                    continue;
                }
                const list = renamesByRoot.get(root) || [];
                list.push({ oldUri: f.oldUri.fsPath, newUri: f.newUri.fsPath });
                renamesByRoot.set(root, list);
            }

            if (renamesByRoot.size === 0) {
                log("No renames within workspace roots. Nothing to do.");
                return;
            }

            for (const [repoRoot, renames] of renamesByRoot.entries()) {
                log(`Processing ${renames.length} rename(s) for workspace root: ${repoRoot}`);
                for (const r of renames) {
                    log(`  - ${r.oldUri}  ->  ${r.newUri}`);
                }

                const t0 = Date.now();
                await runPythonHelper(pythonPath, helperPath, repoRoot, renames, extraArgs);
                const dt = ((Date.now() - t0) / 1000).toFixed(2);
                log(`Finished updating imports for ${renames.length} rename(s) in ${dt}s (root: ${repoRoot}).`);
            }
        } catch (err: any) {
            const msg = `Import update failed: ${err?.message || String(err)}`;
            log(msg);
            vscode.window.showErrorMessage("FileMover: " + msg);
        }
    });

    context.subscriptions.push(didRename);

    log("Extension activated.");
}

export function deactivate() {
    log("Deactivating extension.");
}
