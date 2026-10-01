import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent, type WheelEvent } from "react";
import { basename, formatCoordinate, nextCycle, resolveThemePreference, statusIndices, timelinePositionForRecord, timelineRecordIndexAtX } from "./lib/logic";
import type { AnalysisResponse, AnalysisSuccess, EngineRecord, ExportResponse, Status } from "./lib/types";
import "./styles.css";
import { diagnosticOptions, diagnosticPhase, diagnosticsEnabled, useRenderDiagnostics } from "./lib/diagnostics";

type Lifecycle = "idle" | "running" | "done" | "failed";
type ThemePreference = "system" | "light" | "dark";
const IS_DEV = import.meta.env.DEV;

function markTiming(name: string, start?: string) {
  if (!IS_DEV || typeof performance === "undefined") return;
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

function getCellValue(record: EngineRecord, key: string): string {
  switch (key) {
    case "eiva_ffid": return record.eiva_ffid || "";
    case "recorder_ffid": return record.recorder_ffid || "";
    case "eiva_coord": return formatCoordinate(record.eiva_easting, record.eiva_northing);
    case "recorder_coord": return record.status === "NO_SHOT" ? "No shot recorded" : formatCoordinate(record.recorder_x, record.recorder_y);
    case "distance": return record.distance_m === null ? "" : record.distance_m.toFixed(3);
    case "recorder_x": return record.recorder_x === null ? "" : record.recorder_x.toFixed(2);
    case "recorder_y": return record.recorder_y === null ? "" : record.recorder_y.toFixed(2);
    case "diagnostic": return record.diagnostic;
    default: return record.eiva_values[key.slice("eiva_raw:".length)] || "";
  }
}

function errorMessage(response: AnalysisResponse | ExportResponse): string {
  const error = "error" in response ? response.error : undefined;
  if (error?.message) return error.detail ? `${error.message} ${error.detail}` : error.message;
  return "The requested operation could not be completed.";
}

export default function App() {
  useRenderDiagnostics("App");
  const isolation = diagnosticOptions?.isolation || "full";
  const [eivaPath, setEivaPath] = useState("");
  const [recorderPath, setRecorderPath] = useState("");
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
  const dragRef = useRef({ active: false, moved: false, x: 0, scrollLeft: 0 });

  const theme = resolveThemePreference(themePreference, systemDark);
  useEffect(() => {
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
    if (!analysis) return;
    diagnosticPhase(`analysis-react-commit:${analysis.records.length}-rows`);
    requestAnimationFrame(() => requestAnimationFrame(() => diagnosticPhase("analysis-two-frames")));
  }, [analysis]);
  useEffect(() => {
    if (!diagnosticsEnabled) return;
    window.shotlogfixerTest = { setFiles: (eivaPath, recorderPath) => { setEivaPath(eivaPath); setRecorderPath(recorderPath); } };
    return () => { delete window.shotlogfixerTest; };
  }, []);

  const records = analysis?.records || [];
  const problemGroups = useMemo(() => ({
    EIVA_ONLY: statusIndices(records, "EIVA_ONLY"),
    RECORDER_INVALID: statusIndices(records, "RECORDER_INVALID"),
    REVIEW: statusIndices(records, "REVIEW"),
  }), [records]);
  const [navCurrent, setNavCurrent] = useState<Record<string, number | null>>({ EIVA_ONLY: null, RECORDER_INVALID: null, REVIEW: null });
  const allColumns = useMemo(() => [...BASE_COLUMNS, ...(analysis?.eiva_headers || []).map((header) => ({ key: `eiva_raw:${header}`, label: `EIVA ${header}` }))], [analysis]);

  const selectRecord = (index: number) => {
    if (!records[index]) return;
    setSelectedIndex(index);
    rowVirtualizer.scrollToIndex(index, { align: "center", behavior: "smooth" });
    const timeline = timelineRef.current;
    if (timeline) {
      const trackWidth = Math.max(1400, records.length * 5);
      const x = ((timelinePositionForRecord(records[index]) - 1) / Math.max(1, (analysis?.summary.eiva_rows || records.length) - 1)) * trackWidth;
      timeline.scrollTo({ left: Math.max(0, x - timeline.clientWidth / 2), behavior: "smooth" });
    }
  };

  const navigate = (status: "EIVA_ONLY" | "RECORDER_INVALID" | "REVIEW", step: 1 | -1) => {
    const next = nextCycle(problemGroups[status], navCurrent[status], step);
    if (next === null) return;
    setNavCurrent((current) => ({ ...current, [status]: next }));
    selectRecord(next);
  };

  const chooseFile = async (kind: "eiva" | "recorder") => {
    try {
      const selected = kind === "eiva" ? await window.shotlogfixer.selectEivaFile() : await window.shotlogfixer.selectRecorderFile();
      if (selected) kind === "eiva" ? setEivaPath(selected) : setRecorderPath(selected);
    } catch { setError("The file picker could not be opened."); setLifecycle("failed"); }
  };

  const analyse = async () => {
    diagnosticPhase("analyse-entered");
    markTiming("analyse-request-start");
    setError("");
    if (!eivaPath && !recorderPath) { setError("Select both an EIVA log and a recorder log before analysing."); setLifecycle("failed"); return; }
    if (!eivaPath) { setError("Select an EIVA log before analysing."); setLifecycle("failed"); return; }
    if (!recorderPath) { setError("Select a recorder log before analysing."); setLifecycle("failed"); return; }
    setAnalysis(null); setSelectedIndex(null); setLifecycle("running");
    try {
      diagnosticPhase("analyse-ipc-invoke-start");
      const response = await window.shotlogfixer.analyseFiles(eivaPath, recorderPath);
      diagnosticPhase("analyse-ipc-promise-resolved");
      markTiming("python-response-received", "analyse-request-start");
      diagnosticPhase(`analyse-response-known:${JSON.stringify(response).length}-bytes`);
      if (!response.ok) { setError(errorMessage(response)); setLifecycle("failed"); return; }
      setAnalysis(response); diagnosticPhase("analyse-setAnalysis-called"); setVisibleColumns(DEFAULT_COLUMNS); setNavCurrent({ EIVA_ONLY: null, RECORDER_INVALID: null, REVIEW: null }); setLifecycle("done");
    } catch { setError("The Python engine could not be reached."); setLifecycle("failed"); }
  };

  const exportQc = async () => {
    if (!analysis) { setError("Analyse a valid file pair before exporting QC CSV."); return; }
    try {
      const outputPath = await window.shotlogfixer.selectQcExportPath();
      if (!outputPath) return;
      const response = await window.shotlogfixer.exportQc(eivaPath, recorderPath, outputPath);
      if (!response.ok) { setError(errorMessage(response)); return; }
      setToast("QC CSV exported successfully");
    } catch { setError("The QC CSV could not be exported."); }
  };

  const correctionReady = Boolean(analysis?.correction.safe && analysis.validation.passed);
  const saveFixedEiva = async () => {
    if (!analysis || !correctionReady) return;
    try {
      const outputPath = await window.shotlogfixer.selectFixedEivaPath(eivaPath);
      if (!outputPath) return;
      const response = await window.shotlogfixer.saveFixedEiva(eivaPath, recorderPath, outputPath);
      if (!response.ok) { setError(errorMessage(response)); return; }
      setToast("Fixed EIVA saved successfully");
    } catch { setError("The fixed EIVA file could not be saved."); }
  };

  const saveFixedPair = async () => {
    if (!analysis || !correctionReady) return;
    try {
      const outputs = await window.shotlogfixer.selectFixedPairPath(eivaPath, recorderPath);
      if (!outputs) return;
      const response = await window.shotlogfixer.saveFixedPair(eivaPath, recorderPath, outputs.eivaPath, outputs.recorderPath);
      if (!response.ok) { setError(errorMessage(response)); return; }
      setToast("Fixed pair created; original files unchanged");
    } catch { setError("The fixed pair could not be saved."); }
  };

  const handleTimelineScroll = () => setTimelineLeft(timelineRef.current?.scrollLeft || 0);
  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    const timeline = timelineRef.current;
    if (!timeline) return;
    event.preventDefault();
    const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    timeline.scrollLeft += delta;
  };
  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    const timeline = timelineRef.current;
    if (!timeline) return;
    dragRef.current = { active: true, moved: false, x: event.clientX, scrollLeft: timeline.scrollLeft };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.active || !timelineRef.current) return;
    const delta = event.clientX - dragRef.current.x;
    if (Math.abs(delta) > 3) dragRef.current.moved = true;
    timelineRef.current.scrollLeft = dragRef.current.scrollLeft - delta;
  };
  const handlePointerUp = () => { dragRef.current.active = false; };
  const handleTimelineClick = (event: MouseEvent<HTMLCanvasElement>) => {
    if (dragRef.current.moved || !timelineRef.current) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left + timelineRef.current.scrollLeft;
    const index = timelineRecordIndexAtX(records, x, timelineTrackWidth, timelineTotal);
    if (index !== null) selectRecord(index);
  };
  const handleTimelineMove = (event: MouseEvent<HTMLCanvasElement>) => {
    if (!timelineRef.current || !records.length) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left + timelineRef.current.scrollLeft;
    const index = timelineRecordIndexAtX(records, x, timelineTrackWidth, timelineTotal);
    if (index === null) return;
    const record = records[index];
    const markerX = ((timelinePositionForRecord(record) - 1) / Math.max(1, timelineTotal - 1)) * (timelineTrackWidth - 8);
    if (Math.abs(markerX - x) > 9) { setTimelineTooltip(null); return; }
    setTimelineTooltip({ x: event.clientX - (timelineRef.current.getBoundingClientRect().left), y: event.clientY - timelineRef.current.getBoundingClientRect().top - 7, text: record.status === "MATCHED" ? `EIVA ${record.eiva_ffid || "—"} → Recorder ${record.recorder_ffid || "—"}\n${record.distance_m?.toFixed(3) || "—"} m` : `EIVA ${record.eiva_ffid || "—"}\n${record.status}` });
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
    records.forEach((record, index) => {
      const x = ((timelinePositionForRecord(record) - 1) / Math.max(1, timelineTotal - 1)) * (timelineTrackWidth - 8);
      const selected = selectedIndex === index;
      context.globalAlpha = record.status === "MATCHED" ? .55 : 1;
      context.fillStyle = colors[record.status] || colors.MATCHED;
      context.fillRect(x - (selected ? 3 : 1.5), selected ? 8 : (record.status === "MATCHED" ? 18 : 14), selected ? 6 : (record.status === "MATCHED" ? 2 : 5), selected ? 44 : (record.status === "MATCHED" ? 25 : 31));
      if (selected) { context.strokeStyle = styles.getPropertyValue("--text"); context.lineWidth = 1; context.strokeRect(x - 4, 7, 8, 46); }
    });
    context.globalAlpha = 1;
    markTiming("timeline-render-complete");
    diagnosticPhase("timeline-effect-complete");
  }, [records, selectedIndex, timelineTotal, timelineTrackWidth, theme, isolation]);

  const columns = useMemo(() => visibleColumns.map((key) => {
    const spec = allColumns.find((column) => column.key === key) || { key, label: key };
    return { id: key, header: spec.label };
  }), [allColumns, visibleColumns]);
  const tableRecords = ["no-table", "no-visualizations", "header-only"].includes(isolation) ? [] : records;
  const tableRows = tableRecords.map((original, index) => ({ id: String(index), index, original }));
  // The previous TanStack virtualizer continuously invalidated its ResizeObserver on
  // Windows Chromium, producing an unbounded App render loop even with zero rows.
  // 2,816 rows are small enough for a stable native table and keep correctness ahead
  // of an optional rendering optimization.
  const virtualRows = tableRows.map((_row, index) => ({ index, start: index * 31, size: 31 }));
  const rowVirtualizer = {
    getTotalSize: () => tableRows.length * 31,
    scrollToIndex: (index: number, _options?: unknown) => { if (tableViewportRef.current) tableViewportRef.current.scrollTop = index * 31; },
    measureElement: undefined,
  };
  useLayoutEffect(() => { if (analysis) markTiming("table-render-complete"); }, [analysis, virtualRows.length, visibleColumns]);
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
        <button className="button primary analyse-button" onClick={analyse} disabled={lifecycle === "running"}>{lifecycle === "running" ? "ANALYSING" : "ANALYSE"}</button>
      </section>

      {error && <div className="error-line" role="alert"><strong>{lifecycle === "failed" ? "Analysis issue" : "Export issue"}</strong><span>{error}</span></div>}

      <section className="summary-section" aria-label="Analysis summary">
        <div className="summary-line">
          <span className="summary-item">Matched <b>{analysis ? analysis.summary.matched : "—"}</b></span>
          <Counter label="EIVA Only" status="EIVA_ONLY" count={analysis?.summary.eiva_only} current={navCurrent.EIVA_ONLY} ordinal={problemGroups.EIVA_ONLY.indexOf(navCurrent.EIVA_ONLY ?? -1) + 1} total={problemGroups.EIVA_ONLY.length} onNavigate={navigate} />
          <span className="summary-item summary-no_shot">NO_SHOT <b>{analysis ? analysis.summary.no_shot ?? 0 : "—"}</b></span>
          <Counter label="Invalid" status="RECORDER_INVALID" count={analysis?.summary.recorder_invalid} current={navCurrent.RECORDER_INVALID} ordinal={problemGroups.RECORDER_INVALID.indexOf(navCurrent.RECORDER_INVALID ?? -1) + 1} total={problemGroups.RECORDER_INVALID.length} onNavigate={navigate} />
          <Counter label="Review" status="REVIEW" count={analysis?.summary.review} current={navCurrent.REVIEW} ordinal={problemGroups.REVIEW.indexOf(navCurrent.REVIEW ?? -1) + 1} total={problemGroups.REVIEW.length} onNavigate={navigate} />
        </div>
        <div className="summary-detail"><span>Total issues: <b>{analysis ? analysis.summary.total_issues : "—"}</b></span><span>FFID jump: <b>{analysis?.ffid_jumps.length ? analysis.ffid_jumps.map((jump) => `${jump.from} → ${jump.to}`).join(", ") : analysis ? "none" : "—"}</b></span></div>
        {analysis && <div className={`correction-line ${correctionReady ? "correction-ready" : "correction-blocked"}`}>
          <strong>{correctionReady ? "Correction ready" : "Correction blocked"}</strong>
          <span>{correctionReady
            ? `${analysis.correction.retained.toLocaleString()} paired shots | ${analysis.summary.total_issues} issues resolved | Validation PASS`
            : analysis.correction.blocking_reasons.join("; ") || analysis.validation.errors.join("; ") || "Validation did not pass"}</span>
        </div>}
        {analysis && <div className="correction-preview"><span>Retained / renumbered: <b>{analysis.correction.retained.toLocaleString()}</b></span><span>EIVA-only removed: <b>{analysis.correction.eiva_only_removed}</b></span><span>NO_SHOT removed: <b>{analysis.correction.no_shot_removed}</b></span><span>Fixed pair rows: <b>{analysis.validation.fixed_eiva_rows.toLocaleString()}</b></span><span>FFID: <b>{analysis.validation.ffid_match_count}/{analysis.validation.ffid_pair_count}</b></span><span>Coordinates: <b>{analysis.validation.coordinate_pass_count}/{analysis.validation.ffid_pair_count}</b></span><span>Max distance: <b>{analysis.validation.max_distance_m === null ? "—" : `${analysis.validation.max_distance_m.toFixed(3)} m`}</b></span></div>}
      </section>

      <section className="timeline-section" aria-label="Acquisition timeline">
        <div className="section-heading"><h2>Acquisition timeline</h2><span>Positions {analysis ? `${visibleStart}–${visibleEnd} of ${timelineTotal}` : "—"}</span></div>
        <div className="timeline-viewport" ref={timelineRef} onScroll={handleTimelineScroll} onWheel={handleWheel} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp}>
          <canvas ref={timelineCanvasRef} className="timeline-canvas" width={timelineTrackWidth} height={60} style={{ width: timelineTrackWidth, height: 60 }} onClick={handleTimelineClick} onMouseMove={handleTimelineMove} onMouseLeave={handleTimelineLeave} aria-label="Acquisition timeline" />
          {timelineTooltip && <div className="timeline-tooltip" style={{ left: timelineTooltip.x, top: timelineTooltip.y }}>{timelineTooltip.text}</div>}
        </div>
      </section>

      <section className="table-section" aria-label="QC detail">
        <div className="section-heading table-heading"><h2>QC detail</h2><div className="columns-wrap"><button className="button secondary compact-button" onClick={() => setColumnsOpen((open) => !open)} aria-expanded={columnsOpen}><Icon name="columns" />Columns</button>{columnsOpen && <div className="columns-popover"><strong>Visible columns</strong><div className="column-list">{allColumns.map((column) => <label key={column.key}><input type="checkbox" checked={visibleColumns.includes(column.key)} onChange={() => setVisibleColumns((current) => current.includes(column.key) ? current.filter((key) => key !== column.key) : [...current, column.key])} />{column.label}</label>)}</div><button className="button primary compact-button" onClick={() => setColumnsOpen(false)}>Apply</button></div>}</div></div>
        <div className="table-viewport" ref={tableViewportRef}><table><thead><tr>{columns.map((column) => <th key={column.id}>{column.header}</th>)}</tr></thead><tbody style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: "relative" }}>{virtualRows.map((virtualRow) => { const row = tableRows[virtualRow.index]; return <tr key={row.id} ref={rowVirtualizer.measureElement} data-index={virtualRow.index} className="virtual-row" style={{ height: `${virtualRow.size}px`, transform: `translateY(${virtualRow.start}px)` }} data-selected={selectedIndex === row.index} data-status={row.original.status} onClick={() => selectRecord(row.index)}>{columns.map((column) => <td key={column.id} className={column.id === "status" ? `status-cell status-${row.original.status.toLowerCase()}` : undefined}>{getCellValue(row.original, column.id)}</td>)}</tr>; })}</tbody></table>{!analysis && <div className="empty-table">Analyse a file pair to load QC detail.</div>}</div>
      </section>
    </main>
    <footer className="app-footer"><span>{analysis ? `${records.length.toLocaleString()} result rows` : "Ready for an offline analysis"}</span><div className="footer-actions"><button className="button secondary compact-button" onClick={exportQc} disabled={!analysis}><Icon name="download" />Export QC CSV</button><button className="button secondary compact-button" onClick={saveFixedEiva} disabled={!correctionReady}>Save Fixed EIVA</button><button className="button primary compact-button" onClick={saveFixedPair} disabled={!correctionReady}>Save Fixed Pair</button></div></footer>
    {toast && <div className="toast" role="status">{toast}</div>}
  </div>;
}

function Counter({ label, status, count, current, ordinal, total, onNavigate }: { label: string; status: "EIVA_ONLY" | "RECORDER_INVALID" | "REVIEW"; count?: number; current: number | null; ordinal: number; total: number; onNavigate: (status: "EIVA_ONLY" | "RECORDER_INVALID" | "REVIEW", step: 1 | -1) => void }) {
  return <span className={`summary-item summary-${status.toLowerCase()}`}>{label} <b>{count ?? "—"}</b><span className="counter-nav"><button className="icon-button" onClick={() => onNavigate(status, -1)} disabled={!total} title={`Previous ${label.toLowerCase()}`}><Icon name="left" /></button><span>{current === null ? (total ? "1" : "0") : `${ordinal} / ${total}`}</span><button className="icon-button" onClick={() => onNavigate(status, 1)} disabled={!total} title={`Next ${label.toLowerCase()}`}><Icon name="right" /></button></span></span>;
}
