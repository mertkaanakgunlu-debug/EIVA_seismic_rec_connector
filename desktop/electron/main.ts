import { app, BrowserWindow, dialog, ipcMain, screen } from "electron";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
const projectRoot = app.isPackaged ? process.resourcesPath : process.env.SHOTLOGFIXER_PROJECT_ROOT || path.resolve(__dirname, "../..");
const diagnosticsEnabled = process.argv.includes("--renderer-diagnostics");
let lastHeartbeat: Record<string, unknown> | null = null;
let lastLoggedHeartbeat = "";

type EngineResponse = Record<string, unknown> & { ok?: boolean };

function engineCommand() {
  if (app.isPackaged) {
    return { command: path.join(process.resourcesPath, "engine", "shotlogfixer-engine.exe"), args: [] };
  }
  return {
    command: process.env.SHOTLOGFIXER_PYTHON || (process.platform === "win32" ? "py" : "python3"),
    args: ["-m", "shotlogfixer.engine_cli"],
  };
}

function diagnosticLog(message: string, details?: Record<string, unknown>) {
  if (!diagnosticsEnabled) return;
  console.log(`[renderer-diagnostics] ${message}${details ? ` ${JSON.stringify(details)}` : ""}`);
}

function runEngine(payload: Record<string, unknown>, label = String(payload.action || "engine")): Promise<EngineResponse> {
  return new Promise((resolve) => {
    const started = performance.now();
    const { command, args } = engineCommand();
    diagnosticLog(`${label}: spawn-start`, { command, args, cwd: projectRoot, packaged: app.isPackaged, atMs: started });
    const child = spawn(command, args, { cwd: projectRoot, shell: false, windowsHide: true });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => { stdout += chunk; });
    child.stderr.on("data", (chunk: string) => { stderr += chunk; });
    child.on("error", (error) => {
      diagnosticLog(`${label}: spawn-error`, { durationMs: performance.now() - started, message: error.message });
      resolve({ ok: false, error: { code: "ENGINE_UNAVAILABLE", message: "The Python engine could not be started.", detail: error.message } });
    });
    child.on("close", (code) => {
      const exited = performance.now();
      diagnosticLog(`${label}: process-exit`, { code, durationMs: exited - started, stdoutBytes: Buffer.byteLength(stdout), stderrBytes: Buffer.byteLength(stderr) });
      const parseStarted = performance.now();
      try {
        const parsed = JSON.parse(stdout.trim()) as EngineResponse;
        const parseEnded = performance.now();
        const records = Array.isArray(parsed.records) ? parsed.records : [];
        const rawBytes = records.reduce((total, record) => total + Buffer.byteLength(JSON.stringify((record as Record<string, unknown>).eiva_values || {})), 0);
        diagnosticLog(`${label}: json-parse`, { durationMs: parseEnded - parseStarted, jsonBytes: Buffer.byteLength(stdout), jsonMb: +(Buffer.byteLength(stdout) / 1_000_000).toFixed(3), recordCount: records.length, eivaValuesBytes: rawBytes });
        if (!parsed.ok && stderr.trim() && parsed.error && typeof parsed.error === "object") {
          (parsed.error as Record<string, unknown>).detail = (parsed.error as Record<string, unknown>).detail || stderr.trim();
        }
        diagnosticLog(`${label}: response-returned`, { durationMs: performance.now() - started });
        resolve(parsed);
      } catch {
        diagnosticLog(`${label}: json-parse-error`, { durationMs: performance.now() - parseStarted });
        resolve({ ok: false, error: { code: code === 0 ? "INVALID_ENGINE_RESPONSE" : "ENGINE_FAILURE", message: "The Python engine returned an invalid response.", detail: stderr.trim() || `Exit code ${code ?? "unknown"}` } });
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

// Preferred size shows the whole primary interface; smaller work areas (laptops) get the full work area instead.
const PREFERRED_WINDOW = { width: 1440, height: 900 };
const MINIMUM_WINDOW = { width: 960, height: 620 };

function initialWindowBounds() {
  const { workArea } = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const width = Math.min(PREFERRED_WINDOW.width, workArea.width);
  const height = Math.min(PREFERRED_WINDOW.height, workArea.height);
  return {
    x: workArea.x + Math.round((workArea.width - width) / 2),
    y: workArea.y + Math.round((workArea.height - height) / 2),
    width,
    height,
    minWidth: Math.min(MINIMUM_WINDOW.width, workArea.width),
    minHeight: Math.min(MINIMUM_WINDOW.height, workArea.height),
    maximize: width < PREFERRED_WINDOW.width || height < PREFERRED_WINDOW.height,
  };
}

function createWindow() {
  const { maximize, ...bounds } = initialWindowBounds();
  const window = new BrowserWindow({
    ...bounds,
    backgroundColor: "#0d1117",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      additionalArguments: diagnosticsEnabled ? [
        "--shotlogfixer-diagnostics",
        ...process.argv.filter((argument) => argument.startsWith("--isolation=") || argument.startsWith("--css=") || argument.startsWith("--theme-stage=")),
      ] : [],
    },
  });
  if (maximize) window.maximize();
  const devUrlArg = process.argv.find((argument) => argument.startsWith("--dev-url="));
  const devUrl = devUrlArg?.slice("--dev-url=".length);
  if (!app.isPackaged && devUrl) {
    void window.loadURL(devUrl);
  } else {
    void window.loadFile(path.join(__dirname, "../dist/index.html"));
  }
  return window;
}

function attachRendererDiagnostics(window: BrowserWindow) {
  if (!diagnosticsEnabled) return;
  const contents = window.webContents;
  contents.on("unresponsive", () => diagnosticLog("webContents.unresponsive", { url: contents.getURL(), heartbeat: lastHeartbeat }));
  contents.on("responsive", () => diagnosticLog("webContents.responsive", { heartbeat: lastHeartbeat }));
  contents.on("render-process-gone", (_event, details) => diagnosticLog("webContents.render-process-gone", { details, heartbeat: lastHeartbeat }));
  contents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL, isMainFrame) => diagnosticLog("webContents.did-fail-load", { errorCode, errorDescription, validatedURL, isMainFrame }));
  (contents as any).on("console-message", (...args: any[]) => {
    const [, second, legacyMessage, legacyLineNumber, legacySourceId] = args;
    const details = second && typeof second === "object"
      ? second
      : { level: second, message: legacyMessage, lineNumber: legacyLineNumber, sourceId: legacySourceId };
    diagnosticLog("renderer.console", {
      level: details?.level,
      message: details?.message,
      sourceId: details?.sourceId,
      lineNumber: details?.lineNumber,
    });
  });
}

// The reference input is the authoritative recorder log; the target input is the EIVA log that gets corrected.
ipcMain.handle("select-file", async (_event, kind: "reference" | "target") => {
  const result = await dialog.showOpenDialog({
    properties: ["openFile"],
    title: kind === "reference" ? "Select reference (recorder) log" : "Select target (EIVA) log to correct",
    filters: [{ name: "Log files", extensions: ["txt", "csv", "log"] }, { name: "All files", extensions: ["*"] }],
  });
  return result.canceled ? null : result.filePaths[0] || null;
});

ipcMain.on("renderer-heartbeat", (_event, snapshot: Record<string, unknown>) => {
  lastHeartbeat = snapshot;
  const marker = `${snapshot.ticks}:${snapshot.phase}`;
  if (diagnosticsEnabled && marker !== lastLoggedHeartbeat) {
    lastLoggedHeartbeat = marker;
    diagnosticLog("renderer-heartbeat", snapshot);
  }
});

ipcMain.handle("get-renderer-heartbeat", () => lastHeartbeat);

ipcMain.handle("analyse-files", (_event, payload: { referencePath: string; targetPath: string; shotIntervalM: number; referenceProfile?: unknown; targetProfile?: unknown }) => {
  diagnosticLog("analyse: ipc-request-received", { referencePath: payload.referencePath, targetPath: payload.targetPath });
  const started = performance.now();
  return runEngine({ action: "analyse", reference_path: payload.referencePath, target_path: payload.targetPath, shot_interval_m: payload.shotIntervalM, reference_profile: payload.referenceProfile, target_profile: payload.targetProfile }, "analyse").then((response) => {
    diagnosticLog("analyse: ipc-response-returned", { durationMs: performance.now() - started });
    return response;
  });
});

ipcMain.handle("inspect-format", (_event, payload: { path: string; inputType: "EIVA" | "RECORDER" }) =>
  runEngine({ action: "detect_format", path: payload.path, input_type: payload.inputType }, "detect-format"));

ipcMain.handle("preview-format", (_event, payload: { path: string; inputType: "EIVA" | "RECORDER"; profile: unknown }) =>
  runEngine({ action: "preview_format", path: payload.path, input_type: payload.inputType, profile: payload.profile }, "preview-format"));

ipcMain.handle("format-profiles", (_event, payload: { action: string; profile?: unknown; name?: string; profileId?: string }) =>
  runEngine({ action: payload.action, profile: payload.profile, name: payload.name, profile_id: payload.profileId }, "format-profile"));

ipcMain.handle("select-qc-export-path", async (_event, payload: { targetPath?: string }) => {
  const defaultPath = payload?.targetPath ? path.join(path.dirname(payload.targetPath), `${path.parse(payload.targetPath).name}_qc.txt`) : "shotlogfixer_qc.txt";
  const result = await dialog.showSaveDialog({
    title: "Export QC TXT",
    defaultPath,
    filters: [{ name: "Text files", extensions: ["txt"] }],
  });
  return result.canceled ? null : result.filePath ? ensureTxtPath(result.filePath) : null;
});

ipcMain.handle("export-qc", (_event, payload: { referencePath: string; targetPath: string; outputPath: string; shotIntervalM: number; expectedHashes?: unknown; referenceProfile?: unknown; targetProfile?: unknown }) =>
  runEngine({ action: "export_qc", reference_path: payload.referencePath, target_path: payload.targetPath, output_path: payload.outputPath, shot_interval_m: payload.shotIntervalM, expected_hashes: payload.expectedHashes, reference_profile: payload.referenceProfile, target_profile: payload.targetProfile }));

function fixedStem(filePath: string) {
  const parsed = path.parse(filePath);
  return path.join(parsed.dir, `${parsed.name}_fixed.txt`);
}

function ensureTxtPath(filePath: string) {
  const parsed = path.parse(filePath);
  return path.join(parsed.dir, `${parsed.name}.txt`);
}

// Correction writes one corrected COPY of the target (EIVA) file. The reference (recorder) file is never rewritten.
ipcMain.handle("select-corrected-target-path", async (_event, payload: { targetPath: string }) => {
  const result = await dialog.showSaveDialog({ title: "Save corrected copy of the target (EIVA) file", defaultPath: fixedStem(payload.targetPath), filters: [{ name: "Text files", extensions: ["txt"] }] });
  return result.canceled ? null : result.filePath ? ensureTxtPath(result.filePath) : null;
});

async function confirmOverwrite(paths: string[]) {
  const existing = paths.filter((filePath) => filePath && existsSync(filePath));
  if (!existing.length) return true;
  const answer = await dialog.showMessageBox({ type: "warning", buttons: ["Cancel", "Overwrite"], defaultId: 0, cancelId: 0,
    title: "Confirm overwrite", message: "A corrected output already exists.", detail: existing.join("\n") });
  return answer.response === 1;
}

ipcMain.handle("save-corrected-target", async (_event, payload: { referencePath: string; targetPath: string; outputPath: string; shotIntervalM: number; expectedHashes?: unknown; referenceProfile?: unknown; targetProfile?: unknown }) => {
  if (!(await confirmOverwrite([payload.outputPath]))) return { ok: false, error: { code: "SAVE_CANCELLED", message: "Save cancelled." } };
  return runEngine({ action: "save_corrected_target", reference_path: payload.referencePath, target_path: payload.targetPath, output_path: payload.outputPath, shot_interval_m: payload.shotIntervalM, overwrite: true, expected_hashes: payload.expectedHashes, reference_profile: payload.referenceProfile, target_profile: payload.targetProfile });
});

async function waitForFrames(window: BrowserWindow, count = 2) {
  return window.webContents.executeJavaScript(`new Promise((resolve) => { let remaining = ${count}; const next = () => requestAnimationFrame(() => { if (--remaining === 0) resolve(true); else next(); }); next(); })`);
}

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
      const heartbeatBefore = await window.webContents.executeJavaScript(`window.shotlogfixerHeartbeat?.() || null`);
      await window.webContents.executeJavaScript(`document.querySelector('.theme-picker-button')?.click()`);
      await waitForFrames(window);
      await window.webContents.executeJavaScript(`document.querySelector('.theme-picker-menu button[role="option"]:not([aria-selected="true"])')?.click()`);
      await waitForFrames(window);
      await new Promise((resolve) => setTimeout(resolve, 350));
      const themeState = await window.webContents.executeJavaScript(`({ theme: document.documentElement.dataset.theme || '', heartbeat: window.shotlogfixerHeartbeat?.() || null })`);
      if (!themeState.theme || !themeState.heartbeat || themeState.heartbeat.ticks <= (heartbeatBefore?.ticks || 0)) {
        console.error("Smoke check failed: real ThemePicker path did not preserve renderer heartbeat.");
        app.exit(1);
        return;
      }
      const columnsBefore = await window.webContents.executeJavaScript(`document.querySelector('.columns-wrap button')?.getAttribute('aria-expanded') || 'false'`);
      await window.webContents.executeJavaScript(`document.querySelector('.columns-wrap button')?.click()`);
      const columnsAfter = await window.webContents.executeJavaScript(`document.querySelector('.columns-wrap button')?.getAttribute('aria-expanded') || 'false'`);
      await window.webContents.executeJavaScript(`document.querySelector('.theme-picker-button')?.click(); document.querySelector('.theme-picker-menu button[role="option"]:not([aria-selected="true"])')?.click()`);
      await waitForFrames(window);
      await new Promise((resolve) => setTimeout(resolve, 350));
      const finalHeartbeat = await window.webContents.executeJavaScript(`window.shotlogfixerHeartbeat?.() || null`);
      if (columnsBefore === columnsAfter || !finalHeartbeat || finalHeartbeat.ticks <= themeState.heartbeat.ticks) {
        console.error("Smoke check failed: follow-up React control or second theme transition did not respond.");
        app.exit(1);
        return;
      }
      // SHOTLOGFIXER_SMOKE_RECORDER is the reference (recorder) log; SHOTLOGFIXER_SMOKE_EIVA is the target (EIVA) log.
      const smokeEiva = process.env.SHOTLOGFIXER_SMOKE_EIVA;
      const smokeRecorder = process.env.SHOTLOGFIXER_SMOKE_RECORDER;
      if (smokeEiva && smokeRecorder) {
        await window.webContents.executeJavaScript(`window.shotlogfixerTest?.setFiles(...${JSON.stringify([smokeRecorder, smokeEiva])})`);
        await waitForFrames(window);
        await window.webContents.executeJavaScript(`document.querySelector('.analyse-button')?.click()`);
        const analysisDone = await window.webContents.executeJavaScript(`new Promise((resolve) => { const started = performance.now(); const poll = () => { const text = document.querySelector('.app-footer')?.textContent || ''; if (/result rows/.test(text)) return resolve({ ok: true, text }); if (performance.now() - started > 20000) return resolve({ ok: false, text }); setTimeout(poll, 100); }; poll(); })`);
        await waitForFrames(window);
        const analysisHeartbeat = await window.webContents.executeJavaScript(`window.shotlogfixerHeartbeat?.() || null`);
        const analysisColumnsBefore = await window.webContents.executeJavaScript(`document.querySelector('.columns-wrap button')?.getAttribute('aria-expanded') || 'false'`);
        await window.webContents.executeJavaScript(`document.querySelector('.columns-wrap button')?.click()`);
        const analysisColumnsAfter = await window.webContents.executeJavaScript(`document.querySelector('.columns-wrap button')?.getAttribute('aria-expanded') || 'false'`);
        if (!analysisDone.ok || !analysisHeartbeat || analysisColumnsBefore === analysisColumnsAfter) {
          console.error("Electron analysis smoke failed: Analyse did not reach a responsive post-paint UI.");
          app.exit(1);
          return;
        }
        diagnosticLog("analysis-smoke-passed", { heartbeat: analysisHeartbeat, resultText: analysisDone.text });
        const smokeOutputDir = process.env.SHOTLOGFIXER_SMOKE_OUTPUT_DIR;
        if (smokeOutputDir) {
          mkdirSync(smokeOutputDir, { recursive: true });
          const qcPath = path.join(smokeOutputDir, "portable-smoke-qc.txt");
          const correctedPath = path.join(smokeOutputDir, "portable-smoke-eiva-corrected.txt");
          const requestBase = { reference_path: smokeRecorder, target_path: smokeEiva, shot_interval_m: 3.125 };
          const [qc, corrected] = await Promise.all([
            runEngine({ action: "export_qc", ...requestBase, output_path: qcPath }, "smoke-export-qc"),
            runEngine({ action: "save_corrected_target", ...requestBase, output_path: correctedPath, overwrite: true }, "smoke-save-corrected-target"),
          ]);
          if (!qc.ok || !corrected.ok || !existsSync(qcPath) || !existsSync(correctedPath)) {
            console.error("Electron packaged smoke failed: bundled engine did not produce validated outputs.");
            app.exit(1);
            return;
          }
          diagnosticLog("packaged-output-smoke-passed", { outputDir: smokeOutputDir, qcPath, correctedPath });
        }
      }
      console.log("Electron smoke passed: actual ThemePicker, animation frames, heartbeat, Columns, and optional bundled-output checks verified.");
      app.exit(0);
    } catch (error) {
      console.error("Smoke check failed:", error);
      app.exit(1);
    }
  });
}

app.whenReady().then(() => {
  const window = createWindow();
  attachRendererDiagnostics(window);
  if (process.argv.includes("--smoke")) {
    void runSmoke(window);
  }
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
