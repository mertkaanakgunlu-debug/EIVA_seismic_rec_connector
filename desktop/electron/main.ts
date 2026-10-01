import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { spawn } from "node:child_process";
import path from "node:path";
const projectRoot = process.env.SHOTLOGFIXER_PROJECT_ROOT || path.resolve(__dirname, "../..");

type EngineResponse = Record<string, unknown> & { ok?: boolean };

function engineCommand() {
  if (app.isPackaged) {
    return { command: path.join(process.resourcesPath, "engine", "shotlogfixer-engine.exe"), args: [] };
  }
  return {
    command: process.env.SHOTLOGFIXER_PYTHON || "python",
    args: ["-m", "shotlogfixer.engine_cli"],
  };
}

function runEngine(payload: Record<string, unknown>): Promise<EngineResponse> {
  return new Promise((resolve) => {
    const { command, args } = engineCommand();
    const child = spawn(command, args, { cwd: projectRoot, shell: false, windowsHide: true });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => { stdout += chunk; });
    child.stderr.on("data", (chunk: string) => { stderr += chunk; });
    child.on("error", (error) => resolve({ ok: false, error: { code: "ENGINE_UNAVAILABLE", message: "The Python engine could not be started.", detail: error.message } }));
    child.on("close", (code) => {
      try {
        const parsed = JSON.parse(stdout.trim()) as EngineResponse;
        if (!parsed.ok && stderr.trim() && parsed.error && typeof parsed.error === "object") {
          (parsed.error as Record<string, unknown>).detail = (parsed.error as Record<string, unknown>).detail || stderr.trim();
        }
        resolve(parsed);
      } catch {
        resolve({ ok: false, error: { code: code === 0 ? "INVALID_ENGINE_RESPONSE" : "ENGINE_FAILURE", message: "The Python engine returned an invalid response.", detail: stderr.trim() || `Exit code ${code ?? "unknown"}` } });
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 980,
    minHeight: 640,
    backgroundColor: "#0d1117",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  window.loadFile(path.join(__dirname, "../dist/index.html"));
  return window;
}

ipcMain.handle("select-file", async (_event, kind: "eiva" | "recorder") => {
  const result = await dialog.showOpenDialog({
    properties: ["openFile"],
    title: kind === "eiva" ? "Select EIVA log" : "Select recorder log",
    filters: [{ name: "Log files", extensions: ["txt", "csv", "log"] }, { name: "All files", extensions: ["*"] }],
  });
  return result.canceled ? null : result.filePaths[0] || null;
});

ipcMain.handle("analyse-files", (_event, payload: { eivaPath: string; recorderPath: string }) =>
  runEngine({ action: "analyse", eiva_path: payload.eivaPath, recorder_path: payload.recorderPath }));

ipcMain.handle("select-qc-export-path", async () => {
  const result = await dialog.showSaveDialog({
    title: "Export QC CSV",
    defaultPath: "shotlogfixer_qc.csv",
    filters: [{ name: "CSV", extensions: ["csv"] }],
  });
  return result.canceled ? null : result.filePath || null;
});

ipcMain.handle("export-qc", (_event, payload: { eivaPath: string; recorderPath: string; outputPath: string }) =>
  runEngine({ action: "export_qc", eiva_path: payload.eivaPath, recorder_path: payload.recorderPath, output_path: payload.outputPath }));

app.whenReady().then(() => {
  const window = createWindow();
  if (process.argv.includes("--smoke")) {
    window.webContents.once("did-finish-load", () => setTimeout(() => app.quit(), 350));
  }
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
