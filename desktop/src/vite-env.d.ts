import type { AnalysisResponse, ExportResponse } from "./lib/types";

type FormatResponse = { ok: boolean; profile?: any; validation?: { valid: boolean; usable_rows: number; data_rows: number; errors: string[] }; preview?: Record<string, Array<{ line: number; raw: string; cells: string[] }>>; columns?: string[]; error?: { message: string; detail?: string } };

declare global {
  const __APP_VERSION__: string;
  interface Window {
    shotlogfixerHeartbeat?: () => { ticks: number; frames: number; lastTick: number; phase: string; counters: Record<string, number> };
    shotlogfixerTest?: { setFiles: (referencePath: string, targetPath: string) => void };
    shotlogfixer: {
      diagnostics?: { isolation: string; css: string; themeStage: string; report: (snapshot: unknown) => void };
      getRendererHeartbeat: () => Promise<unknown>;
      /** The reference input is the authoritative recorder log; the target input is the EIVA log that is corrected. */
      selectReferenceFile: () => Promise<string | null>;
      selectTargetFile: () => Promise<string | null>;
      analyseFiles: (referencePath: string, targetPath: string, shotIntervalM: number, referenceProfile?: unknown, targetProfile?: unknown) => Promise<AnalysisResponse>;
      inspectFormat: (filePath: string, inputType: "EIVA" | "RECORDER") => Promise<FormatResponse>;
      previewFormat: (filePath: string, inputType: "EIVA" | "RECORDER", profile: unknown) => Promise<FormatResponse>;
      listFormatProfiles: () => Promise<{ ok: boolean; profiles?: Array<Record<string, any>>; error?: { message: string; detail?: string } }>;
      saveFormatProfile: (profile: unknown, name: string) => Promise<{ ok: boolean; profile?: Record<string, any>; error?: { message: string; detail?: string } }>;
      selectQcExportPath: (targetPath: string) => Promise<string | null>;
      exportQc: (referencePath: string, targetPath: string, outputPath: string, shotIntervalM: number, expectedHashes?: unknown, referenceProfile?: unknown, targetProfile?: unknown) => Promise<ExportResponse>;
      selectCorrectedTargetPath: (targetPath: string) => Promise<string | null>;
      saveCorrectedTarget: (referencePath: string, targetPath: string, outputPath: string, shotIntervalM: number, expectedHashes?: unknown, referenceProfile?: unknown, targetProfile?: unknown) => Promise<ExportResponse>;
    };
  }
}

export {};
