import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from shotlogfixer.matcher import match_records
from shotlogfixer.parsers import parse_eiva, parse_recorder
from shotlogfixer.qc import (anomaly_event_count, anomaly_frequency_per_1000,
                             ffid_discontinuities, next_cycle,
                             problem_result_indices)
from shotlogfixer.report import export_csv


class App(tk.Tk):
    TIMELINE_STEP = 6

    def __init__(self):
        super().__init__()
        self.title("ShotLogFixer Phase 1 QC")
        self.geometry("1120x760")
        self.eiva_path, self.recorder_path = tk.StringVar(), tk.StringVar()
        self.results, self.eiva_records = [], []
        self.nav_positions, self.nav_current = {}, {}
        self.column_vars, self.column_defs = {}, {}
        self._eiva_position_by_result = {}
        self._timeline_hits = []
        self._timeline_dragging = False
        self._timeline_press_x = 0
        self._build()

    def _build(self):
        inputs = ttk.LabelFrame(self, text="Input files", padding=6)
        inputs.pack(fill="x", padx=8, pady=(8, 4))
        for row, (label, variable) in enumerate((("EIVA Log", self.eiva_path), ("Recorder Log", self.recorder_path))):
            ttk.Label(inputs, text=label, width=14).grid(row=row, column=0, sticky="w")
            ttk.Entry(inputs, textvariable=variable, width=85).grid(row=row, column=1, sticky="ew", padx=5)
            ttk.Button(inputs, text="Select File", command=lambda v=variable: v.set(filedialog.askopenfilename())).grid(row=row, column=2)
        inputs.columnconfigure(1, weight=1)
        ttk.Button(inputs, text="ANALYSE", command=self.analyse).grid(row=0, column=3, rowspan=2, padx=(12, 0), sticky="ns")

        self.summary = ttk.Frame(self, padding=(8, 4))
        self.summary.pack(fill="x")
        self._make_counter_row("Matched", informational=True)
        for status, label in (("EIVA_ONLY", "EIVA-only"), ("RECORDER_INVALID", "Invalid"), ("REVIEW", "Review")):
            self._make_counter_row(label, status)
        self.metrics = ttk.Label(self.summary, text="Flagged records: —   Anomaly events: —   Anomaly frequency: —")
        self.metrics.grid(row=4, column=0, columnspan=5, sticky="w", pady=(3, 0))

        timeline_box = ttk.LabelFrame(self, text="Acquisition timeline", padding=5)
        timeline_box.pack(fill="x", padx=8, pady=4)
        self.range_label = ttk.Label(timeline_box, text="Positions —")
        self.range_label.pack(anchor="w")
        self.timeline = tk.Canvas(timeline_box, height=48, bg="white", highlightthickness=1, highlightbackground="#bbb")
        self.timeline.pack(fill="x", expand=True)
        self.timeline_scroll = ttk.Scrollbar(timeline_box, orient="horizontal", command=self.timeline.xview)
        self.timeline_scroll.pack(fill="x")
        self.timeline.configure(xscrollcommand=self._timeline_xscroll)
        self.timeline.bind("<ButtonPress-1>", self._timeline_press)
        self.timeline.bind("<B1-Motion>", self._timeline_drag)
        self.timeline.bind("<ButtonRelease-1>", self._timeline_release)
        self.timeline.bind("<Shift-MouseWheel>", self._timeline_wheel)
        self.timeline.bind("<Shift-Button-4>", lambda _event: self.timeline.xview_scroll(-3, "units"))
        self.timeline.bind("<Shift-Button-5>", lambda _event: self.timeline.xview_scroll(3, "units"))
        self.timeline.bind("<Configure>", lambda _event: self._draw_timeline())

        table_head = ttk.Frame(self, padding=(8, 4, 8, 0))
        table_head.pack(fill="x")
        ttk.Label(table_head, text="QC detail").pack(side="left")
        self.columns_button = ttk.Button(table_head, text="Columns", command=self._columns_dialog)
        self.columns_button.pack(side="right")
        table_frame = ttk.Frame(self, padding=8)
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, show="headings")
        self.tree_scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree_scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.tree_scroll_y.set, xscrollcommand=self.tree_scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree_scroll_y.grid(row=0, column=1, sticky="ns")
        self.tree_scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1); table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._table_selected)

        bottom = ttk.Frame(self, padding=(8, 0, 8, 8)); bottom.pack(fill="x")
        ttk.Button(bottom, text="Export QC CSV", command=self.export).pack(side="right")

    def _make_counter_row(self, label, status=None, informational=False):
        row = 0 if informational else {"EIVA_ONLY": 1, "RECORDER_INVALID": 2, "REVIEW": 3}[status]
        label_widget = ttk.Label(self.summary, text=f"{label}:")
        label_widget.grid(row=row, column=0, sticky="w")
        value = ttk.Label(self.summary, text="—", width=8)
        value.grid(row=row, column=1, sticky="w")
        if informational:
            self.matched_value = value
            return
        position = ttk.Label(self.summary, text="", width=8); position.grid(row=row, column=2, sticky="w")
        prev = ttk.Button(self.summary, text="<", width=3, command=lambda s=status: self._navigate(s, -1)); prev.grid(row=row, column=3)
        nxt = ttk.Button(self.summary, text=">", width=3, command=lambda s=status: self._navigate(s, 1)); nxt.grid(row=row, column=4)
        value.bind("<Button-1>", lambda _event, s=status: self._navigate(s, 1))
        label_widget.bind("<Button-1>", lambda _event, s=status: self._navigate(s, 1))
        setattr(self, f"{status.lower()}_value", value); setattr(self, f"{status.lower()}_position", position)

    def analyse(self):
        eiva_path = self.eiva_path.get().strip()
        recorder_path = self.recorder_path.get().strip()
        if not eiva_path and not recorder_path:
            self._show_error("Input files", "Please select both input files.")
            return
        if not eiva_path:
            self._show_error("Input files", "Please select an EIVA log file.")
            return
        if not recorder_path:
            self._show_error("Input files", "Please select a recorder header file.")
            return
        if not self._validate_path(eiva_path, "EIVA") or not self._validate_path(recorder_path, "recorder"):
            return
        self._clear_analysis()
        try:
            eiva_records = parse_eiva(eiva_path)
        except PermissionError as exc:
            self._show_error("EIVA file", "Unable to open the selected EIVA file.", str(exc)); return
        except (OSError, ValueError) as exc:
            self._show_error("EIVA file", "Unable to parse the selected EIVA file.", str(exc)); return
        try:
            recorder = parse_recorder(recorder_path)
        except PermissionError as exc:
            self._show_error("Recorder file", "Unable to open the selected recorder file.", str(exc)); return
        except (OSError, ValueError) as exc:
            self._show_error("Recorder file", "Unable to parse the selected recorder file.", str(exc)); return
        self.eiva_records = eiva_records
        self.results = match_records(eiva_records, recorder)
        self._configure_columns()
        self._populate_table()
        self._update_counters()
        self._draw_timeline()

    def _configure_columns(self):
        self.column_defs = {
            "eiva_ffid": "EIVA FFID", "recorder_ffid": "Recorder FFID",
            "eiva_coord": "EIVA Coordinate", "recorder_coord": "Recorder Coordinate",
            "distance": "Distance (m)", "status": "Status", "diagnostic": "Diagnostic",
            "recorder_x": "Recorder SOU_X", "recorder_y": "Recorder SOU_Y",
        }
        for header in (self.eiva_records[0].original_values_by_column if self.eiva_records else {}):
            self.column_defs.setdefault("eiva_raw:" + header, "EIVA " + header)
        defaults = {key for key in self.column_defs if key in {"eiva_ffid", "recorder_ffid", "eiva_coord", "recorder_coord", "distance", "status"}}
        old = {key for key, var in self.column_vars.items() if var.get()}
        self.column_vars = {key: tk.BooleanVar(value=(key in old if old else key in defaults)) for key in self.column_defs}

    def _visible_columns(self):
        return [key for key in self.column_defs if self.column_vars.get(key, tk.BooleanVar()).get()]

    def _value(self, result, key):
        e, rec = result.eiva_record, result.recorder_record
        if key == "eiva_ffid": return e.original_ffid if e else ""
        if key == "recorder_ffid": return rec.ffid if rec else ""
        if key == "eiva_coord": return f"{e.easting_spark:.3f}, {e.northing_spark:.3f}" if e else ""
        if key == "recorder_coord": return f"{rec.source_x:.3f}, {rec.source_y:.3f}" if rec else ""
        if key == "distance": return f"{result.distance_m:.3f}" if result.distance_m is not None else ""
        if key == "status": return result.status
        if key == "diagnostic": return result.diagnostic
        if key == "recorder_x": return f"{rec.source_x:.5f}" if rec else ""
        if key == "recorder_y": return f"{rec.source_y:.5f}" if rec else ""
        return e.original_values_by_column.get(key.split(":", 1)[1], "") if e else ""

    def _populate_table(self):
        columns = self._visible_columns(); self.tree.configure(columns=columns)
        for key in columns:
            self.tree.heading(key, text=self.column_defs[key]); self.tree.column(key, width=145, anchor="w")
        for item in self.tree.get_children(): self.tree.delete(item)
        for index, result in enumerate(self.results):
            self.tree.insert("", "end", iid=str(index), values=[self._value(result, key) for key in columns])

    def _columns_dialog(self):
        if not self.results: return
        window = tk.Toplevel(self)
        window.title("Columns")
        window.transient(self)
        window.resizable(False, True)
        body = ttk.Frame(window, padding=8); body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, width=300, height=min(430, max(150, len(self.column_defs) * 26)), highlightthickness=0)
        scroll = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        checks = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=checks, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        checks.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.grid(row=0, column=0, sticky="nsew"); scroll.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1); body.columnconfigure(0, weight=1)
        for row, key in enumerate(self.column_defs):
            ttk.Checkbutton(checks, text=self.column_defs[key], variable=self.column_vars[key]).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        ttk.Button(body, text="Apply", command=lambda: (self._populate_table(), window.destroy())).grid(row=1, column=0, columnspan=2, pady=(8, 0))
        window.update_idletasks()
        x = self.columns_button.winfo_rootx()
        y = self.columns_button.winfo_rooty() + self.columns_button.winfo_height() + 4
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        x = max(0, min(x, self.winfo_screenwidth() - width - 8))
        y = max(0, min(y, self.winfo_screenheight() - height - 8))
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.grab_set()

    def _update_counters(self):
        counts = {status: len(problem_result_indices(self.results, status)) for status in ("EIVA_ONLY", "RECORDER_INVALID", "REVIEW")}
        self.matched_value.config(text=str(sum(r.status == "MATCHED" for r in self.results)))
        for status in counts:
            getattr(self, f"{status.lower()}_value").config(text=str(counts[status]))
            getattr(self, f"{status.lower()}_position").config(text=f"{'1' if counts[status] else '0'} / {counts[status]}")
        flagged = sum(counts.values()); events = anomaly_event_count(self.results); freq = anomaly_frequency_per_1000(self.results, len(self.eiva_records))
        jumps = ffid_discontinuities(self.eiva_records)
        jump_text = "none" if not jumps else ", ".join(f"{before}→{after}" for before, after in jumps)
        self.metrics.config(text=f"Flagged records: {flagged}   Anomaly events: {events}   Anomaly frequency: {freq:.2f} / 1000 shots   FFID jumps: {jump_text}")
        self.nav_positions = {status: problem_result_indices(self.results, status) for status in counts}; self.nav_current = {}

    def _navigate(self, status, step):
        index = next_cycle(self.nav_positions.get(status, []), self.nav_current.get(status), step)
        if index is None: return
        self.nav_current[status] = index; positions = self.nav_positions[status]
        getattr(self, f"{status.lower()}_position").config(text=f"{positions.index(index)+1} / {len(positions)}")
        self._select_result(index)

    def _select_result(self, index):
        iid = str(index); self.tree.selection_set(iid); self.tree.focus(iid); self.tree.see(iid); self._ensure_timeline_visible(index)

    def _result_position(self, index):
        result = self.results[index]
        if result.eiva_record:
            return next((i for i, e in enumerate(self.eiva_records) if e.source_line_number == result.eiva_record.source_line_number), 0)
        for later in range(index + 1, len(self.results)):
            if self.results[later].eiva_record: return self._result_position(later)
        for earlier in range(index - 1, -1, -1):
            if self.results[earlier].eiva_record: return self._result_position(earlier)
        return 0

    def _ensure_timeline_visible(self, result_index):
        if not self.eiva_records: return
        x = self._result_position(result_index) * self.TIMELINE_STEP
        visible = max(1, self.timeline.winfo_width()); total = max(visible, len(self.eiva_records) * self.TIMELINE_STEP)
        left = max(0, min(total - visible, x - visible // 2)); self.timeline.xview_moveto(left / total)
        self._update_range_label()

    def _table_selected(self, _event):
        selection = self.tree.selection()
        if selection: self._ensure_timeline_visible(int(selection[0]))

    def _draw_timeline(self):
        self.timeline.delete("all"); self._timeline_hits = []
        if not self.eiva_records: self.range_label.config(text="Positions —"); return
        total = max(self.timeline.winfo_width(), len(self.eiva_records) * self.TIMELINE_STEP); self.timeline.configure(scrollregion=(0, 0, total, 48))
        eiva_position = {r.eiva_record.source_line_number: i for i, r in enumerate(self.results) if r.eiva_record}
        priority = {"MATCHED": 0, "EIVA_ONLY": 1, "REVIEW": 2, "RECORDER_INVALID": 3}; colors = {"MATCHED": "#2e9d50", "EIVA_ONLY": "#d33", "REVIEW": "#f90", "RECORDER_INVALID": "#b65f00"}
        by_pixel = {}
        for result_index, result in enumerate(self.results):
            position = self._result_position(result_index); x = position * self.TIMELINE_STEP + 1; current = by_pixel.get(x)
            if current is None or priority[result.status] > priority[current[0]]: by_pixel[x] = (result.status, result_index)
            if result.status in {"EIVA_ONLY", "REVIEW", "RECORDER_INVALID"}: self._timeline_hits.append((x, result_index))
        for x, (status, result_index) in by_pixel.items():
            self.timeline.create_rectangle(x, 8, x + 4, 38, fill=colors[status], outline=colors[status], tags=(f"result_{result_index}",))
        self._update_range_label()

    def _timeline_press(self, event):
        self._timeline_press_x = event.x
        self._timeline_dragging = False
        self.timeline.scan_mark(event.x, event.y)

    def _timeline_drag(self, event):
        if abs(event.x - self._timeline_press_x) > 3:
            self._timeline_dragging = True
        self.timeline.scan_dragto(event.x, event.y, gain=1)

    def _timeline_release(self, event):
        if not self._timeline_dragging:
            self._timeline_click(event)

    def _timeline_wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        self.timeline.xview_scroll(delta * 3, "units")
        return "break"

    def _timeline_click(self, event):
        x = self.timeline.canvasx(event.x); nearby = [(abs(x - marker), index) for marker, index in self._timeline_hits if abs(x - marker) <= self.TIMELINE_STEP * 2]
        if nearby: self._select_result(min(nearby)[1])

    def _update_range_label(self):
        if not self.eiva_records: return
        visible = max(1, self.timeline.winfo_width()); left = int(self.timeline.canvasx(0) / self.TIMELINE_STEP) + 1; count = max(1, visible // self.TIMELINE_STEP); right = min(len(self.eiva_records), left + count - 1)
        self.range_label.config(text=f"Positions {left}–{right} of {len(self.eiva_records)}")

    def _timeline_xscroll(self, *args):
        self.timeline_scroll.set(*args)
        self._update_range_label()

    def _validate_path(self, value, label):
        path = Path(value)
        if not path.exists():
            self._show_error("Input file", f"The selected {label} file does not exist:\n{value}")
            return False
        if not path.is_file():
            self._show_error("Input file", f"The selected {label} path is not a file:\n{value}")
            return False
        return True

    def _show_error(self, title, message, detail=None):
        if detail:
            message = f"{message}\n\nDetails: {detail}"
        messagebox.showerror(title, message)

    def _clear_analysis(self):
        self.results, self.eiva_records = [], []
        self.nav_positions, self.nav_current = {}, {}
        for item in self.tree.get_children(): self.tree.delete(item)
        self.timeline.delete("all")
        self.timeline.configure(scrollregion=(0, 0, 0, 48))
        self.range_label.config(text="Positions —")
        self.matched_value.config(text="—")
        for status in ("EIVA_ONLY", "RECORDER_INVALID", "REVIEW"):
            getattr(self, f"{status.lower()}_value").config(text="—")
            getattr(self, f"{status.lower()}_position").config(text="")
        self.metrics.config(text="Flagged records: —   Anomaly events: —   Anomaly frequency: —")

    def export(self):
        if not self.results:
            self._show_error("Export QC CSV", "Please analyse a valid EIVA and recorder file pair first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path: return
        try:
            export_csv(path, self.results)
        except PermissionError as exc:
            self._show_error("Export QC CSV", "Unable to write the QC CSV file.", str(exc))
        except OSError as exc:
            self._show_error("Export QC CSV", "Unable to write the QC CSV file.", str(exc))


if __name__ == "__main__":
    App().mainloop()
