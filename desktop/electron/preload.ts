import { contextBridge, ipcRenderer } from "electron";

const diagnosticsEnabled = process.argv.includes("--shotlogfixer-diagnostics") || process.argv.includes("--renderer-diagnostics");

contextBridge.exposeInMainWorld("shotlogfixer", {
  getRendererHeartbeat: () => ipcRenderer.invoke("get-renderer-heartbeat"),
  ...(diagnosticsEnabled ? { diagnostics: {
    isolation: process.argv.find((arg) => arg.startsWith("--isolation="))?.split("=")[1] || "full",
    css: process.argv.find((arg) => arg.startsWith("--css="))?.split("=")[1] || "full",
    themeStage: process.argv.find((arg) => arg.startsWith("--theme-stage="))?.split("=")[1] || "full",
    report: (snapshot: unknown) => ipcRenderer.send("renderer-heartbeat", snapshot),
  } } : {}),
  selectReferenceFile: () => ipcRenderer.invoke("select-file", "reference") as Promise<string | null>,
  selectTargetFile: () => ipcRenderer.invoke("select-file", "target") as Promise<string | null>,
  analyseFiles: (referencePath: string, targetPath: string, shotIntervalM: number, referenceProfile?: unknown, targetProfile?: unknown) => ipcRenderer.invoke("analyse-files", { referencePath, targetPath, shotIntervalM, referenceProfile, targetProfile }),
  inspectFormat: (filePath: string, inputType: "EIVA" | "RECORDER") => ipcRenderer.invoke("inspect-format", { path: filePath, inputType }),
  previewFormat: (filePath: string, inputType: "EIVA" | "RECORDER", profile: unknown) => ipcRenderer.invoke("preview-format", { path: filePath, inputType, profile }),
  listFormatProfiles: () => ipcRenderer.invoke("format-profiles", { action: "list_profiles" }),
  saveFormatProfile: (profile: unknown, name: string) => ipcRenderer.invoke("format-profiles", { action: "save_profile", profile, name }),
  selectQcExportPath: (targetPath: string) => ipcRenderer.invoke("select-qc-export-path", { targetPath }) as Promise<string | null>,
  exportQc: (referencePath: string, targetPath: string, outputPath: string, shotIntervalM: number, expectedHashes?: unknown, referenceProfile?: unknown, targetProfile?: unknown) => ipcRenderer.invoke("export-qc", { referencePath, targetPath, outputPath, shotIntervalM, expectedHashes, referenceProfile, targetProfile }),
  selectCorrectedTargetPath: (targetPath: string) => ipcRenderer.invoke("select-corrected-target-path", { targetPath }) as Promise<string | null>,
  saveCorrectedTarget: (referencePath: string, targetPath: string, outputPath: string, shotIntervalM: number, expectedHashes?: unknown, referenceProfile?: unknown, targetProfile?: unknown) => ipcRenderer.invoke("save-corrected-target", { referencePath, targetPath, outputPath, shotIntervalM, expectedHashes, referenceProfile, targetProfile }),
});
