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
  selectEivaFile: () => ipcRenderer.invoke("select-file", "eiva") as Promise<string | null>,
  selectRecorderFile: () => ipcRenderer.invoke("select-file", "recorder") as Promise<string | null>,
  analyseFiles: (eivaPath: string, recorderPath: string, shotIntervalM: number, eivaProfile?: unknown, recorderProfile?: unknown) => ipcRenderer.invoke("analyse-files", { eivaPath, recorderPath, shotIntervalM, eivaProfile, recorderProfile }),
  inspectFormat: (filePath: string, inputType: "EIVA" | "RECORDER") => ipcRenderer.invoke("inspect-format", { path: filePath, inputType }),
  previewFormat: (filePath: string, inputType: "EIVA" | "RECORDER", profile: unknown) => ipcRenderer.invoke("preview-format", { path: filePath, inputType, profile }),
  listFormatProfiles: () => ipcRenderer.invoke("format-profiles", { action: "list_profiles" }),
  saveFormatProfile: (profile: unknown, name: string) => ipcRenderer.invoke("format-profiles", { action: "save_profile", profile, name }),
  selectQcExportPath: (eivaPath: string) => ipcRenderer.invoke("select-qc-export-path", { eivaPath }) as Promise<string | null>,
  exportQc: (eivaPath: string, recorderPath: string, outputPath: string, shotIntervalM: number, expectedHashes?: unknown, eivaProfile?: unknown, recorderProfile?: unknown) => ipcRenderer.invoke("export-qc", { eivaPath, recorderPath, outputPath, shotIntervalM, expectedHashes, eivaProfile, recorderProfile }),
  selectFixedEivaPath: (eivaPath: string) => ipcRenderer.invoke("select-fixed-eiva-path", { eivaPath }) as Promise<string | null>,
  selectFixedPairPath: (eivaPath: string, recorderPath: string) => ipcRenderer.invoke("select-fixed-pair-path", { eivaPath, recorderPath }) as Promise<{ eivaPath: string; recorderPath: string } | null>,
  saveFixedEiva: (eivaPath: string, recorderPath: string, outputPath: string, shotIntervalM: number, expectedHashes?: unknown, eivaProfile?: unknown, recorderProfile?: unknown) => ipcRenderer.invoke("save-fixed-eiva", { eivaPath, recorderPath, outputPath, shotIntervalM, expectedHashes, eivaProfile, recorderProfile }),
  saveFixedPair: (eivaPath: string, recorderPath: string, eivaOutput: string, recorderOutput: string, shotIntervalM: number, expectedHashes?: unknown, eivaProfile?: unknown, recorderProfile?: unknown) => ipcRenderer.invoke("save-fixed-pair", { eivaPath, recorderPath, eivaOutput, recorderOutput, shotIntervalM, expectedHashes, eivaProfile, recorderProfile }),
});
