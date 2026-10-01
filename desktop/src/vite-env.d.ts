import type { AnalysisResponse, ExportResponse } from "./lib/types";

declare global {
  interface Window {
    shotlogfixerHeartbeat?: () => { ticks: number; frames: number; lastTick: number; phase: string; counters: Record<string, number> };
    shotlogfixerTest?: { setFiles: (eivaPath: string, recorderPath: string) => void };
    shotlogfixer: {
      diagnostics?: { isolation: string; css: string; themeStage: string; report: (snapshot: unknown) => void };
      getRendererHeartbeat: () => Promise<unknown>;
      selectEivaFile: () => Promise<string | null>;
      selectRecorderFile: () => Promise<string | null>;
      analyseFiles: (eivaPath: string, recorderPath: string, shotIntervalM: number) => Promise<AnalysisResponse>;
      selectQcExportPath: (eivaPath: string) => Promise<string | null>;
      exportQc: (eivaPath: string, recorderPath: string, outputPath: string, shotIntervalM: number) => Promise<ExportResponse>;
      selectFixedEivaPath: (eivaPath: string) => Promise<string | null>;
      selectFixedPairPath: (eivaPath: string, recorderPath: string) => Promise<{ eivaPath: string; recorderPath: string } | null>;
      saveFixedEiva: (eivaPath: string, recorderPath: string, outputPath: string, shotIntervalM: number) => Promise<ExportResponse>;
      saveFixedPair: (eivaPath: string, recorderPath: string, eivaOutput: string, recorderOutput: string, shotIntervalM: number) => Promise<ExportResponse>;
    };
  }
}

export {};
