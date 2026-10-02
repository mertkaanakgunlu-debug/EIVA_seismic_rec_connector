import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent, type PointerEvent } from "react";
import { basename, columnAlignment, ffidJumpTargets, getCellValue, GROUP_KEYS, groupIndices, loadColumnOrder, mergeColumnOrder, moveColumn, nextCycle, orderedVisibleColumns, recordTone, resolveThemePreference, saveColumnOrder, timelineLogicalX, timelineMarkerX, timelineRecordIndexAtX, type GroupKey } from "./lib/logic";
import type { AnalysisResponse, AnalysisSuccess, CorrectionBlocker, EngineRecord, ExportResponse, FormatProfileSummary, QcFinding } from "./lib/types";
import "./styles.css";
import { diagnosticOptions, diagnosticPhase, diagnosticsEnabled, useRenderDiagnostics } from "./lib/diagnostics";
import { describeFinding, describeRecord, formatAssociation, formatBlocker, formatQcCode, type QcDescription } from "./lib/presentation";
import { FloatingTooltip, Popover } from "./Popover";

type Lifecycle = "idle" | "running" | "done" | "failed";
type ThemePreference = "system" | "light" | "dark";
type Role = "reference" | "target";
const EMPTY_RECORDS: EngineRecord[] = [];
const EMPTY_NAV: Record<GroupKey, number | null> = { TARGET_ONLY: null, NEEDS_REVIEW: null, INVALID: null, BLOCKED: null, QC_SEVERE: null, QC_WARNING: null, POSITION_JUMP: null };

function markTiming(name: string, start?: string) {
  if (!diagnosticsEnabled || typeof performance === "undefined") return;
  performance.mark(name);
  if (start) {
    try { performance.measure(name, start, name); } catch { /* The mark may be the first event in a fresh renderer. */ }
  }
}

const DEFAULT_COLUMNS = ["reference_ffid", "target_ffid", "corrected_ffid", "reference_coord", "target_coord", "distance", "association", "qc"];
const BASE_COLUMNS: Array<{ key: string; label: string }> = [
  { key: "reference_ffid", label: "Recorder FFID" },
  { key: "target_ffid", label: "EIVA Original FFID" },
  { key: "corrected_ffid", label: "Corrected FFID" },
  { key: "reference_coord", label: "Recorder Coordinate" },
  { key: "target_coord", label: "EIVA Coordinate" },
  { key: "distance", label: "Distance (m)" },
  { key: "association", label: "Match" },
  { key: "qc", label: "QC" },
  { key: "basis", label: "Basis" },
  { key: "confidence", label: "Confidence" },
  { key: "diagnostic", label: "QC note" },
  { key: "reference_line", label: "Recorder Line" },
  { key: "target_line", label: "EIVA Line" },
];

function Icon({ name }: { name: "left" | "right" | "folder" | "columns" | "download" | "gear" | "sliders" | "chevron" }) {
  const paths = {
    left: <path d="m14 6-6 6 6 6M8 12h10" />,
    right: <path d="m10 6 6 6-6 6M16 12H6" />,
    folder: <path d="M3.5 6.5h6l1.5 2h9.5v9.5h-17zM3.5 6.5v-2h5l1.5 2" />,
    columns: <><path d="M4 5h16v14H4z" /><path d="M10 5v14M16 5v14" /></>,
    download: <><path d="M12 4v10M8 10l4 4 4-4M5 19h14" /></>,
    gear: <><circle cx="12" cy="12" r="3" /><circle cx="12" cy="12" r="6.5" /><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" /></>,
    chevron: <path d="m7 10 5 5 5-5" />,
    sliders: <><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="icon" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function StatusMark({ lifecycle }: { lifecycle: Lifecycle }) {
  const labels: Record<Lifecycle, string> = { idle: "Ready", running: "Analysing", done: "Analysis complete", failed: "Analysis failed" };
  return <span className={`status-mark status-mark-${lifecycle}`} aria-live="polite"><span className="status-mark-dot" />{labels[lifecycle]}</span>;
}

// "RECORDER" / "EIVA" are the stored profile slots: RECORDER profiles describe the authoritative reference input, EIVA profiles the target.
function formatReadiness(state: any) {
  const profile = state?.profile as FormatProfileSummary | undefined;
  const ready = Boolean(profile && state?.validation?.valid && profile.confidence !== "Unresolved");
  const label = profile ? (ready ? "Ready" : profile.confidence === "Review recommended" ? "Needs review" : "Not ready") : state?.error ? "Not ready" : "Inspecting…";
  return { profile, ready, label };
}

/** Subordinate, inline readiness of the detected input format; shown inside the file field. */
function FormatBadge({ kind, state }: { kind: "EIVA" | "RECORDER"; state: any }) {
  const { profile, ready, label } = formatReadiness(state);
  const name = profile?.name || (kind === "EIVA" ? "Target format" : "Reference format");
  return <span className={`format-badge ${ready ? "format-ready" : "format-review"}`} aria-live="polite" title={`Format: ${name} (${label})`}>
    <span aria-hidden="true">{ready ? "✓" : "!"}</span><span className="format-badge-name">{profile ? `${name} · ${label}` : label}</span>
  </span>;
}

function ConfigureFormatButton({ kind, state, onConfigure }: { kind: "EIVA" | "RECORDER"; state: any; onConfigure: () => void }) {
  const { profile } = formatReadiness(state);
  const label = `Configure ${kind === "EIVA" ? "target (EIVA)" : "reference (recorder)"} format`;
  return <button className="button secondary icon-only-button" onClick={onConfigure} disabled={!profile} aria-label={label} title={profile ? `${label}: ${profile.name}` : label}><Icon name="gear" /></button>;
}

/** The shot interval drives QC distance bands and the alignment distance cap; it lives in a compact settings panel. */
function AnalysisSettings({ value, onChange, valid, interval }: { value: string; onChange: (value: string) => void; valid: boolean; interval: number }) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => document.getElementById("shot-interval")?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);
  return <>
    <button ref={buttonRef} className={`settings-button${valid ? "" : " is-invalid"}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((current) => !current)} title={valid ? `Shot interval ${interval} m` : "Shot interval needs a finite positive value"}><Icon name="sliders" />Settings</button>
    {open && <Popover anchorRef={buttonRef} onClose={() => setOpen(false)} className="settings-panel" role="dialog" aria-label="Settings">
      <strong>Settings</strong>
      <div className="settings-group">QC</div>
      <div className="settings-field"><label htmlFor="shot-interval">Shot interval</label><input id="shot-interval" inputMode="decimal" value={value} onChange={(event) => onChange(event.target.value)} aria-invalid={value.length > 0 && !valid} /><span className="unit">m</span></div>
      <div className="settings-field settings-readout"><span className="settings-label">Normal QC distance</span><b>{valid ? `${(interval / 2).toFixed(4).replace(/0+$/, "").replace(/\.$/, "")} m` : "—"}</b><span className="settings-calculated">calculated</span></div>
      <p className="settings-note">Normal QC distance is half the shot interval. The shot interval sets the QC distance bands; it never rejects a recorder record. Re-analyse after changing it.</p>
    </Popover>}
  </>;
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
  const roleNames = kind === "EIVA" ? [["FFID", "FFID (replaced in the corrected copy)"], ["EIVA_EASTING", "Easting / X"], ["EIVA_NORTHING", "Northing / Y"]] : [["FFID", "FFID (authoritative)"], ["RECORDER_X", "X / Easting"], ["RECORDER_Y", "Y / Northing"]];
  const updateStructure = (key: string, value: unknown) => setWorking((current: any) => ({ ...current, [key === "header_mode" ? "header" : key]: value, structure: { ...current.structure, [key]: value } }));
  const updateMapping = (role: string, value: string) => setWorking((current: any) => { const mapping = { ...current.column_mapping }; if (value === "") delete mapping[role]; else mapping[role] = Number(value); return { ...current, column_mapping: mapping }; });
  const rows = preview?.[previewMode === "raw" ? "first" : previewMode] || [];
  const sourceColumns = columns.length ? columns : Object.keys(working.column_mapping || {}).map((_, index) => `Column ${index + 1}`);
  const usable = validation?.usable_rows ?? 0;
  const total = validation?.data_rows ?? 0;
  const valid = Boolean(validation?.valid && roleNames.every(([role]) => Number.isInteger(working.column_mapping?.[role])));
  return <div className="format-dialog" role="dialog" aria-modal="true" aria-labelledby="format-dialog-title"><div className="format-dialog-inner" ref={dialogRef} tabIndex={-1}>
    <div className="format-dialog-header"><div><h2 id="format-dialog-title">Configure {kind === "EIVA" ? "Target (EIVA)" : "Reference (Recorder)"} Format</h2><p className="dialog-file" title={filePath}>{basename(filePath)}</p></div><button className="icon-button" onClick={onCancel} aria-label="Cancel">×</button></div>
    <div className="format-config-grid"><label>Profile<select value={working.id || ""} onChange={(event) => { const selected = profiles.find((profile) => profile.id === event.target.value); if (selected) setWorking(JSON.parse(JSON.stringify(selected))); }}><option value="">Detected format</option>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}{profile.source === "BUILTIN" ? " (built-in)" : ""}</option>)}</select></label><label>Encoding<select value={structure.encoding || "AUTO"} onChange={(event) => updateStructure("encoding", event.target.value)}><option value="AUTO">Auto</option><option value="utf-8">UTF-8</option><option value="utf-8-sig">UTF-8 BOM</option><option value="cp1252">CP1252</option><option value="latin-1">Latin-1</option></select></label></div>
    <fieldset><legend>File structure</legend><div className="choice-row"><label><input type="radio" checked={working.source !== "CUSTOM"} onChange={() => setWorking((current: any) => ({ ...current, source: "DETECTED" }))} /> Auto detect</label><label><input type="radio" checked={working.source === "CUSTOM"} onChange={() => setWorking((current: any) => ({ ...current, source: "CUSTOM" }))} /> Custom</label></div><div className="format-config-grid"><label>Delimiter<select value={structure.delimiter || "comma"} onChange={(event) => updateStructure("delimiter", event.target.value)}><option value="comma">Comma (,)</option><option value="tab">Tab</option><option value="whitespace">Whitespace</option><option value="semicolon">Semicolon (;)</option><option value="pipe">Pipe (|)</option></select></label><label>Header<select value={structure.header_mode || "ABSENT"} onChange={(event) => updateStructure("header_mode", event.target.value)}><option value="ABSENT">No header</option><option value="PRESENT">First row contains names</option></select></label><label>Skip rows<input type="number" min="0" value={structure.skip_rows ?? 0} onChange={(event) => updateStructure("skip_rows", Math.max(0, Number(event.target.value) || 0))} /></label><label className="checkbox-label"><input type="checkbox" checked={structure.trim_whitespace !== false} onChange={(event) => updateStructure("trim_whitespace", event.target.checked)} /> Trim whitespace</label></div></fieldset>
    <fieldset><legend>Field mapping</legend><div className="mapping-grid">{roleNames.map(([role, label]) => <label key={role}>{label}<select value={String(working.column_mapping?.[role] ?? "")} onChange={(event) => updateMapping(role, event.target.value)}><option value="">Unmapped</option>{sourceColumns.map((column, index) => <option key={`${role}-${index}`} value={index}>{column || `Column ${index + 1}`}</option>)}</select></label>)}</div></fieldset>
    <section className="preview-panel"><div className="preview-toolbar"><div className="preview-tabs"><button className={previewMode !== "raw" ? "active" : ""} onClick={() => setPreviewMode("first")}>Parsed</button><button className={previewMode === "raw" ? "active" : ""} onClick={() => setPreviewMode("raw")}>Raw Text</button></div><label>Preview<select value={previewMode === "raw" ? "first" : previewMode} onChange={(event) => setPreviewMode(event.target.value as PreviewMode)}><option value="first">First 20</option><option value="random">Random 20</option><option value="last">Last 20</option></select></label></div>{previewMode === "raw" ? <pre className="raw-preview raw-preview-main">{rows.map((row: any) => row.raw).join("")}</pre> : <div className="preview-table-wrap"><table className="preview-table"><thead><tr><th>Row</th>{sourceColumns.map((column, index) => <th key={index}>{column || `Column ${index + 1}`}</th>)}</tr></thead><tbody>{rows.map((row: any) => <tr key={row.line}><td>{row.line}</td>{row.cells.map((cell: string, index: number) => <td key={index}>{cell}</td>)}</tr>)}</tbody></table></div>}</section>
    <div className={`format-validation ${valid ? "is-valid" : "is-invalid"}`}><strong>{valid ? "✓ Format valid" : "✕ Format not ready"}</strong><span>{usable.toLocaleString()} data rows · {usable.toLocaleString()} usable · {Math.max(0, total - usable).toLocaleString()} malformed</span>{!valid && validation?.errors?.[0] && <small>{validation.errors[0]}</small>}</div>
    <div className="format-dialog-actions"><button className="button secondary" onClick={() => onSave(working)}>Save as Profile</button><button className="button secondary" onClick={onCancel}>Cancel</button><button className="button primary" disabled={!valid} onClick={() => onUse({ ...working, confidence: valid ? "High confidence" : working.confidence, detection_metadata: { ...(working.detection_metadata || {}), confirmed: true } })}>Use Format</button></div>
  </div></div>;
}

/** Structural impossibilities only. QC observations never appear here: they do not block a corrected copy. */
function CorrectionDetails({ blockers, onClose }: { blockers: CorrectionBlocker[]; onClose: () => void }) {
  return <div className="details-drawer" role="dialog" aria-modal="true" aria-label="Correction details"><div className="details-inner"><div className="format-dialog-header"><h2>Correction blocked</h2><button className="icon-button" onClick={onClose} aria-label="Close details">×</button></div><p className="dialog-file">These conditions make a corrected copy impossible. QC warnings never block output.</p><div className="reason-list">{blockers.map((blocker) => <div className="reason-row" key={`${blocker.code}-${blocker.message}`}><strong>{formatBlocker(blocker.code)}</strong><small title={blocker.message}>{blocker.message}</small></div>)}</div><button className="button primary" onClick={onClose}>Close</button></div></div>;
}

function ThemePicker({ value, onChange }: { value: ThemePreference; onChange: (value: ThemePreference) => void }) {
  useRenderDiagnostics("ThemePicker");
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { diagnosticPhase(`theme-picker-open:${open}`); }, [open]);
  const options: Array<[ThemePreference, string]> = [["system", "System"], ["light", "Light"], ["dark", "Dark"]];
  return <div className="theme-picker">
    <span>Theme</span>
    <button ref={buttonRef} className="theme-picker-button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((current) => !current)}>{options.find(([key]) => key === value)?.[1] || "System"}<span aria-hidden="true">⌄</span></button>
    {open && <Popover anchorRef={buttonRef} onClose={() => setOpen(false)} matchAnchorWidth className="theme-picker-menu" role="listbox" aria-label="Theme preference">
      {options.map(([key, label]) => <button key={key} role="option" aria-selected={key === value} onClick={() => { markTiming("theme-option-selected"); onChange(key); setOpen(false); }}>{label}</button>)}
    </Popover>}
  </div>;
}

function errorMessage(response: AnalysisResponse | ExportResponse): string {
  const error = "error" in response ? response.error : undefined;
  if (error?.message) return error.detail ? `${error.message} ${error.detail}` : error.message;
  return "The requested operation could not be completed.";
}

export default function App() {
  useRenderDiagnostics("App");
  const isolation = diagnosticOptions?.isolation || "full";
  const [referencePath, setReferencePath] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const [formatStates, setFormatStates] = useState<{ reference: any; target: any }>({ reference: null, target: null });
  const [formatOverrides, setFormatOverrides] = useState<{ reference: any; target: any }>({ reference: null, target: null });
  const [formatDetails, setFormatDetails] = useState<Role | null>(null);
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
  // The operator's QC column order, kept in local storage only (no engine setting, no file).
  const [columnOrderPreference, setColumnOrderPreference] = useState<string[] | null>(() => loadColumnOrder(window.localStorage));
  const [columnDrag, setColumnDrag] = useState<{ key: string; dropIndex: number; left: number } | null>(null);
  const columnDragRef = useRef<{ key: string; x: number; started: boolean } | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const detailsButtonRef = useRef<HTMLButtonElement>(null);
  const [toast, setToast] = useState("");
  const [timelineLeft, setTimelineLeft] = useState(0);
  const [timelineTooltip, setTimelineTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const timelineCanvasRef = useRef<HTMLCanvasElement>(null);
  const tableViewportRef = useRef<HTMLDivElement>(null);
  const columnsButtonRef = useRef<HTMLButtonElement>(null);
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
  useEffect(() => { if (analysis) markTiming("analysis-state-assigned"); }, [analysis]);
  useEffect(() => {
    if (!analysis || !diagnosticsEnabled) return;
    diagnosticPhase(`analysis-react-commit:${analysis.records.length}-rows`);
    requestAnimationFrame(() => requestAnimationFrame(() => diagnosticPhase("analysis-two-frames")));
  }, [analysis]);
  useEffect(() => {
    if (!diagnosticsEnabled) return;
    window.shotlogfixerTest = { setFiles: (reference, target) => { setReferencePath(reference); setTargetPath(target); } };
    return () => { delete window.shotlogfixerTest; };
  }, []);

  const records = analysis?.records || EMPTY_RECORDS;
  const problemGroups = useMemo(() => groupIndices(records), [records]);
  const [navCurrent, setNavCurrent] = useState<Record<GroupKey, number | null>>(EMPTY_NAV);
  const jumpTargets = useMemo(() => ffidJumpTargets(records, analysis?.qc.ffid_jumps || []), [analysis, records]);
  const [jumpCurrent, setJumpCurrent] = useState<number | null>(null);
  const allColumns = useMemo(() => [...BASE_COLUMNS, ...(analysis?.target_headers || []).map((header) => ({ key: `target_raw:${header}`, label: `EIVA ${header}` }))], [analysis]);
  const columnOrder = useMemo(() => mergeColumnOrder(columnOrderPreference, allColumns.map((column) => column.key)), [allColumns, columnOrderPreference]);
  const findingsByRow = useMemo(() => {
    const rank: Record<string, number> = { SEVERE: 0, WARNING: 1, INFO: 2 };
    const byRow = new Map<string, QcFinding[]>();
    for (const finding of analysis?.qc.findings || []) if (finding.row_id) byRow.set(finding.row_id, [...(byRow.get(finding.row_id) || []), finding]);
    for (const list of byRow.values()) list.sort((a, b) => rank[a.severity] - rank[b.severity]);
    return byRow;
  }, [analysis]);
  const generalFindings = useMemo(() => (analysis?.qc.findings || []).filter((finding) => !finding.row_id), [analysis]);
  const analysedInterval = analysis?.parameters.shot_interval_m;
  const recordNote = (record: EngineRecord) => describeRecord(record, findingsByRow.get(record.id) || [], analysedInterval);
  const shotInterval = Number(shotIntervalText.trim().replace(",", "."));
  const validShotInterval = Number.isFinite(shotInterval) && shotInterval > 0;
  const analysisStale = Boolean(analysis && (!validShotInterval || analysis.parameters.shot_interval_m !== shotInterval));
  const profileStale = Boolean(analysis && ((formatStates.reference?.profile?.profile_hash && analysis.input_formats?.reference?.profile_hash !== formatStates.reference.profile.profile_hash) || (formatStates.target?.profile?.profile_hash && analysis.input_formats?.target?.profile_hash !== formatStates.target.profile.profile_hash)));
  const formatBlocked = Boolean(formatStates.reference?.profile?.confidence === "Unresolved" || formatStates.target?.profile?.confidence === "Unresolved" || formatStates.reference?.validation?.valid === false || formatStates.target?.validation?.valid === false);
  const formatNeedsReview = Boolean(!formatOverrides.reference && formatStates.reference?.profile?.confidence === "Review recommended" || !formatOverrides.target && formatStates.target?.profile?.confidence === "Review recommended");
  useEffect(() => {
    let cancelled = false;
    const inspect = async (path: string, inputType: "EIVA" | "RECORDER", key: Role) => {
      if (!path) { setFormatStates((current) => ({ ...current, [key]: null })); return; }
      try {
        const response = await window.shotlogfixer.inspectFormat(path, inputType);
        if (!cancelled) setFormatStates((current) => ({ ...current, [key]: response.ok ? response : { error: response.error?.detail || response.error?.message || "Format detection failed" } }));
      } catch { if (!cancelled) setFormatStates((current) => ({ ...current, [key]: { error: "Format detection failed" } })); }
    };
    void inspect(referencePath, "RECORDER", "reference"); void inspect(targetPath, "EIVA", "target");
    return () => { cancelled = true; };
  }, [referencePath, targetPath]);

  const focusRecord = (index: number) => {
    if (!records[index]) return;
    setSelectedIndex(index);
    setNavCurrent((current) => {
      const next = { ...current };
      for (const key of GROUP_KEYS) if (problemGroups[key].includes(index)) next[key] = index;
      return next;
    });
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
      const x = timelineMarkerX(records[index], trackWidth, analysis?.summary.target_rows || records.length);
      timeline.scrollTo({ left: Math.max(0, x - timeline.clientWidth / 2), behavior: "auto" });
    }
  };

  const navigate = (group: GroupKey, step: 1 | -1) => {
    const next = nextCycle(problemGroups[group], navCurrent[group], step);
    if (next === null) return;
    setNavCurrent((current) => ({ ...current, [group]: next }));
    focusRecord(next);
  };

  const focusIssue = (group: GroupKey) => {
    const current = navCurrent[group];
    const target = current !== null && problemGroups[group].includes(current) ? current : nextCycle(problemGroups[group], null, 1);
    if (target === null) return;
    setNavCurrent((state) => ({ ...state, [group]: target }));
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

  const chooseFile = async (role: Role) => {
    try {
      const selected = role === "reference" ? await window.shotlogfixer.selectReferenceFile() : await window.shotlogfixer.selectTargetFile();
      if (selected) { if (role === "reference") { setReferencePath(selected); setFormatOverrides((current) => ({ ...current, reference: null })); } else { setTargetPath(selected); setFormatOverrides((current) => ({ ...current, target: null })); } }
    } catch { setError("The file picker could not be opened."); setLifecycle("failed"); }
  };

  const analyse = async () => {
    diagnosticPhase("analyse-entered");
    markTiming("analyse-request-start");
    setError("");
    if (!validShotInterval) { setError("Enter a finite positive Shot Interval in Settings before analysing."); setLifecycle("failed"); return; }
    if (formatBlocked || formatNeedsReview) { setError(formatBlocked ? "Format not ready — configure the input mapping before analysing." : "Format needs review — open Configure and confirm the interpretation before analysing."); setLifecycle("failed"); return; }
    if (!referencePath && !targetPath) { setError("Select both a reference (recorder) log and a target (EIVA) log before analysing."); setLifecycle("failed"); return; }
    if (!referencePath) { setError("Select a reference (recorder) log before analysing."); setLifecycle("failed"); return; }
    if (!targetPath) { setError("Select a target (EIVA) log before analysing."); setLifecycle("failed"); return; }
    setAnalysis(null); setSelectedIndex(null); setLifecycle("running");
    try {
      diagnosticPhase("analyse-ipc-invoke-start");
      const response = await window.shotlogfixer.analyseFiles(referencePath, targetPath, shotInterval, formatOverrides.reference, formatOverrides.target);
      diagnosticPhase("analyse-ipc-promise-resolved");
      markTiming("python-response-received", "analyse-request-start");
      if (diagnosticsEnabled) diagnosticPhase(`analyse-response-known:${JSON.stringify(response).length}-bytes`);
      if (!response.ok) { setError(errorMessage(response)); setLifecycle("failed"); return; }
      setAnalysis(response); if (response.input_formats) setFormatStates({ reference: { ok: true, profile: response.input_formats.reference, validation: { valid: true, usable_rows: response.summary.reference_rows, data_rows: response.summary.reference_rows } }, target: { ok: true, profile: response.input_formats.target, validation: { valid: true, usable_rows: response.summary.target_rows, data_rows: response.summary.target_rows } } }); diagnosticPhase("analyse-setAnalysis-called"); setVisibleColumns(DEFAULT_COLUMNS); setNavCurrent(EMPTY_NAV); setJumpCurrent(null); setLifecycle("done");
    } catch { setError("The Python engine could not be reached."); setLifecycle("failed"); }
  };

  const exportQc = async () => {
    if (!analysis || analysisStale || profileStale) { setError("Analysis settings changed — re-analyse before exporting QC."); return; }
    try {
      const outputPath = await window.shotlogfixer.selectQcExportPath(targetPath);
      if (!outputPath) return;
      const response = await window.shotlogfixer.exportQc(referencePath, targetPath, outputPath, shotInterval, analysis.input_hashes, analysis.input_formats?.reference, analysis.input_formats?.target);
      if (!response.ok) { setError(errorMessage(response)); return; }
      setToast("QC TXT exported successfully");
    } catch { setError("The QC TXT could not be exported."); }
  };

  // Correction and QC are separate: only structural blockers (correction.safe) gate the corrected copy.
  const correctionReady = Boolean(analysis && !analysisStale && !profileStale && analysis.correction.safe);
  const correctionBlockers = analysis?.correction.blockers.length ? analysis.correction.blockers : analysis ? analysis.validation.errors.map((message) => ({ code: "VALIDATION", message })) : [];
  const saveCorrected = async () => {
    if (!analysis || !correctionReady) return;
    try {
      const outputPath = await window.shotlogfixer.selectCorrectedTargetPath(targetPath);
      if (!outputPath) return;
      const response = await window.shotlogfixer.saveCorrectedTarget(referencePath, targetPath, outputPath, shotInterval, analysis.input_hashes, analysis.input_formats?.reference, analysis.input_formats?.target);
      if (!response.ok) { setError(errorMessage(response)); return; }
      setToast("Corrected copy saved; source files unchanged");
    } catch { setError("The corrected copy could not be saved."); }
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
    if (markerIndex !== null) focusRecord(markerIndex);
  };
  const handleTimelineMove = (event: MouseEvent<HTMLCanvasElement>) => {
    if (!timelineRef.current || !records.length) return;
    if (dragRef.current.active && dragRef.current.moved) return;
    const x = timelineLogicalX(event.clientX, timelineRef.current.getBoundingClientRect().left + timelineRef.current.clientLeft, timelineRef.current.scrollLeft);
    const index = timelineRecordIndexAtX(records, x, timelineTrackWidth, timelineTotal);
    if (index === null) { setTimelineTooltip(null); return; }
    const record = records[index];
    const jump = analysis?.qc.ffid_jumps.find((candidate) => candidate.row_id === record.id);
    const jumpDetail = jump ? `\nRecorder FFID sequence ${jump.kind === "REVERSAL" ? "goes back" : "jumps"} from ${jump.from} to ${jump.to}` : "";
    const text = record.association === "ASSIGNED"
      ? `Recorder ${record.reference_ffid} → EIVA ${record.target_ffid}\nCorrected FFID ${record.corrected_ffid}\n${getCellValue(record, "distance")} m · ${getCellValue(record, "qc")}`
      : `${formatAssociation(record.association)}\n${record.target_ffid ? `EIVA ${record.target_ffid}` : `Recorder ${record.reference_ffid}`}`;
    setTimelineTooltip({ x: event.clientX, y: event.clientY, text: text + jumpDetail });
  };
  const handleTimelineLeave = () => setTimelineTooltip(null);

  const timelineTrackWidth = Math.max(1400, records.length * 5);
  const timelineTotal = analysis?.summary.target_rows || records.length;
  useEffect(() => {
    const canvas = timelineCanvasRef.current;
    if (!canvas || ["no-timeline", "no-visualizations", "header-only"].includes(isolation)) return;
    diagnosticPhase("timeline-effect-start");
    const context = canvas.getContext("2d");
    if (!context) return;
    const styles = getComputedStyle(document.documentElement);
    diagnosticPhase("timeline-style-read");
    const colors: Record<string, string> = { ok: styles.getPropertyValue("--matched"), warning: styles.getPropertyValue("--review"), severe: styles.getPropertyValue("--invalid"), "target-only": styles.getPropertyValue("--target-only"), invalid: styles.getPropertyValue("--invalid") };
    context.clearRect(0, 0, timelineTrackWidth, 60);
    context.strokeStyle = styles.getPropertyValue("--border"); context.globalAlpha = 1; context.lineWidth = 1; context.beginPath(); context.moveTo(0, 30.5); context.lineTo(timelineTrackWidth, 30.5); context.stroke();
    records.forEach((record, index) => {
      const x = timelineMarkerX(record, timelineTrackWidth, timelineTotal);
      const selected = selectedIndex === index;
      const tone = recordTone(record);
      context.globalAlpha = tone === "ok" ? .55 : 1;
      context.fillStyle = colors[tone] || colors.ok;
      context.fillRect(x - (selected ? 3 : 1.5), selected ? 8 : (tone === "ok" ? 18 : 14), selected ? 6 : (tone === "ok" ? 2 : 5), selected ? 44 : (tone === "ok" ? 25 : 31));
      if (selected) { context.strokeStyle = styles.getPropertyValue("--text"); context.lineWidth = 1; context.strokeRect(x - 4, 7, 8, 46); }
    });
    context.globalAlpha = 1;
    markTiming("timeline-render-complete");
    diagnosticPhase("timeline-effect-complete");
  }, [analysis, records, selectedIndex, timelineTotal, timelineTrackWidth, theme, isolation]);

  const columns = useMemo(() => orderedVisibleColumns(columnOrder, visibleColumns).map((key) => {
    const spec = allColumns.find((column) => column.key === key) || { key, label: key };
    // The eight default columns total ~1135 px so the QC column is visible in the default window without horizontal scrolling.
    const fixedWidths: Record<string, number> = { reference_ffid: 105, target_ffid: 150, corrected_ffid: 115, reference_coord: 170, target_coord: 170, distance: 100, association: 110, qc: 215 };
    const width = fixedWidths[key] ?? (key === "diagnostic" || key.startsWith("target_raw:") ? 220 : 130);
    return { id: key, header: spec.label, alignment: columnAlignment(key), width };
  }), [allColumns, columnOrder, visibleColumns]);
  const visibleKeys = columns.map((column) => column.id);
  const applyColumnOrder = (next: string[]) => {
    // Keep saved positions of columns this file does not have (e.g. another EIVA file's raw fields).
    const kept = [...next, ...(columnOrderPreference || []).filter((key) => !next.includes(key))];
    setColumnOrderPreference(kept);
    saveColumnOrder(window.localStorage, kept);
  };
  const resetColumns = () => {
    setColumnOrderPreference(null);
    saveColumnOrder(window.localStorage, null);
    setVisibleColumns(DEFAULT_COLUMNS);
  };
  /** Drop position among the visible headers for a pointer x, and where to draw the insertion line. */
  const columnDropAt = (clientX: number) => {
    const viewport = tableViewportRef.current;
    const headers = viewport ? Array.from(viewport.querySelectorAll<HTMLTableCellElement>("thead th")) : [];
    if (!viewport || !headers.length) return null;
    let dropIndex = headers.findIndex((header) => { const rect = header.getBoundingClientRect(); return clientX < rect.left + rect.width / 2; });
    if (dropIndex < 0) dropIndex = headers.length;
    const edge = dropIndex < headers.length ? headers[dropIndex].getBoundingClientRect().left : headers[headers.length - 1].getBoundingClientRect().right;
    const box = viewport.getBoundingClientRect();
    return { dropIndex, left: edge - box.left - viewport.clientLeft + viewport.scrollLeft };
  };
  const handleHeaderPointerDown = (event: PointerEvent<HTMLTableCellElement>, key: string) => {
    if (event.button !== 0) return;
    columnDragRef.current = { key, x: event.clientX, started: false };
  };
  const handleHeaderPointerMove = (event: PointerEvent<HTMLTableCellElement>) => {
    const drag = columnDragRef.current;
    if (!drag) return;
    if (!drag.started) {
      if (Math.abs(event.clientX - drag.x) < 5) return;
      drag.started = true;
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    const viewport = tableViewportRef.current;
    if (viewport) {
      // Near either edge the table scrolls so a column can be carried to any position.
      const box = viewport.getBoundingClientRect();
      if (event.clientX > box.right - 36) viewport.scrollLeft += 18;
      else if (event.clientX < box.left + 36) viewport.scrollLeft -= 18;
    }
    const drop = columnDropAt(event.clientX);
    if (drop) setColumnDrag({ key: drag.key, ...drop });
  };
  const finishColumnDrag = (event: PointerEvent<HTMLTableCellElement>, commit: boolean) => {
    const drag = columnDragRef.current;
    columnDragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (drag?.started && commit) {
      const drop = columnDropAt(event.clientX);
      if (drop) applyColumnOrder(moveColumn(columnOrder, visibleKeys, drag.key, drop.dropIndex));
    }
    setColumnDrag(null);
  };
  const handleHeaderKeyDown = (event: ReactKeyboardEvent<HTMLTableCellElement>, key: string) => {
    if (!event.altKey || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
    event.preventDefault();
    const index = visibleKeys.indexOf(key);
    const target = event.key === "ArrowLeft" ? index - 1 : index + 2;
    if (target < 0 || target > visibleKeys.length) return;
    applyColumnOrder(moveColumn(columnOrder, visibleKeys, key, target));
    requestAnimationFrame(() => tableViewportRef.current?.querySelector<HTMLTableCellElement>(`thead th[data-column="${CSS.escape(key)}"]`)?.focus());
  };
  const tableRecords = ["no-table", "no-visualizations", "header-only"].includes(isolation) ? [] : records;
  useLayoutEffect(() => { if (analysis) markTiming("table-render-complete"); }, [analysis, visibleColumns]);
  const visibleStart = timelineTotal ? Math.min(timelineTotal, Math.floor((timelineLeft / timelineTrackWidth) * timelineTotal) + 1) : 0;
  const visibleCount = timelineRef.current ? Math.ceil((timelineRef.current.clientWidth / timelineTrackWidth) * timelineTotal) : 0;
  const visibleEnd = timelineTotal ? Math.min(timelineTotal, visibleStart + Math.max(1, visibleCount) - 1) : 0;
  const distances = useMemo(() => records.flatMap((record) => record.association === "ASSIGNED" && record.distance_m !== null ? [record.distance_m] : []).sort((a, b) => a - b), [records]);
  const medianDistance = distances.length ? distances[Math.floor(distances.length / 2)] : null;
  const maxDistance = distances.length ? distances[distances.length - 1] : null;
  const summary = analysis?.summary;
  const displacedRuns = analysis?.qc.summary.by_code.ASSOCIATION_RUN_DISPLACED ?? 0;
  const withoutRow = analysis?.correction.reference_without_target ?? 0;
  const counterTotal = (group: GroupKey) => problemGroups[group].length;
  const counter = (label: string, group: GroupKey, title?: string) => <Counter label={label} group={group} title={title} count={summary ? counterTotal(group) : undefined} current={navCurrent[group]} ordinal={problemGroups[group].indexOf(navCurrent[group] ?? -1) + 1} total={counterTotal(group)} onNavigate={navigate} onFocus={focusIssue} />;
  const selectedRecord = selectedIndex === null ? undefined : records[selectedIndex];
  const selectedFindings = selectedRecord ? findingsByRow.get(selectedRecord.id) || [] : [];
  const selectedNote = selectedRecord ? recordNote(selectedRecord) : null;
  /** Hover text: every finding of the row in plain words, then the canonical codes for technical follow-up. */
  const rowTitle = (record: EngineRecord) => {
    const findings = findingsByRow.get(record.id) || [];
    const note = recordNote(record);
    return note ? noteTitle(note, findings, record, analysedInterval) : undefined;
  };

  return <div className="app-shell" data-diagnostics-isolation={isolation}>
    <header className="app-header">
      <div><h1>ShotLogFixer</h1><p>Seismic acquisition QC</p></div>
      <div className="header-actions"><StatusMark lifecycle={lifecycle} /><AnalysisSettings value={shotIntervalText} onChange={setShotIntervalText} valid={validShotInterval} interval={shotInterval} /><ThemePicker value={themePreference} onChange={setThemePreference} /></div>
    </header>

    <main>
      <section className="input-section" aria-label="Input files">
        <div className="file-row"><label htmlFor="reference-path" title="Authoritative: every valid record is a real shot and its FFID is the reference FFID">Reference (Recorder)</label><div className="file-field"><input id="reference-path" value={referencePath ? basename(referencePath) : "No file selected"} readOnly title={referencePath} className={!referencePath ? "placeholder" : ""} />{referencePath && <FormatBadge kind="RECORDER" state={formatStates.reference} />}</div><button className="button secondary" onClick={() => chooseFile("reference")}>Browse</button><ConfigureFormatButton kind="RECORDER" state={formatStates.reference} onConfigure={() => setFormatDetails("reference")} /></div>
        <div className="file-row"><label htmlFor="target-path" title="Corrected: a copy of this file receives the recorder FFIDs; unassigned rows are removed">Target (EIVA)</label><div className="file-field"><input id="target-path" value={targetPath ? basename(targetPath) : "No file selected"} readOnly title={targetPath} className={!targetPath ? "placeholder" : ""} />{targetPath && <FormatBadge kind="EIVA" state={formatStates.target} />}</div><button className="button secondary" onClick={() => chooseFile("target")}>Browse</button><ConfigureFormatButton kind="EIVA" state={formatStates.target} onConfigure={() => setFormatDetails("target")} /></div>
        <div className="input-actions">
          <button className="button primary analyse-button" onClick={analyse} disabled={lifecycle === "running" || formatBlocked || formatNeedsReview}>{lifecycle === "running" ? "ANALYSING" : "ANALYSE"}</button>
          <div className="output-actions" aria-label="Output actions">
            <button className="button secondary compact-button" onClick={exportQc} disabled={!analysis || analysisStale || profileStale}><Icon name="download" />Export QC</button>
            <button className="button primary compact-button" onClick={saveCorrected} disabled={!correctionReady} title="Writes a corrected copy of the target file; the recorder file is never modified">Save Corrected EIVA</button>
          </div>
        </div>
      </section>

      {error && <div className="error-line" role="alert"><strong>{lifecycle === "failed" ? "Analysis issue" : "Export issue"}</strong><span>{error}</span></div>}
      {(analysisStale || profileStale) && <div className="stale-line" role="status"><strong>Analysis settings changed — re-analyse</strong><span>Output actions are disabled until the Shot Interval (Settings) and input format profiles match the analysed values.</span></div>}
      {formatDetails && <FormatDialog kind={formatDetails === "target" ? "EIVA" : "RECORDER"} filePath={formatDetails === "target" ? targetPath : referencePath} state={formatStates[formatDetails]} onCancel={() => setFormatDetails(null)} onUse={(profile) => { const active = { ...profile, profile_hash: "" }; setFormatOverrides((current) => ({ ...current, [formatDetails]: active })); setFormatStates((current) => ({ ...current, [formatDetails]: { ...current[formatDetails], profile: active } })); setFormatDetails(null); }} onSave={(profile) => { const name = window.prompt("Save format profile as", profile?.name || "My format"); if (name) void window.shotlogfixer.saveFormatProfile(profile, name); }} />}

      <section className="summary-section" aria-label="Analysis summary">
        <div className="summary-line">
          <span className="summary-item summary-matched" title="Recorder shots matched to an EIVA position">Matched <b>{summary ? summary.assigned.toLocaleString() : "—"}</b></span>
          {counter("EIVA-only", "TARGET_ONLY", "EIVA positions with no recorder shot; they are not in the corrected EIVA file")}
          {counter("Needs review", "NEEDS_REVIEW", "Unmatched recorder shots and rows with a warning or severe QC finding")}
          <button ref={detailsButtonRef} className={`button secondary compact-button qc-details-button${detailsOpen ? " is-open" : ""}`} onClick={() => setDetailsOpen((open) => !open)} aria-haspopup="dialog" aria-expanded={detailsOpen} disabled={!analysis}>QC details<Icon name="chevron" /></button>
          {analysis && detailsOpen && <Popover anchorRef={detailsButtonRef} onClose={() => setDetailsOpen(false)} className="qc-details-panel" role="dialog" aria-label="QC details">
            <div className="qc-details-group">
              <strong>Needs review</strong>
              {counter("Unmatched recorder shots", "BLOCKED", "Recorder records with no EIVA position; they are not in the corrected EIVA file")}
              {counter("Severe findings", "QC_SEVERE")}
              {counter("Warnings", "QC_WARNING")}
              {counter("Invalid or no-shot rows", "INVALID")}
            </div>
            <div className="qc-details-group">
              <strong>Recorder log</strong>
              {counter("Position jumps", "POSITION_JUMP")}
              <JumpNavigation jumps={analysis.qc.ffid_jumps} current={jumpCurrent} targets={jumpTargets} onFocus={focusJump} onNavigate={navigateJump} />
              <span className="summary-item">No-shot rows <b>{summary ? summary.reference_no_shot.toLocaleString() : "—"}</b></span>
              <span className="summary-item" title="Observations for a human to inspect. They never change a match and never block the corrected copy.">QC notes <b>{summary ? summary.qc_info.toLocaleString() : "—"}</b></span>
            </div>
            <div className="qc-details-group">
              <strong>Corrected EIVA file</strong>
              <span className="summary-item" title="One corrected row for each recorder record that received an EIVA row">Rows <b>{analysis.validation.corrected_rows.toLocaleString()}</b> of <b>{analysis.validation.expected_rows.toLocaleString()}</b> recorder shots</span>
              <span className="summary-item">EIVA-only rows removed <b>{analysis.correction.target_only_removed.toLocaleString()}</b></span>
              {analysis.correction.invalid_target_removed > 0 && <span className="summary-item">Invalid EIVA rows removed <b>{analysis.correction.invalid_target_removed.toLocaleString()}</b></span>}
              <span className="summary-item">FFIDs changed <b>{analysis.validation.ffid_changed.toLocaleString()}</b> · unchanged <b>{analysis.validation.ffid_unchanged.toLocaleString()}</b></span>
              <span className="summary-item">Match distance median <b>{medianDistance === null ? "—" : `${medianDistance.toFixed(3)} m`}</b> · max <b>{maxDistance === null ? "—" : `${maxDistance.toFixed(3)} m`}</b></span>
            </div>
            {generalFindings.length > 0 && <div className="qc-details-group qc-details-notes">
              <strong>General notes</strong>
              {generalFindings.map((finding, index) => <QcNote key={`${finding.code}-${index}`} note={describeFinding(finding, null, analysedInterval)} code={finding.code} severity={finding.severity} />)}
            </div>}
          </Popover>}
        </div>
        {analysis && <div className={`correction-line ${correctionReady ? "correction-ready" : "correction-blocked"}`}>
          <strong>{correctionReady ? "Correction ready" : "Correction blocked"}</strong>
          <span>{correctionReady
            ? <span title="QC warnings never block the corrected copy.">{`Corrected EIVA file ${analysis.correction.corrected_rows.toLocaleString()} rows · ${(analysis.correction.target_only_removed + analysis.correction.invalid_target_removed).toLocaleString()} EIVA rows left out`}{withoutRow ? ` · ${withoutRow.toLocaleString()} recorder shot${withoutRow === 1 ? " has" : "s have"} no EIVA match and ${withoutRow === 1 ? "is" : "are"} not in the file` : ""}{displacedRuns ? ` · possible one-shot offset in ${displacedRuns} place${displacedRuns === 1 ? "" : "s"}: review before saving` : ""}</span>
            : `${correctionBlockers.length.toLocaleString()} structural blocker${correctionBlockers.length === 1 ? "" : "s"}. `}<button className="inline-details" onClick={() => setCorrectionDetailsOpen(true)} disabled={correctionReady}>View details</button></span>
        </div>}
        {analysis && correctionDetailsOpen && <CorrectionDetails blockers={correctionBlockers} onClose={() => setCorrectionDetailsOpen(false)} />}
      </section>

      <section className="timeline-section" aria-label="Acquisition timeline">
        <div className="section-heading"><h2>Acquisition timeline</h2><span>Positions {analysis ? `${visibleStart}–${visibleEnd} of ${timelineTotal}` : "—"}</span></div>
        <div className="timeline-viewport" ref={timelineRef} onClick={handleTimelineClick} onScroll={handleTimelineScroll} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp}>
          <canvas ref={timelineCanvasRef} className="timeline-canvas" width={timelineTrackWidth} height={60} style={{ width: timelineTrackWidth, height: 60 }} onMouseMove={handleTimelineMove} onMouseLeave={handleTimelineLeave} aria-label="Acquisition timeline" />
          {timelineTooltip && <FloatingTooltip x={timelineTooltip.x} y={timelineTooltip.y} className="timeline-tooltip">{timelineTooltip.text}</FloatingTooltip>}
        </div>
      </section>

      <section className="table-section" aria-label="QC table">
        <div className="section-heading table-heading">
          <h2>QC table</h2>
          <p className="row-note" aria-live="polite" title={selectedNote ? noteTitle(selectedNote, selectedFindings) : undefined}>{selectedRecord && selectedNote
            ? <><span className={`row-note-mark qc-${selectedRecord.qc_severity.toLowerCase()}`} aria-hidden="true" />{selectedNote.text}{selectedNote.detail ? ` ${selectedNote.detail}` : ""}{selectedFindings.length > 1 ? <span className="row-note-more"> +{selectedFindings.length - 1} more</span> : null}</>
            : selectedRecord ? "No QC findings for the selected row." : analysis ? "Select a row to read its QC note." : null}</p>
          <div className="columns-wrap"><button ref={columnsButtonRef} className="button secondary compact-button" onClick={() => setColumnsOpen((open) => !open)} aria-expanded={columnsOpen}><Icon name="columns" />Columns</button>{columnsOpen && <Popover anchorRef={columnsButtonRef} onClose={() => setColumnsOpen(false)} className="columns-popover" role="dialog" aria-label="Visible columns"><strong>Visible columns</strong><p className="columns-hint">Drag table headers to reorder columns.</p><div className="column-list">{columnOrder.map((key) => allColumns.find((column) => column.key === key)).filter((column) => column !== undefined).map((column) => <label key={column.key}><input type="checkbox" checked={visibleColumns.includes(column.key)} onChange={() => setVisibleColumns((current) => current.includes(column.key) ? current.filter((key) => key !== column.key) : [...current, column.key])} />{column.label}</label>)}</div><div className="columns-popover-footer"><button className="button secondary compact-button" onClick={resetColumns}>Reset columns</button></div></Popover>}</div>
        </div>
        <div className={`table-viewport${columnDrag ? " is-dragging-column" : ""}`} ref={tableViewportRef}>
          <table style={{ minWidth: columns.reduce((sum, column) => sum + column.width, 0) }}>
            <colgroup>{columns.map((column) => <col key={column.id} style={{ width: column.width }} />)}</colgroup>
            <thead><tr>{columns.map((column) => <th key={column.id} data-column={column.id} className={columnDrag?.key === column.id ? "is-dragged" : undefined} style={{ textAlign: column.alignment }} tabIndex={0} title="Drag to reorder (Alt+← / Alt+→)" onPointerDown={(event) => handleHeaderPointerDown(event, column.id)} onPointerMove={handleHeaderPointerMove} onPointerUp={(event) => finishColumnDrag(event, true)} onPointerCancel={(event) => finishColumnDrag(event, false)} onKeyDown={(event) => handleHeaderKeyDown(event, column.id)}>{column.header}</th>)}</tr></thead>
            <tbody>{tableRecords.map((record, index) => <tr key={record.id} data-index={index} data-selected={selectedIndex === index} data-status={record.association} onClick={() => focusRecord(index)}>
              {columns.map((column) => <td key={column.id} data-column={column.id} style={{ textAlign: column.alignment }} className={column.id === "association" ? `status-cell status-${record.association.toLowerCase()}` : column.id === "qc" ? `qc-cell qc-${record.qc_severity.toLowerCase()}` : undefined} title={column.id === "qc" || column.id === "diagnostic" ? rowTitle(record) : undefined}>{column.id === "diagnostic" ? recordNote(record)?.text ?? "—" : getCellValue(record, column.id)}</td>)}
            </tr>)}</tbody>
          </table>
          {columnDrag && <div className="column-drop-indicator" style={{ left: columnDrag.left, top: tableViewportRef.current?.scrollTop ?? 0, height: tableViewportRef.current?.clientHeight ?? 0 }} aria-hidden="true" />}
          {!analysis && <div className="empty-table">Analyse a file pair to load the QC table.</div>}
        </div>
      </section>
    </main>
    <footer className="app-footer"><span>{analysis ? `${records.length.toLocaleString()} result rows` : "Ready for an offline analysis"}</span><span className="app-version">Version {__APP_VERSION__}</span></footer>
    {toast && <div className="toast" role="status">{toast}</div>}
  </div>;
}

function Counter({ label, group, title, count, current, ordinal, total, onNavigate, onFocus }: { label: string; group: GroupKey; title?: string; count?: number; current: number | null; ordinal: number; total: number; onNavigate: (group: GroupKey, step: 1 | -1) => void; onFocus: (group: GroupKey) => void }) {
  return <EventNavigation className={`summary-${group.toLowerCase()}${count === 0 ? " summary-zero" : ""}`} title={title} label={label} value={count === undefined ? "—" : count.toLocaleString()} total={total} ordinal={current === null ? 1 : ordinal} onFocus={() => onFocus(group)} onNavigate={(step) => onNavigate(group, step)} />;
}

function JumpNavigation({ jumps, current, targets, onFocus, onNavigate }: { jumps: Array<{ from: number | null; to: number | null }>; current: number | null; targets: Array<number | null>; onFocus: () => void; onNavigate: (step: 1 | -1) => void }) {
  return <span className="jump-navigation">
    <EventNavigation label="FFID jumps" value={jumps.length} total={targets.some((target) => target !== null) ? jumps.length : 0} ordinal={(current ?? 0) + 1} onFocus={onFocus} onNavigate={onNavigate} />
  </span>;
}

function EventNavigation({ className = "", title, label, value, total, ordinal, onFocus, onNavigate }: { className?: string; title?: string; label: string; value: string | number; total: number; ordinal: number; onFocus: () => void; onNavigate: (step: 1 | -1) => void }) {
  const content = <>{label} <b>{value}</b></>;
  return <span className={`summary-item ${className} ${total ? "" : "summary-inactive"}`} title={title}>
    {total ? <button className="summary-trigger" onClick={onFocus}>{content}</button> : content}
    {total > 1 && <span className="counter-nav">
      <button className="icon-button" onClick={() => onNavigate(-1)} title={`Previous ${label.toLowerCase().replace(/:$/, "")}`}><Icon name="left" /></button>
      <span>{ordinal} / {total}</span>
      <button className="icon-button" onClick={() => onNavigate(1)} title={`Next ${label.toLowerCase().replace(/:$/, "")}`}><Icon name="right" /></button>
    </span>}
  </span>;
}

function noteTitle(note: QcDescription, findings: QcFinding[], record?: EngineRecord, shotInterval?: number): string {
  const lines = [findings.length ? null : [note.text, note.detail].filter(Boolean).join(" ")];
  for (const finding of findings) { const described = describeFinding(finding, record, shotInterval); lines.push([described.text, described.detail].filter(Boolean).join(" ")); }
  if (findings.length) lines.push(`Codes: ${findings.map((finding) => finding.code).join(", ")}`);
  return lines.filter(Boolean).join("\n");
}

function QcNote({ note, code, severity }: { note: QcDescription; code: string; severity: string }) {
  return <p className="qc-note" title={code}><span className={`row-note-mark qc-${severity.toLowerCase()}`} aria-hidden="true" /><span><b>{formatQcCode(code)}.</b> {note.text}{note.detail ? ` ${note.detail}` : ""}</span></p>;
}

