import type { AnalysisResponse, ExportResponse } from "./lib/types";

declare global {
  const __APP_VERSION__: string;
  interface Window {
    shotlogfixerHeartbeat?: () => { ticks: number; frames: number; lastTick: number; phase: string; counters: Record<string, number> };
    shotlogfixerTest?: { setFiles: (eivaPath: string, recorderPath: string) => void };
    shotlogfixer: {
      diagnostics?: { isolation: string; css: string; themeStage: string; report: (snapshot: unknown) => void };
      getRendererHeartbeat: () => Promise<unknown>;
      selectEivaFile: () => Promise<string | null>;
      selectRecorderFile: () => Promise<string | null>;
      analyseFiles: (eivaPath: string, recorderPath: string, shotIntervalM: number, eivaProfile?: unknown, recorderProfile?: unknown) => Promise<AnalysisResponse>;
      inspectFormat: (filePath: string, inputType: "EIVA" | "RECORDER") => Promise<{ ok: boolean; profile?: { id: string; name: string; confidence: string; delimiter: string; header: string; profile_hash: string; column_mapping: Record<string, number> }; validation?: { valid: boolean; usable_rows: number; data_rows: number; errors: string[] }; preview?: Record<string, Array<{ line: number; raw: string; cells: string[] }>>; columns?: string[]; error?: { message: string; detail?: string } }>;
      previewFormat: (filePath: string, inputType: "EIVA" | "RECORDER", profile: unknown) => Promise<{ ok: boolean; profile?: any; validation?: { valid: boolean; usable_rows: number; data_rows: number; errors: string[] }; preview?: Record<string, Array<{ line: number; raw: string; cells: string[] }>>; columns?: string[]; error?: { message: string; detail?: string } }>;
      listFormatProfiles: () => Promise<{ ok: boolean; profiles?: Array<Record<string, any>>; error?: { message: string; detail?: string } }>;
      saveFormatProfile: (profile: unknown, name: string) => Promise<{ ok: boolean; profile?: Record<string, any>; error?: { message: string; detail?: string } }>;
      selectQcExportPath: (eivaPath: string) => Promise<string | null>;
      exportQc: (eivaPath: string, recorderPath: string, outputPath: string, shotIntervalM: number, expectedHashes?: unknown, eivaProfile?: unknown, recorderProfile?: unknown) => Promise<ExportResponse>;
      selectFixedEivaPath: (eivaPath: string) => Promise<string | null>;
      selectFixedPairPath: (eivaPath: string, recorderPath: string) => Promise<{ eivaPath: string; recorderPath: string } | null>;
      saveFixedEiva: (eivaPath: string, recorderPath: string, outputPath: string, shotIntervalM: number, expectedHashes?: unknown, eivaProfile?: unknown, recorderProfile?: unknown) => Promise<ExportResponse>;
      saveFixedPair: (eivaPath: string, recorderPath: string, eivaOutput: string, recorderOutput: string, shotIntervalM: number, expectedHashes?: unknown, eivaProfile?: unknown, recorderProfile?: unknown) => Promise<ExportResponse>;
    };
  }
}

export {};
