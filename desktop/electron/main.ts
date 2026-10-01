import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
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
  const devUrlArg = process.argv.find((argument) => argument.startsWith("--dev-url="));
  const devUrl = devUrlArg?.slice("--dev-url=".length);
  if (!app.isPackaged && devUrl) {
    void window.loadURL(devUrl);
  } else {
    void window.loadFile(path.join(__dirname, "../dist/index.html"));
  }
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

function fixedStem(filePath: string) {
  const parsed = path.parse(filePath);
  return path.join(parsed.dir, `${parsed.name}_fixed.txt`);
}

ipcMain.handle("select-fixed-eiva-path", async (_event, payload: { eivaPath: string }) => {
  const result = await dialog.showSaveDialog({ title: "Save Fixed EIVA", defaultPath: fixedStem(payload.eivaPath), filters: [{ name: "Text files", extensions: ["txt"] }] });
  return result.canceled ? null : result.filePath || null;
});

ipcMain.handle("select-fixed-pair-path", async (_event, payload: { eivaPath: string; recorderPath: string }) => {
  const result = await dialog.showSaveDialog({ title: "Save Fixed Pair (choose EIVA file)", defaultPath: fixedStem(payload.eivaPath), filters: [{ name: "Text files", extensions: ["txt"] }] });
  if (result.canceled || !result.filePath) return null;
  return { eivaPath: result.filePath, recorderPath: path.join(path.dirname(result.filePath), `${path.parse(payload.recorderPath).name}_fixed.txt`) };
});

async function confirmOverwrite(paths: string[]) {
  const existing = paths.filter((filePath) => filePath && existsSync(filePath));
  if (!existing.length) return true;
  const answer = await dialog.showMessageBox({ type: "warning", buttons: ["Cancel", "Overwrite"], defaultId: 0, cancelId: 0,
    title: "Confirm overwrite", message: "A fixed output already exists.", detail: existing.join("\n") });
  return answer.response === 1;
}

ipcMain.handle("save-fixed-eiva", async (_event, payload: { eivaPath: string; recorderPath: string; outputPath: string }) => {
  if (!(await confirmOverwrite([payload.outputPath]))) return { ok: false, error: { code: "SAVE_CANCELLED", message: "Save cancelled." } };
  return runEngine({ action: "save_fixed_eiva", eiva_path: payload.eivaPath, recorder_path: payload.recorderPath, output_path: payload.outputPath, overwrite: true });
});

ipcMain.handle("save-fixed-pair", async (_event, payload: { eivaPath: string; recorderPath: string; eivaOutput: string; recorderOutput: string }) => {
  if (!(await confirmOverwrite([payload.eivaOutput, payload.recorderOutput]))) return { ok: false, error: { code: "SAVE_CANCELLED", message: "Save cancelled." } };
  return runEngine({ action: "save_fixed_pair", eiva_path: payload.eivaPath, recorder_path: payload.recorderPath, eiva_output: payload.eivaOutput, recorder_output: payload.recorderOutput, overwrite: true });
});

async function runSmoke(window: BrowserWindow) {
  let failed = false;
  window.webContents.on("did-fail-load", (_event, errorCode, errorDescription) => {
    failed = true;
    console.error(`Smoke renderer load failed (${errorCode}): ${errorDescription}`);
  });
  window.webContents.once("did-finish-load", async () => {
    try {
      const result = await window.webContents.executeJavaScript(`(() => ({
        heading: document.querySelector('h1')?.textContent || '',
        rootMounted: Boolean(document.querySelector('#root')?.firstElementChild),
        bridge: Boolean(window.shotlogfixer),
        themeBefore: document.documentElement.dataset.theme || '',
      }))()`);
      if (failed || result.heading !== "ShotLogFixer" || !result.rootMounted || !result.bridge) {
        console.error("Smoke check failed: renderer did not mount the ShotLogFixer UI and preload bridge.");
        app.exit(1);
        return;
      }
      const themeResult = await window.webContents.executeJavaScript(`(() => {
        document.documentElement.dataset.theme = 'light';
        return document.documentElement.dataset.theme;
      })()`);
      if (themeResult !== "light") {
        console.error("Smoke check failed: renderer theme did not respond.");
        app.exit(1);
        return;
      }
      console.log("Electron smoke passed: React root, heading, preload bridge, and theme response verified.");
      app.exit(0);
    } catch (error) {
      console.error("Smoke check failed:", error);
      app.exit(1);
    }
  });
}

app.whenReady().then(() => {
  const window = createWindow();
  if (process.argv.includes("--smoke")) {
    void runSmoke(window);
  }
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
