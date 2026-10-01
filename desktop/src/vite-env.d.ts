import type { AnalysisResponse, ExportResponse } from "./lib/types";

declare global {
  interface Window {
    shotlogfixer: {
      selectEivaFile: () => Promise<string | null>;
      selectRecorderFile: () => Promise<string | null>;
      analyseFiles: (eivaPath: string, recorderPath: string) => Promise<AnalysisResponse>;
      selectQcExportPath: () => Promise<string | null>;
      exportQc: (eivaPath: string, recorderPath: string, outputPath: string) => Promise<ExportResponse>;
    };
  }
}

export {};
