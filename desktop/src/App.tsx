import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent } from "react";
import { basename, columnAlignment, ffidJumpTargets, getCellValue, nextCycle, resolveThemePreference, statusIndices, timelineLogicalX, timelineMarkerX, timelineRecordIndexAtX } from "./lib/logic";
import type { AnalysisResponse, AnalysisSuccess, EngineRecord, ExportResponse, RecorderGapEvent, FormatProfileSummary } from "./lib/types";
import "./styles.css";
import { diagnosticOptions, diagnosticPhase, diagnosticsEnabled, useRenderDiagnostics } from "./lib/diagnostics";
import { formatDiagnostic, formatGapClassification, formatRecordStatus } from "./lib/presentation";

type Lifecycle = "idle" | "running" | "done" | "failed";
type ThemePreference = "system" | "light" | "dark";
const EMPTY_RECORDS: EngineRecord[] = [];

function markTiming(name: string, start?: string) {
  if (!diagnosticsEnabled || typeof performance === "undefined") return;
  performance.mark(name);
  if (start) {
    try { performance.measure(name, start, name); } catch { /* The mark may be the first event in a fresh renderer. */ }
  }
}

const DEFAULT_COLUMNS = ["eiva_ffid", "recorder_ffid", "eiva_coord", "recorder_coord", "distance", "status"];
const BASE_COLUMNS: Array<{ key: string; label: string }> = [
  { key: "eiva_ffid", label: "EIVA FFID" },
  { key: "recorder_ffid", label: "Recorder FFID" },
  { key: "eiva_coord", label: "EIVA Coordinate" },
  { key: "recorder_coord", label: "Recorder Coordinate" },
  { key: "distance", label: "Distance (m)" },
  { key: "status", label: "Status" },
  { key: "diagnostic", label: "Diagnostic" },
  { key: "recorder_x", label: "Recorder SOU_X" },
  { key: "recorder_y", label: "Recorder SOU_Y" },
  { key: "gap", label: "Gap" },
];

function Icon({ name }: { name: "left" | "right" | "folder" | "columns" | "download" }) {
  const paths = {
    left: <path d="m14 6-6 6 6 6M8 12h10" />,
    right: <path d="m10 6 6 6-6 6M16 12H6" />,
    folder: <path d="M3.5 6.5h6l1.5 2h9.5v9.5h-17zM3.5 6.5v-2h5l1.5 2" />,
    columns: <><path d="M4 5h16v14H4z" /><path d="M10 5v14M16 5v14" /></>,
    download: <><path d="M12 4v10M8 10l4 4 4-4M5 19h14" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="icon" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function StatusMark({ lifecycle }: { lifecycle: Lifecycle }) {
  const labels: Record<Lifecycle, string> = { idle: "Ready", running: "Analysing", done: "Analysis complete", failed: "Analysis failed" };
  return <span className={`status-mark status-mark-${lifecycle}`} aria-live="polite"><span className="status-mark-dot" />{labels[lifecycle]}</span>;
}

function FormatStatus({ kind, state, onConfigure }: { kind: "EIVA" | "RECORDER"; state: any; onConfigure: () => void }) {
  const profile = state?.profile as FormatProfileSummary | undefined;
  const ready = Boolean(profile && state?.validation?.valid && profile.confidence !== "Unresolved");
  const label = profile ? (ready ? "Ready" : profile.confidence === "Review recommended" ? "Needs review" : "Not ready") : state?.error ? "Not ready" : "Inspecting…";
  return <div className="format-status" aria-live="polite"><span className="format-role">Format</span><strong>{profile?.name || (kind === "EIVA" ? "EIVA format" : "Recorder format")}</strong><span className={`format-state ${ready ? "format-ready" : "format-review"}`}>{ready ? "✓" : "!"} {label}</span><button className="button secondary compact-button" onClick={onConfigure} disabled={!profile}>Configure</button></div>;
}

type PreviewMode = "first" | "random" | "last" | "raw";

function FormatDialog({ kind, filePath, state, onCancel, onUse, onSave }: { kind: "EIVA" | "RECORDER"; filePath: string; state: any; onCancel: () => void; onUse: (profile: any) => void; onSave: (profile: any) => void }) {
  const initial = state?.profile;
  const [working, setWorking] = useState<any>(() => initial ? JSON.parse(JSON.stringify(initial)) : null);
  const [preview, setPreview] = useState<any>(state?.preview || null);
  const [columns, setColumns] = useState<string[]>(state?.columns || []);
  const [validation, setValidation] = useState<any>(state?.validation || null);
  const [profiles, setProfiles] = useState<any[]>([]);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("first");
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onCancel(); };
    document.addEventListener("keydown", onKey);
    dialogRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  useEffect(() => {
    if (!working || !filePath) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      const response = await window.shotlogfixer.previewFormat(filePath, kind, working);
      if (!active) return;
      if (response.ok) { setPreview(response.preview); setColumns(response.columns || []); setValidation(response.validation); }
      else setValidation({ valid: false, usable_rows: 0, data_rows: 0, errors: [response.error?.detail || response.error?.message || "Format not ready"] });
    }, 120);
    return () => { active = false; window.clearTimeout(timer); };
  }, [filePath, kind, working]);

  useEffect(() => {
    let active = true;
    void window.shotlogfixer.listFormatProfiles().then((response) => {
      if (active && response.ok) setProfiles((response.profiles || []).filter((profile) => profile.input_type === kind));
    }).catch(() => undefined);
    return () => { active = false; };
  }, [kind]);

  if (!working) return null;
  const structure = working.structure || {};
  const roleNames = kind === "EIVA" ? [["FFID", "FFID"], ["EIVA_EASTING", "EIVA Easting"], ["EIVA_NORTHING", "EIVA Northing"]] : [["FFID", "FFID"], ["RECORDER_X", "Recorder X"], ["RECORDER_Y", "Recorder Y"]];
  const updateStructure = (key: string, value: unknown) => setWorking((current: any) => ({ ...current, [key === "header_mode" ? "header" : key]: value, structure: { ...current.structure, [key]: value } }));
  const updateMapping = (role: string, value: string) => setWorking((current: any) => { const mapping = { ...current.column_mapping }; if (value === "") delete mapping[role]; else mapping[role] = Number(value); return { ...current, column_mapping: mapping }; });
  const rows = preview?.[previewMode === "raw" ? "first" : previewMode] || [];
  const sourceColumns = columns.length ? columns : Object.keys(working.column_mapping || {}).map((_, index) => `Column ${index + 1}`);
  const usable = validation?.usable_rows ?? 0;
  const total = validation?.data_rows ?? 0;
  const valid = Boolean(validation?.valid && roleNames.every(([role]) => Number.isInteger(working.column_mapping?.[role])));
  return <div className="format-dialog" role="dialog" aria-modal="true" aria-labelledby="format-dialog-title"><div className="format-dialog-inner" ref={dialogRef} tabIndex={-1}>
    <div className="format-dialog-header"><div><h2 id="format-dialog-title">Configure {kind === "EIVA" ? "EIVA" : "Recorder"} Format</h2><p className="dialog-file" title={filePath}>{basename(filePath)}</p></div><button className="icon-button" onClick={onCancel} aria-label="Cancel">×</button></div>
    <div className="format-config-grid"><label>Profile<select value={working.id || ""} onChange={(event) => { const selected = profiles.find((profile) => profile.id === event.target.value); if (selected) setWorking(JSON.parse(JSON.stringify(selected))); }}><option value="">Detected format</option>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}{profile.source === "BUILTIN" ? " (built-in)" : ""}</option>)}</select></label><label>Encoding<select value={structure.encoding || "AUTO"} onChange={(event) => updateStructure("encoding", event.target.value)}><option value="AUTO">Auto</option><option value="utf-8">UTF-8</option><option value="utf-8-sig">UTF-8 BOM</option><option value="cp1252">CP1252</option><option value="latin-1">Latin-1</option></select></label></div>
    <fieldset><legend>File structure</legend><div className="choice-row"><label><input type="radio" checked={working.source !== "CUSTOM"} onChange={() => setWorking((current: any) => ({ ...current, source: "DETECTED" }))} /> Auto detect</label><label><input type="radio" checked={working.source === "CUSTOM"} onChange={() => setWorking((current: any) => ({ ...current, source: "CUSTOM" }))} /> Custom</label></div><div className="format-config-grid"><label>Delimiter<select value={structure.delimiter || "comma"} onChange={(event) => updateStructure("delimiter", event.target.value)}><option value="comma">Comma (,)</option><option value="tab">Tab</option><option value="whitespace">Whitespace</option><option value="semicolon">Semicolon (;)</option><option value="pipe">Pipe (|)</option></select></label><label>Header<select value={structure.header_mode || "ABSENT"} onChange={(event) => updateStructure("header_mode", event.target.value)}><option value="ABSENT">No header</option><option value="PRESENT">First row contains names</option></select></label><label>Skip rows<input type="number" min="0" value={structure.skip_rows ?? 0} onChange={(event) => updateStructure("skip_rows", Math.max(0, Number(event.target.value) || 0))} /></label><label className="checkbox-label"><input type="checkbox" checked={structure.trim_whitespace !== false} onChange={(event) => updateStructure("trim_whitespace", event.target.checked)} /> Trim whitespace</label></div></fieldset>
    <fieldset><legend>Field mapping</legend><div className="mapping-grid">{roleNames.map(([role, label]) => <label key={role}>{label}<select value={String(working.column_mapping?.[role] ?? "")} onChange={(event) => updateMapping(role, event.target.value)}><option value="">Unmapped</option>{sourceColumns.map((column, index) => <option key={`${role}-${index}`} value={index}>{column || `Column ${index + 1}`}</option>)}</select></label>)}</div></fieldset>
    <section className="preview-panel"><div className="preview-toolbar"><div className="preview-tabs"><button className={previewMode !== "raw" ? "active" : ""} onClick={() => setPreviewMode("first")}>Parsed</button><button className={previewMode === "raw" ? "active" : ""} onClick={() => setPreviewMode("raw")}>Raw Text</button></div><label>Preview<select value={previewMode === "raw" ? "first" : previewMode} onChange={(event) => setPreviewMode(event.target.value as PreviewMode)}><option value="first">First 20</option><option value="random">Random 20</option><option value="last">Last 20</option></select></label></div>{previewMode === "raw" ? <pre className="raw-preview raw-preview-main">{rows.map((row: any) => row.raw).join("")}</pre> : <div className="preview-table-wrap"><table className="preview-table"><thead><tr><th>Row</th>{sourceColumns.map((column, index) => <th key={index}>{column || `Column ${index + 1}`}</th>)}</tr></thead><tbody>{rows.map((row: any) => <tr key={row.line}><td>{row.line}</td>{row.cells.map((cell: string, index: number) => <td key={index}>{cell}</td>)}</tr>)}</tbody></table></div>}</section>
    <div className={`format-validation ${valid ? "is-valid" : "is-invalid"}`}><strong>{valid ? "✓ Format valid" : "✕ Format not ready"}</strong><span>{usable.toLocaleString()} data rows · {usable.toLocaleString()} usable · {Math.max(0, total - usable).toLocaleString()} malformed</span>{!valid && validation?.errors?.[0] && <small>{validation.errors[0]}</small>}</div>
    <div className="format-dialog-actions"><button className="button secondary" onClick={() => onSave(working)}>Save as Profile</button><button className="button secondary" onClick={onCancel}>Cancel</button><button className="button primary" disabled={!valid} onClick={() => onUse({ ...working, confidence: valid ? "High confidence" : working.confidence, detection_metadata: { ...(working.detection_metadata || {}), confirmed: true } })}>Use Format</button></div>
  </div></div>;
}

function CorrectionDetails({ reasons, onClose }: { reasons: string[]; onClose: () => void }) {
  const categories = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const reason of reasons) {
      const category = reason.startsWith("Unresolved REVIEW") ? "Unresolved review" : reason.startsWith("Recorder") || reason.includes("NO_SHOT") ? "Recorder or NO_SHOT review" : reason.startsWith("Ambiguous") ? "Ambiguous mapping" : "Other validation block";
      groups.set(category, [...(groups.get(category) || []), reason]);
    }
    return [...groups.entries()];
  }, [reasons]);
  return <div className="details-drawer" role="dialog" aria-modal="true" aria-label="Correction details"><div className="details-inner"><div className="format-dialog-header"><h2>Correction blocked</h2><button className="icon-button" onClick={onClose} aria-label="Close details">×</button></div><p className="dialog-file">Review the grouped conditions before saving a fixed file.</p><div className="reason-list">{categories.map(([category, values]) => <div className="reason-row" key={category}><strong>{category}</strong><span>{values.length.toLocaleString()}</span><small>{values.slice(0, 3).map((value) => formatDiagnostic(value)).join(" · ")}{values.length > 3 ? " · …" : ""}</small></div>)}</div><button className="button primary" onClick={onClose}>Close</button></div></div>;
}

function ThemePicker({ value, onChange }: { value: ThemePreference; onChange: (value: ThemePreference) => void }) {
  useRenderDiagnostics("ThemePicker");
  const [open, setOpen] = useState(false);
  useEffect(() => { diagnosticPhase(`theme-picker-open:${open}`); }, [open]);
  const options: Array<[ThemePreference, string]> = [["system", "System"], ["light", "Light"], ["dark", "Dark"]];
  return <div className="theme-picker">
    <span>Theme</span>
    <button className="theme-picker-button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((current) => !current)}>{options.find(([key]) => key === value)?.[1] || "System"}<span aria-hidden="true">⌄</span></button>
    {open && <div className="theme-picker-menu" role="listbox" aria-label="Theme preference">
      {options.map(([key, label]) => <button key={key} role="option" aria-selected={key === value} onClick={() => { markTiming("theme-option-selected"); onChange(key); setOpen(false); }}>{label}</button>)}
    </div>}
  </div>;
}

function errorMessage(response: AnalysisResponse | ExportResponse): string {
  const error = "error" in response ? response.error : undefined;
  if (error?.message) return formatDiagnostic(error.detail ? `${error.message} ${error.detail}` : error.message);
  return "The requested operation could not be completed.";
}

export default function App() {
  useRenderDiagnostics("App");
  const isolation = diagnosticOptions?.isolation || "full";
  const [eivaPath, setEivaPath] = useState("");
  const [recorderPath, setRecorderPath] = useState("");
  const [formatStates, setFormatStates] = useState<{ eiva: any; recorder: any }>({ eiva: null, recorder: null });
  const [formatOverrides, setFormatOverrides] = useState<{ eiva: any; recorder: any }>({ eiva: null, recorder: null });
  const [formatDetails, setFormatDetails] = useState<"eiva" | "recorder" | null>(null);
  const [correctionDetailsOpen, setCorrectionDetailsOpen] = useState(false);
  const [shotIntervalText, setShotIntervalText] = useState("3.125");
  const [analysis, setAnalysis] = useState<AnalysisSuccess | null>(null);
  const [lifecycle, setLifecycle] = useState<Lifecycle>("idle");
  const [error, setError] = useState("");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [themePreference, setThemePreference] = useState<ThemePreference>(() => (localStorage.getItem("shotlogfixer-theme") as ThemePreference | null) || "system");
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true);
  const [visibleColumns, setVisibleColumns] = useState<string[]>(DEFAULT_COLUMNS);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [timelineLeft, setTimelineLeft] = useState(0);
  const [timelineTooltip, setTimelineTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const timelineCanvasRef = useRef<HTMLCanvasElement>(null);
  const tableViewportRef = useRef<HTMLDivElement>(null);
  const columnsWrapRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef({ active: false, moved: false, x: 0, scrollLeft: 0 });

  const theme = resolveThemePreference(themePreference, systemDark);
  useEffect(() => {
    if (!diagnosticsEnabled) return;
    document.documentElement.dataset.diagnosticsCss = diagnosticOptions?.css || "full";
    return () => { delete document.documentElement.dataset.diagnosticsCss; };
  }, []);
  useEffect(() => {
    diagnosticPhase("theme-effect-start");
    markTiming("theme-change-start");
    document.documentElement.dataset.theme = theme;
    diagnosticPhase("theme-dom-written");
    localStorage.setItem("shotlogfixer-theme", themePreference);
    diagnosticPhase("theme-effect-complete");
    markTiming("theme-change-complete", "theme-change-start");
  }, [theme, themePreference]);
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener?.("change", onChange);
    return () => media.removeEventListener?.("change", onChange);
  }, []);
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(""), 3600); return () => window.clearTimeout(timer); }, [toast]);
  useEffect(() => {
    if (!columnsOpen) return;
    const closeOutside = (event: globalThis.MouseEvent) => {
      if (columnsWrapRef.current && !columnsWrapRef.current.contains(event.target as Node)) setColumnsOpen(false);
    };
    document.addEventListener("mousedown", closeOutside);
    return () => document.removeEventListener("mousedown", closeOutside);
  }, [columnsOpen]);
  useEffect(() => { if (analysis) markTiming("analysis-state-assigned"); }, [analysis]);
  useEffect(() => {
    if (!analysis || !diagnosticsEnabled) return;
    diagnosticPhase(`analysis-react-commit:${analysis.records.length}-rows`);
    requestAnimationFrame(() => requestAnimationFrame(() => diagnosticPhase("analysis-two-frames")));
  }, [analysis]);
  useEffect(() => {
    if (!diagnosticsEnabled) return;
    window.shotlogfixerTest = { setFiles: (eivaPath, recorderPath) => { setEivaPath(eivaPath); setRecorderPath(recorderPath); } };
    return () => { delete window.shotlogfixerTest; };
  }, []);

  const records = analysis?.records || EMPTY_RECORDS;
  const problemGroups = useMemo(() => ({
    EIVA_ONLY: statusIndices(records, "EIVA_ONLY"),
    NO_SHOT: statusIndices(records, "NO_SHOT"),
    RECORDER_INVALID: statusIndices(records, "RECORDER_INVALID"),
    REVIEW: statusIndices(records, "REVIEW"),
  }), [records]);
  const [navCurrent, setNavCurrent] = useState<Record<string, number | null>>({ EIVA_ONLY: null, NO_SHOT: null, RECORDER_INVALID: null, REVIEW: null });
  const jumpTargets = useMemo(() => ffidJumpTargets(records, analysis?.ffid_jumps || []), [analysis, records]);
  const [jumpCurrent, setJumpCurrent] = useState<number | null>(null);
  const [gapCurrent, setGapCurrent] = useState<number | null>(null);
  const allColumns = useMemo(() => [...BASE_COLUMNS, ...(analysis?.eiva_headers || []).map((header) => ({ key: `eiva_raw:${header}`, label: `EIVA ${header}` }))], [analysis]);
  const shotInterval = Number(shotIntervalText.trim().replace(",", "."));
  const validShotInterval = Number.isFinite(shotInterval) && shotInterval > 0;
  const analysisStale = Boolean(analysis && (!validShotInterval || analysis.parameters.shot_interval_m !== shotInterval));
  const profileStale = Boolean(analysis && ((formatStates.eiva?.profile?.profile_hash && analysis.input_formats?.eiva?.profile_hash !== formatStates.eiva.profile.profile_hash) || (formatStates.recorder?.profile?.profile_hash && analysis.input_formats?.recorder?.profile_hash !== formatStates.recorder.profile.profile_hash)));
  const formatBlocked = Boolean(formatStates.eiva?.profile?.confidence === "Unresolved" || formatStates.recorder?.profile?.confidence === "Unresolved" || formatStates.eiva?.validation?.valid === false || formatStates.recorder?.validation?.valid === false);
  const formatNeedsReview = Boolean(!formatOverrides.eiva && formatStates.eiva?.profile?.confidence === "Review recommended" || !formatOverrides.recorder && formatStates.recorder?.profile?.confidence === "Review recommended");
  useEffect(() => {
    let cancelled = false;
    const inspect = async (path: string, inputType: "EIVA" | "RECORDER", key: "eiva" | "recorder") => {
      if (!path) { setFormatStates((current) => ({ ...current, [key]: null })); return; }
      try {
        const response = await window.shotlogfixer.inspectFormat(path, inputType);
        if (!cancelled) setFormatStates((current) => ({ ...current, [key]: response.ok ? response : { error: response.error?.detail || response.error?.message || "Format detection failed" } }));
      } catch { if (!cancelled) setFormatStates((current) => ({ ...current, [key]: { error: "Format detection failed" } })); }
    };
    void inspect(eivaPath, "EIVA", "eiva"); void inspect(recorderPath, "RECORDER", "recorder");
    return () => { cancelled = true; };
  }, [eivaPath, recorderPath]);

  const focusRecord = (index: number) => {
    if (!records[index]) return;
    setSelectedIndex(index);
    const status = records[index].status;
    if (status !== "MATCHED") setNavCurrent((current) => ({ ...current, [status]: index }));
    const jump = jumpTargets.indexOf(index);
    if (jump >= 0) setJumpCurrent(jump);
    const viewport = tableViewportRef.current;
    const row = viewport?.querySelector<HTMLTableRowElement>(`tr[data-index="${index}"]`);
    if (viewport && row) {
      const rowTop = viewport.scrollTop + row.getBoundingClientRect().top - viewport.getBoundingClientRect().top - viewport.clientTop;
      viewport.scrollTo({ top: Math.max(0, rowTop - (viewport.clientHeight - row.clientHeight) / 2), behavior: "auto" });
    }
    const timeline = timelineRef.current;
    if (timeline) {
      const trackWidth = Math.max(1400, records.length * 5);
      const x = timelineMarkerX(records[index], trackWidth, analysis?.summary.eiva_rows || records.length);
      timeline.scrollTo({ left: Math.max(0, x - timeline.clientWidth / 2), behavior: "auto" });
    }
  };

  const navigate = (status: "EIVA_ONLY" | "NO_SHOT" | "RECORDER_INVALID" | "REVIEW", step: 1 | -1) => {
    const next = nextCycle(problemGroups[status], navCurrent[status], step);
    if (next === null) return;
    setNavCurrent((current) => ({ ...current, [status]: next }));
    focusRecord(next);
  };

  const focusIssue = (status: "EIVA_ONLY" | "NO_SHOT" | "RECORDER_INVALID" | "REVIEW") => {
    const current = navCurrent[status];
    const target = current !== null && problemGroups[status].includes(current) ? current : nextCycle(problemGroups[status], null, 1);
    if (target === null) return;
    setNavCurrent((state) => ({ ...state, [status]: target }));
    focusRecord(target);
  };

  const navigateJump = (step: 1 | -1) => {
    const next = nextCycle(jumpTargets.flatMap((target, index) => target === null ? [] : [index]), jumpCurrent, step);
    if (next === null || jumpTargets[next] === null) return;
    setJumpCurrent(next);
    focusRecord(jumpTargets[next]);
  };

  const focusJump = () => {
    if (jumpCurrent !== null && jumpTargets[jumpCurrent] !== null) focusRecord(jumpTargets[jumpCurrent]);
    else navigateJump(1);
  };

  const focusGap = (index: number) => {
    const gap = analysis?.recorder_gaps[index];
    if (!gap) return;
    setGapCurrent(index);
    const target = gap.eiva_only_indices[0] ?? gap.right_eiva_source_index ?? gap.left_eiva_source_index;
    if (target !== null && target !== undefined) focusRecord(target);
  };
  const navigateGap = (step: 1 | -1) => {
    const next = nextCycle(analysis?.recorder_gaps.map((_, index) => index) || [], gapCurrent, step);
    if (next !== null) focusGap(next);
  };

  const chooseFile = async (kind: "eiva" | "recorder") => {
    try {
      const selected = kind === "eiva" ? await window.shotlogfixer.selectEivaFile() : await window.shotlogfixer.selectRecorderFile();
      if (selected) { if (kind === "eiva") { setEivaPath(selected); setFormatOverrides((current) => ({ ...current, eiva: null })); } else { setRecorderPath(selected); setFormatOverrides((current) => ({ ...current, recorder: null })); } }
    } catch { setError("The file picker could not be opened."); setLifecycle("failed"); }
  };

  const analyse = async () => {
    diagnosticPhase("analyse-entered");
    markTiming("analyse-request-start");
    setError("");
    if (!validShotInterval) { setError("Enter a finite positive Shot Interval before analysing."); setLifecycle("failed"); return; }
    if (formatBlocked || formatNeedsReview) { setError(formatBlocked ? "Format not ready — configure the input mapping before analysing." : "Format needs review — open Configure and confirm the interpretation before analysing."); setLifecycle("failed"); return; }
    if (!eivaPath && !recorderPath) { setError("Select both an EIVA log and a recorder log before analysing."); setLifecycle("failed"); return; }
    if (!eivaPath) { setError("Select an EIVA log before analysing."); setLifecycle("failed"); return; }
    if (!recorderPath) { setError("Select a recorder log before analysing."); setLifecycle("failed"); return; }
    setAnalysis(null); setSelectedIndex(null); setLifecycle("running");
    try {
      diagnosticPhase("analyse-ipc-invoke-start");
      const response = await window.shotlogfixer.analyseFiles(eivaPath, recorderPath, shotInterval, formatOverrides.eiva, formatOverrides.recorder);
      diagnosticPhase("analyse-ipc-promise-resolved");
      markTiming("python-response-received", "analyse-request-start");
      if (diagnosticsEnabled) diagnosticPhase(`analyse-response-known:${JSON.stringify(response).length}-bytes`);
      if (!response.ok) { setError(errorMessage(response)); setLifecycle("failed"); return; }
      setAnalysis(response); if (response.input_formats) setFormatStates({ eiva: { ok: true, profile: response.input_formats.eiva, validation: { valid: true, usable_rows: response.summary.eiva_rows, data_rows: response.summary.eiva_rows } }, recorder: { ok: true, profile: response.input_formats.recorder, validation: { valid: true, usable_rows: response.summary.recorder_rows, data_rows: response.summary.recorder_rows } } }); diagnosticPhase("analyse-setAnalysis-called"); setVisibleColumns(DEFAULT_COLUMNS); setNavCurrent({ EIVA_ONLY: null, NO_SHOT: null, RECORDER_INVALID: null, REVIEW: null }); setJumpCurrent(null); setGapCurrent(null); setLifecycle("done");
    } catch { setError("The Python engine could not be reached."); setLifecycle("failed"); }
  };

  const exportQc = async () => {
    if (!analysis || analysisStale || profileStale) { setError("Analysis settings changed — re-analyse before exporting QC."); return; }
    try {
      const outputPath = await window.shotlogfixer.selectQcExportPath(eivaPath);
      if (!outputPath) return;
      const response = await window.shotlogfixer.exportQc(eivaPath, recorderPath, outputPath, shotInterval, analysis.input_hashes, analysis.input_formats?.eiva, analysis.input_formats?.recorder);
      if (!response.ok) { setError(errorMessage(response)); return; }
      setToast("QC TXT exported successfully");
    } catch { setError("The QC TXT could not be exported."); }
  };

  const correctionReady = Boolean(analysis && !analysisStale && !profileStale && analysis.correction.safe && analysis.validation.passed);
  const correctionReasons = analysis ? (analysis.correction.blocking_reasons.length ? analysis.correction.blocking_reasons : analysis.validation.errors) : [];
  const saveFixedEiva = async () => {
    if (!analysis || !correctionReady) return;
    try {
      const outputPath = await window.shotlogfixer.selectFixedEivaPath(eivaPath);
      if (!outputPath) return;
      const response = await window.shotlogfixer.saveFixedEiva(eivaPath, recorderPath, outputPath, shotInterval, analysis.input_hashes, analysis.input_formats?.eiva, analysis.input_formats?.recorder);
      if (!response.ok) { setError(errorMessage(response)); return; }
      setToast("Fixed EIVA saved successfully");
    } catch { setError("The fixed EIVA file could not be saved."); }
  };

  const saveFixedPair = async () => {
    if (!analysis || !correctionReady) return;
    try {
      const outputs = await window.shotlogfixer.selectFixedPairPath(eivaPath, recorderPath);
      if (!outputs) return;
      const response = await window.shotlogfixer.saveFixedPair(eivaPath, recorderPath, outputs.eivaPath, outputs.recorderPath, shotInterval, analysis.input_hashes, analysis.input_formats?.eiva, analysis.input_formats?.recorder);
      if (!response.ok) { setError(errorMessage(response)); return; }
      setToast("Fixed pair created; original files unchanged");
    } catch { setError("The fixed pair could not be saved."); }
  };

  const handleTimelineScroll = () => setTimelineLeft(timelineRef.current?.scrollLeft || 0);
  useEffect(() => {
    const timeline = timelineRef.current;
    if (!timeline) return;
    const wheel = (event: globalThis.WheelEvent) => {
      event.preventDefault();
      timeline.scrollLeft += Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    };
    // React's delegated wheel listener is passive in Chromium. Keep wheel panning
    // local so it can suppress vertical page scrolling reliably.
    timeline.addEventListener("wheel", wheel, { passive: false });
    return () => timeline.removeEventListener("wheel", wheel);
  }, []);
  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    const timeline = timelineRef.current;
    if (!timeline) return;
    dragRef.current = { active: true, moved: false, x: event.clientX, scrollLeft: timeline.scrollLeft };
  };
  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.active || !timelineRef.current) return;
    const delta = event.clientX - dragRef.current.x;
    if (Math.abs(delta) > 3 && !dragRef.current.moved) {
      dragRef.current.moved = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      setTimelineTooltip(null);
    }
    timelineRef.current.scrollLeft = dragRef.current.scrollLeft - delta;
  };
  const handlePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    dragRef.current.active = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const handleTimelineClick = (event: MouseEvent<HTMLDivElement>) => {
    if (dragRef.current.moved) { dragRef.current.moved = false; return; }
    if (!timelineRef.current) return;
    const x = timelineLogicalX(event.clientX, timelineRef.current.getBoundingClientRect().left + timelineRef.current.clientLeft, timelineRef.current.scrollLeft);
    const markerIndex = timelineRecordIndexAtX(records, x, timelineTrackWidth, timelineTotal);
    if (markerIndex !== null) { focusRecord(markerIndex); return; }
    const gapIndex = (analysis?.recorder_gaps || []).findIndex((gap) => {
      const left = gap.left_eiva_source_index == null ? 0 : timelineMarkerX(records[gap.left_eiva_source_index], timelineTrackWidth, timelineTotal);
      const right = gap.right_eiva_source_index == null ? left : timelineMarkerX(records[gap.right_eiva_source_index], timelineTrackWidth, timelineTotal);
      return x >= Math.min(left, right) && x <= Math.max(left, right);
    });
    if (gapIndex >= 0) { focusGap(gapIndex); return; }
    const index = timelineRecordIndexAtX(records, x, timelineTrackWidth, timelineTotal);
    if (index !== null) focusRecord(index);
  };
  const handleTimelineMove = (event: MouseEvent<HTMLCanvasElement>) => {
    if (!timelineRef.current || !records.length) return;
    if (dragRef.current.active && dragRef.current.moved) return;
    const x = timelineLogicalX(event.clientX, timelineRef.current.getBoundingClientRect().left + timelineRef.current.clientLeft, timelineRef.current.scrollLeft);
    const gap = (analysis?.recorder_gaps || []).find((candidate) => {
      const left = candidate.left_eiva_source_index == null ? 0 : timelineMarkerX(records[candidate.left_eiva_source_index], timelineTrackWidth, timelineTotal);
      const right = candidate.right_eiva_source_index == null ? left : timelineMarkerX(records[candidate.right_eiva_source_index], timelineTrackWidth, timelineTotal);
      return x >= Math.min(left, right) && x <= Math.max(left, right);
    });
    if (gap) {
      setTimelineTooltip({ x: event.clientX - timelineRef.current.getBoundingClientRect().left, y: event.clientY - timelineRef.current.getBoundingClientRect().top - 7,
        text: `Recorder Gap\n${gap.left_recorder_ffid} → ${gap.right_recorder_ffid}\n${gap.distance_m.toFixed(3)} m | ${gap.gap_span_steps} span steps\n${gap.estimated_missing_positions} estimated missing intermediate positions\n${gap.explicit_no_shot_count} explicit not-recorded rows | ${gap.unexplained_missing_positions} unexplained\n${formatGapClassification(gap.classification)}\n${formatDiagnostic(gap.diagnostic)}` });
      return;
    }
    const index = timelineRecordIndexAtX(records, x, timelineTrackWidth, timelineTotal);
    if (index === null) { setTimelineTooltip(null); return; }
    const record = records[index];
    const jump = analysis?.ffid_jumps.find((_, jumpIndex) => jumpTargets[jumpIndex] === index);
    const jumpDetail = jump ? `\nFFID jump ${jump.from} → ${jump.to}` : "";
    setTimelineTooltip({ x: event.clientX - (timelineRef.current.getBoundingClientRect().left), y: event.clientY - timelineRef.current.getBoundingClientRect().top - 7, text: (record.status === "MATCHED" ? `EIVA ${record.eiva_ffid || "—"} → Recorder ${record.recorder_ffid || "—"}\n${record.distance_m?.toFixed(3) || "—"} m` : `EIVA ${record.eiva_ffid || "—"}\n${formatRecordStatus(record.status)}`) + jumpDetail });
  };
  const handleTimelineLeave = () => setTimelineTooltip(null);

  const timelineTrackWidth = Math.max(1400, records.length * 5);
  const timelineTotal = analysis?.summary.eiva_rows || records.length;
  useEffect(() => {
    const canvas = timelineCanvasRef.current;
    if (!canvas || ["no-timeline", "no-visualizations", "header-only"].includes(isolation)) return;
    diagnosticPhase("timeline-effect-start");
    const context = canvas.getContext("2d");
    if (!context) return;
    const styles = getComputedStyle(document.documentElement);
    diagnosticPhase("timeline-style-read");
    const colors: Record<string, string> = { MATCHED: styles.getPropertyValue("--matched"), EIVA_ONLY: styles.getPropertyValue("--eiva-only"), REVIEW: styles.getPropertyValue("--review"), RECORDER_INVALID: styles.getPropertyValue("--invalid"), NO_SHOT: styles.getPropertyValue("--review") };
    context.clearRect(0, 0, timelineTrackWidth, 60);
    context.strokeStyle = styles.getPropertyValue("--border"); context.globalAlpha = 1; context.lineWidth = 1; context.beginPath(); context.moveTo(0, 30.5); context.lineTo(timelineTrackWidth, 30.5); context.stroke();
    (analysis?.recorder_gaps || []).forEach((gap) => {
      if (gap.left_eiva_source_index == null || gap.right_eiva_source_index == null) return;
      const left = timelineMarkerX(records[gap.left_eiva_source_index], timelineTrackWidth, timelineTotal);
      const right = timelineMarkerX(records[gap.right_eiva_source_index], timelineTrackWidth, timelineTotal);
      context.globalAlpha = gap.blocks_correction ? .28 : .18;
      context.fillStyle = gap.blocks_correction ? styles.getPropertyValue("--invalid") : styles.getPropertyValue("--review");
      context.fillRect(Math.min(left, right), 22, Math.max(3, Math.abs(right - left)), 17);
    });
    records.forEach((record, index) => {
      const x = timelineMarkerX(record, timelineTrackWidth, timelineTotal);
      const selected = selectedIndex === index;
      context.globalAlpha = record.status === "MATCHED" ? .55 : 1;
      context.fillStyle = colors[record.status] || colors.MATCHED;
      context.fillRect(x - (selected ? 3 : 1.5), selected ? 8 : (record.status === "MATCHED" ? 18 : 14), selected ? 6 : (record.status === "MATCHED" ? 2 : 5), selected ? 44 : (record.status === "MATCHED" ? 25 : 31));
      if (selected) { context.strokeStyle = styles.getPropertyValue("--text"); context.lineWidth = 1; context.strokeRect(x - 4, 7, 8, 46); }
    });
    context.globalAlpha = 1;
    markTiming("timeline-render-complete");
    diagnosticPhase("timeline-effect-complete");
  }, [analysis, records, selectedIndex, timelineTotal, timelineTrackWidth, theme, isolation]);

  const columns = useMemo(() => visibleColumns.map((key) => {
    const spec = allColumns.find((column) => column.key === key) || { key, label: key };
    const width = key === "diagnostic" || key.startsWith("eiva_raw:") ? 220 : key.endsWith("coord") ? 220 : key === "status" ? 160 : 130;
    return { id: key, header: spec.label, alignment: columnAlignment(key), width };
  }), [allColumns, visibleColumns]);
  const tableRecords = ["no-table", "no-visualizations", "header-only"].includes(isolation) ? [] : records;
  useLayoutEffect(() => { if (analysis) markTiming("table-render-complete"); }, [analysis, visibleColumns]);
  const visibleStart = timelineTotal ? Math.min(timelineTotal, Math.floor((timelineLeft / timelineTrackWidth) * timelineTotal) + 1) : 0;
  const visibleCount = timelineRef.current ? Math.ceil((timelineRef.current.clientWidth / timelineTrackWidth) * timelineTotal) : 0;
  const visibleEnd = timelineTotal ? Math.min(timelineTotal, visibleStart + Math.max(1, visibleCount) - 1) : 0;

  return <div className="app-shell" data-diagnostics-isolation={isolation}>
    <header className="app-header">
      <div><h1>ShotLogFixer</h1><p>Seismic acquisition QC</p></div>
      <div className="header-actions"><StatusMark lifecycle={lifecycle} /><ThemePicker value={themePreference} onChange={setThemePreference} /></div>
    </header>

    <main>
      <section className="input-section" aria-label="Input files">
        <div className="file-row"><label htmlFor="eiva-path">EIVA Log</label><input id="eiva-path" value={eivaPath ? basename(eivaPath) : "No file selected"} readOnly title={eivaPath} className={!eivaPath ? "placeholder" : ""} /><button className="button secondary" onClick={() => chooseFile("eiva")}>Browse</button></div>
        <div className="file-row"><label htmlFor="recorder-path">Recorder Log</label><input id="recorder-path" value={recorderPath ? basename(recorderPath) : "No file selected"} readOnly title={recorderPath} className={!recorderPath ? "placeholder" : ""} /><button className="button secondary" onClick={() => chooseFile("recorder")}>Browse</button></div>
        <FormatStatus kind="EIVA" state={formatStates.eiva} onConfigure={() => setFormatDetails("eiva")} />
        <FormatStatus kind="RECORDER" state={formatStates.recorder} onConfigure={() => setFormatDetails("recorder")} />
        <div className="shot-interval-row"><label htmlFor="shot-interval">Shot Interval</label><input id="shot-interval" inputMode="decimal" value={shotIntervalText} onChange={(event) => setShotIntervalText(event.target.value)} aria-invalid={shotIntervalText.length > 0 && !validShotInterval} /><span className="unit">m</span><span className="tolerance-readout">Tolerance <b>{validShotInterval ? `${(shotInterval / 2).toFixed(4).replace(/0+$/, "").replace(/\.$/, "")} m` : "—"}</b></span></div>
        <div className="input-actions">
          <button className="button primary analyse-button" onClick={analyse} disabled={lifecycle === "running" || formatBlocked || formatNeedsReview}>{lifecycle === "running" ? "ANALYSING" : "ANALYSE"}</button>
          <div className="output-actions" aria-label="Output actions">
            <button className="button secondary compact-button" onClick={exportQc} disabled={!analysis || analysisStale || profileStale}><Icon name="download" />Export QC</button>
            <button className="button secondary compact-button" onClick={saveFixedEiva} disabled={!correctionReady}>Save Fixed EIVA</button>
            <button className="button primary compact-button" onClick={saveFixedPair} disabled={!correctionReady}>Save Fixed Pair</button>
          </div>
        </div>
      </section>

      {error && <div className="error-line" role="alert"><strong>{lifecycle === "failed" ? "Analysis issue" : "Export issue"}</strong><span>{error}</span></div>}
      {(analysisStale || profileStale) && <div className="stale-line" role="status"><strong>Analysis settings changed — re-analyse</strong><span>Output actions are disabled until Shot Interval and input format profiles match the analysed values.</span></div>}
      {formatDetails && <FormatDialog kind={formatDetails === "eiva" ? "EIVA" : "RECORDER"} filePath={formatDetails === "eiva" ? eivaPath : recorderPath} state={formatStates[formatDetails]} onCancel={() => setFormatDetails(null)} onUse={(profile) => { const active = { ...profile, profile_hash: "" }; setFormatOverrides((current) => ({ ...current, [formatDetails]: active })); setFormatStates((current) => ({ ...current, [formatDetails]: { ...current[formatDetails], profile: active } })); setFormatDetails(null); }} onSave={(profile) => { const name = window.prompt("Save format profile as", profile?.name || "My format"); if (name) void window.shotlogfixer.saveFormatProfile(profile, name); }} />}

      <section className="summary-section" aria-label="Analysis summary">
        <div className="summary-line">
          <span className="summary-item">Matched <b>{analysis ? analysis.summary.matched : "—"}</b></span>
          <Counter label={formatRecordStatus("EIVA_ONLY")} status="EIVA_ONLY" count={analysis?.summary.eiva_only} current={navCurrent.EIVA_ONLY} ordinal={problemGroups.EIVA_ONLY.indexOf(navCurrent.EIVA_ONLY ?? -1) + 1} total={problemGroups.EIVA_ONLY.length} onNavigate={navigate} onFocus={focusIssue} />
          <Counter label={formatRecordStatus("NO_SHOT")} status="NO_SHOT" count={analysis ? analysis.summary.no_shot ?? 0 : undefined} current={navCurrent.NO_SHOT} ordinal={problemGroups.NO_SHOT.indexOf(navCurrent.NO_SHOT ?? -1) + 1} total={problemGroups.NO_SHOT.length} onNavigate={navigate} onFocus={focusIssue} />
          <Counter label="Invalid" status="RECORDER_INVALID" count={analysis?.summary.recorder_invalid} current={navCurrent.RECORDER_INVALID} ordinal={problemGroups.RECORDER_INVALID.indexOf(navCurrent.RECORDER_INVALID ?? -1) + 1} total={problemGroups.RECORDER_INVALID.length} onNavigate={navigate} onFocus={focusIssue} />
          <Counter label="Review" status="REVIEW" count={analysis?.summary.review} current={navCurrent.REVIEW} ordinal={problemGroups.REVIEW.indexOf(navCurrent.REVIEW ?? -1) + 1} total={problemGroups.REVIEW.length} onNavigate={navigate} onFocus={focusIssue} />
          <GapCounter gaps={analysis?.recorder_gaps || []} current={gapCurrent} onFocus={focusGap} onNavigate={navigateGap} />
        </div>
        <div className="summary-detail"><span>Total issues: <b>{analysis ? analysis.summary.total_issues : "—"}</b></span><JumpNavigation jumps={analysis?.ffid_jumps || []} current={jumpCurrent} targets={jumpTargets} onFocus={focusJump} onNavigate={navigateJump} /></div>
        {analysis && <div className={`correction-line ${correctionReady ? "correction-ready" : "correction-blocked"}`}>
          <strong>{correctionReady ? "Correction ready" : "Correction blocked"}</strong>
          <span>{correctionReady
            ? `${analysis.correction.retained.toLocaleString()} paired shots | ${analysis.summary.total_issues} issues resolved | Validation PASS`
            : `${correctionReasons.length.toLocaleString()} blocking conditions require review. `}<button className="inline-details" onClick={() => setCorrectionDetailsOpen(true)} disabled={correctionReady}>View details</button></span>
        </div>}
        {analysis && correctionDetailsOpen && <CorrectionDetails reasons={correctionReasons} onClose={() => setCorrectionDetailsOpen(false)} />}
        {analysis && <div className="correction-preview"><span>Retained / renumbered: <b>{analysis.correction.retained.toLocaleString()}</b></span><span>EIVA-only removed: <b>{analysis.correction.eiva_only_removed}</b></span><span>Not-recorded rows removed: <b>{analysis.correction.no_shot_removed}</b></span><span>Fixed pair rows: <b>{analysis.validation.fixed_eiva_rows.toLocaleString()}</b></span><span>FFID: <b>{analysis.validation.ffid_match_count}/{analysis.validation.ffid_pair_count}</b></span><span>Coordinates: <b>{analysis.validation.coordinate_pass_count}/{analysis.validation.ffid_pair_count}</b></span><span>Max EIVA–Recorder difference: <b>{analysis.validation.max_distance_m === null ? "—" : `${analysis.validation.max_distance_m.toFixed(3)} m`}</b></span></div>}
      </section>

      <section className="timeline-section" aria-label="Acquisition timeline">
        <div className="section-heading"><h2>Acquisition timeline</h2><span>Positions {analysis ? `${visibleStart}–${visibleEnd} of ${timelineTotal}` : "—"}</span></div>
        <div className="timeline-viewport" ref={timelineRef} onClick={handleTimelineClick} onScroll={handleTimelineScroll} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp}>
          <canvas ref={timelineCanvasRef} className="timeline-canvas" width={timelineTrackWidth} height={60} style={{ width: timelineTrackWidth, height: 60 }} onMouseMove={handleTimelineMove} onMouseLeave={handleTimelineLeave} aria-label="Acquisition timeline" />
          {timelineTooltip && <div className="timeline-tooltip" style={{ left: timelineTooltip.x + timelineLeft, top: timelineTooltip.y }}>{timelineTooltip.text}</div>}
        </div>
      </section>

      <section className="table-section" aria-label="QC detail">
        <div className="section-heading table-heading"><h2>QC detail</h2><div className="columns-wrap" ref={columnsWrapRef}><button className="button secondary compact-button" onClick={() => setColumnsOpen((open) => !open)} aria-expanded={columnsOpen}><Icon name="columns" />Columns</button>{columnsOpen && <div className="columns-popover"><strong>Visible columns</strong><div className="column-list">{allColumns.map((column) => <label key={column.key}><input type="checkbox" checked={visibleColumns.includes(column.key)} onChange={() => setVisibleColumns((current) => current.includes(column.key) ? current.filter((key) => key !== column.key) : [...current, column.key])} />{column.label}</label>)}</div></div>}</div></div>
        <div className="table-viewport" ref={tableViewportRef}>
          <table style={{ minWidth: columns.reduce((sum, column) => sum + column.width, 0) }}>
            <colgroup>{columns.map((column) => <col key={column.id} style={{ width: column.width }} />)}</colgroup>
            <thead><tr>{columns.map((column) => <th key={column.id} data-column={column.id} style={{ textAlign: column.alignment }}>{column.header}</th>)}</tr></thead>
            <tbody>{tableRecords.map((record, index) => <tr key={record.id} data-index={index} data-selected={selectedIndex === index} data-status={record.status} onClick={() => focusRecord(index)}>
              {columns.map((column) => <td key={column.id} data-column={column.id} style={{ textAlign: column.alignment }} className={column.id === "status" ? `status-cell status-${record.status.toLowerCase()}` : undefined}>{getCellValue(record, column.id)}</td>)}
            </tr>)}</tbody>
          </table>
          {!analysis && <div className="empty-table">Analyse a file pair to load QC detail.</div>}
        </div>
      </section>
    </main>
    <footer className="app-footer"><span>{analysis ? `${records.length.toLocaleString()} result rows` : "Ready for an offline analysis"}</span><span className="app-version">Version {__APP_VERSION__}</span></footer>
    {toast && <div className="toast" role="status">{toast}</div>}
  </div>;
}

type NavigationStatus = "EIVA_ONLY" | "NO_SHOT" | "RECORDER_INVALID" | "REVIEW";

function Counter({ label, status, count, current, ordinal, total, onNavigate, onFocus }: { label: string; status: NavigationStatus; count?: number; current: number | null; ordinal: number; total: number; onNavigate: (status: NavigationStatus, step: 1 | -1) => void; onFocus: (status: NavigationStatus) => void }) {
  return <EventNavigation className={`summary-${status.toLowerCase()}`} label={label} value={count ?? "—"} total={total} ordinal={current === null ? 1 : ordinal} onFocus={() => onFocus(status)} onNavigate={(step) => onNavigate(status, step)} />;
}

function GapCounter({ gaps, current, onFocus, onNavigate }: { gaps: RecorderGapEvent[]; current: number | null; onFocus: (index: number) => void; onNavigate: (step: 1 | -1) => void }) {
  const gap = gaps[current ?? 0];
  return <span className="summary-item summary-recorder-gap">
    {gaps.length ? <button className="summary-trigger" onClick={() => onFocus(current ?? 0)}>Recorder Gaps <b>{gaps.length}</b></button> : <>Recorder Gaps <b>0</b></>}
    {gaps.length > 1 && <span className="counter-nav"><button className="icon-button" onClick={() => onNavigate(-1)} title="Previous Recorder gap"><Icon name="left" /></button><span>{(current ?? 0) + 1} / {gaps.length}</span><button className="icon-button" onClick={() => onNavigate(1)} title="Next Recorder gap"><Icon name="right" /></button></span>}
    {gap && <span className="gap-classification" title={formatDiagnostic(gap.diagnostic)}>{formatGapClassification(gap.classification)}</span>}
  </span>;
}

function JumpNavigation({ jumps, current, targets, onFocus, onNavigate }: { jumps: Array<{ from: string; to: string }>; current: number | null; targets: Array<number | null>; onFocus: () => void; onNavigate: (step: 1 | -1) => void }) {
  return <span className="jump-navigation">
    <EventNavigation label="FFID Jumps" value={jumps.length} total={targets.some((target) => target !== null) ? jumps.length : 0} ordinal={(current ?? 0) + 1} onFocus={onFocus} onNavigate={onNavigate} />
  </span>;
}

function EventNavigation({ className = "", label, value, total, ordinal, onFocus, onNavigate }: { className?: string; label: string; value: string | number; total: number; ordinal: number; onFocus: () => void; onNavigate: (step: 1 | -1) => void }) {
  const content = <>{label} <b>{value}</b></>;
  return <span className={`summary-item ${className} ${total ? "" : "summary-inactive"}`}>
    {total ? <button className="summary-trigger" onClick={onFocus}>{content}</button> : content}
    {total > 1 && <span className="counter-nav">
      <button className="icon-button" onClick={() => onNavigate(-1)} title={`Previous ${label.toLowerCase().replace(/:$/, "")}`}><Icon name="left" /></button>
      <span>{ordinal} / {total}</span>
      <button className="icon-button" onClick={() => onNavigate(1)} title={`Next ${label.toLowerCase().replace(/:$/, "")}`}><Icon name="right" /></button>
    </span>}
  </span>;
}
