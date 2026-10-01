import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("shotlogfixer", {
  selectEivaFile: () => ipcRenderer.invoke("select-file", "eiva") as Promise<string | null>,
  selectRecorderFile: () => ipcRenderer.invoke("select-file", "recorder") as Promise<string | null>,
  analyseFiles: (eivaPath: string, recorderPath: string) => ipcRenderer.invoke("analyse-files", { eivaPath, recorderPath }),
  selectQcExportPath: () => ipcRenderer.invoke("select-qc-export-path") as Promise<string | null>,
  exportQc: (eivaPath: string, recorderPath: string, outputPath: string) => ipcRenderer.invoke("export-qc", { eivaPath, recorderPath, outputPath }),
});
