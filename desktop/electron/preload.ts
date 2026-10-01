import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("shotlogfixer", {
  selectEivaFile: () => ipcRenderer.invoke("select-file", "eiva") as Promise<string | null>,
  selectRecorderFile: () => ipcRenderer.invoke("select-file", "recorder") as Promise<string | null>,
  analyseFiles: (eivaPath: string, recorderPath: string) => ipcRenderer.invoke("analyse-files", { eivaPath, recorderPath }),
  selectQcExportPath: () => ipcRenderer.invoke("select-qc-export-path") as Promise<string | null>,
  exportQc: (eivaPath: string, recorderPath: string, outputPath: string) => ipcRenderer.invoke("export-qc", { eivaPath, recorderPath, outputPath }),
  selectFixedEivaPath: (eivaPath: string) => ipcRenderer.invoke("select-fixed-eiva-path", { eivaPath }) as Promise<string | null>,
  selectFixedPairPath: (eivaPath: string, recorderPath: string) => ipcRenderer.invoke("select-fixed-pair-path", { eivaPath, recorderPath }) as Promise<{ eivaPath: string; recorderPath: string } | null>,
  saveFixedEiva: (eivaPath: string, recorderPath: string, outputPath: string) => ipcRenderer.invoke("save-fixed-eiva", { eivaPath, recorderPath, outputPath }),
  saveFixedPair: (eivaPath: string, recorderPath: string, eivaOutput: string, recorderOutput: string) => ipcRenderer.invoke("save-fixed-pair", { eivaPath, recorderPath, eivaOutput, recorderOutput }),
});
