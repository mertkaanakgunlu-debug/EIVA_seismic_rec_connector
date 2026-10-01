import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from shotlogfixer.matcher import match_records
from shotlogfixer.analysis_parameters import AnalysisParameters
from shotlogfixer.parsers import parse_eiva, parse_recorder
from shotlogfixer.qc import (anomaly_event_count, anomaly_frequency_per_1000,
                             ffid_discontinuities, next_cycle,
                             problem_result_indices)
from shotlogfixer.report import export_txt
from shotlogfixer.theme import get_theme


class App(tk.Tk):
    TIMELINE_STEP = 6

    def __init__(self):
        super().__init__()
        self.title("ShotLogFixer")
        self.geometry("1160x800")
        self.minsize(900, 650)
        self.theme_name = tk.StringVar(value="Light")
        self.theme = get_theme("Light")
        self.eiva_path, self.recorder_path = tk.StringVar(), tk.StringVar()
        self.shot_interval = tk.StringVar(value="3.125")
        self.analysis_parameters = None
        self.results, self.eiva_records = [], []
        self.nav_positions, self.nav_current = {}, {}
        self.column_vars, self.column_defs = {}, {}
        self._timeline_hits = []
        self._timeline_dragging = False
        self._timeline_press_x = 0
        self._build()
        self._apply_theme()

    def _build(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.configure(bg=self.theme["background"])

        header = ttk.Frame(self, style="App.TFrame", padding=(18, 14, 18, 10)); header.pack(fill="x")
        self.status_dots = tk.Canvas(header, width=46, height=20, highlightthickness=0, bg=self.theme["background"]); self.status_dots.pack(side="left", padx=(0, 10))
        title_box = ttk.Frame(header, style="App.TFrame"); title_box.pack(side="left")
        ttk.Label(title_box, text="ShotLogFixer", style="Title.TLabel").pack(anchor="w")
        self.subtitle = ttk.Label(title_box, text="Phase 1 QC cockpit", style="Secondary.TLabel"); self.subtitle.pack(anchor="w")
        theme_box = ttk.Frame(header, style="App.TFrame"); theme_box.pack(side="right")
        ttk.Label(theme_box, text="Theme", style="Secondary.TLabel").pack(side="left", padx=(0, 6))
        self.theme_choice = ttk.Combobox(theme_box, textvariable=self.theme_name, values=("Light", "Dark", "System"), state="readonly", width=9)
        self.theme_choice.pack(side="left"); self.theme_choice.bind("<<ComboboxSelected>>", self._theme_changed)

        inputs = ttk.LabelFrame(self, text="Input files", style="Panel.TLabelframe", padding=12); inputs.pack(fill="x", padx=18, pady=(0, 8))
        for row, (label, variable) in enumerate((("EIVA Log", self.eiva_path), ("Recorder Log", self.recorder_path))):
            ttk.Label(inputs, text=label, width=14, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(inputs, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            ttk.Button(inputs, text="Browse…", command=lambda v=variable: v.set(filedialog.askopenfilename())).grid(row=row, column=2, pady=4)
        ttk.Label(inputs, text="Shot Interval", width=14, style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(inputs, textvariable=self.shot_interval, width=12).grid(row=2, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(inputs, text="m  (tolerance = half interval)", style="Secondary.TLabel").grid(row=2, column=2, sticky="w", pady=4)
        inputs.columnconfigure(1, weight=1)
        self.analyse_button = ttk.Button(inputs, text="ANALYSE", style="Accent.TButton", command=self.analyse); self.analyse_button.grid(row=0, column=3, rowspan=3, padx=(16, 0), sticky="ns")

        self.summary = ttk.Frame(self, style="App.TFrame", padding=(18, 4, 18, 6)); self.summary.pack(fill="x")
        self.card_frame = ttk.Frame(self.summary, style="App.TFrame"); self.card_frame.pack(fill="x")
        self._make_counter_row("Matched", informational=True)
        for status, label in (("EIVA_ONLY", "EIVA Only"), ("RECORDER_INVALID", "Invalid"), ("REVIEW", "Review")):
            self._make_counter_row(label, status)
        self.metrics = ttk.Label(self.summary, text="Flagged records: —   Anomaly events: —   Anomaly frequency: —", style="Metric.TLabel"); self.metrics.pack(anchor="w", pady=(8, 0))

        timeline_box = ttk.LabelFrame(self, text="Acquisition timeline", style="Panel.TLabelframe", padding=10); timeline_box.pack(fill="x", padx=18, pady=4)
        self.range_label = ttk.Label(timeline_box, text="Positions —", style="Secondary.TLabel"); self.range_label.pack(anchor="w", pady=(0, 6))
        self.timeline = tk.Canvas(timeline_box, height=52, highlightthickness=1); self.timeline.pack(fill="x", expand=True)
        self.timeline_scroll = ttk.Scrollbar(timeline_box, orient="horizontal", command=self.timeline.xview); self.timeline_scroll.pack(fill="x", pady=(6, 0))
        self.timeline.configure(xscrollcommand=self._timeline_xscroll)
        self.timeline.bind("<ButtonPress-1>", self._timeline_press); self.timeline.bind("<B1-Motion>", self._timeline_drag); self.timeline.bind("<ButtonRelease-1>", self._timeline_release)
        self.timeline.bind("<Shift-MouseWheel>", self._timeline_wheel); self.timeline.bind("<Shift-Button-4>", lambda _event: self.timeline.xview_scroll(-3, "units")); self.timeline.bind("<Shift-Button-5>", lambda _event: self.timeline.xview_scroll(3, "units")); self.timeline.bind("<Configure>", lambda _event: self._draw_timeline())

        table_head = ttk.Frame(self, style="App.TFrame", padding=(18, 10, 18, 4)); table_head.pack(fill="x")
        ttk.Label(table_head, text="QC detail", style="Section.TLabel").pack(side="left")
        self.columns_button = ttk.Button(table_head, text="Columns", command=self._columns_dialog); self.columns_button.pack(side="right")
        table_frame = ttk.Frame(self, style="App.TFrame", padding=(18, 0, 18, 8)); table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, show="headings")
        self.tree_scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview); self.tree_scroll_x = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.tree_scroll_y.set, xscrollcommand=self.tree_scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); self.tree_scroll_y.grid(row=0, column=1, sticky="ns"); self.tree_scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1); table_frame.columnconfigure(0, weight=1); self.tree.bind("<<TreeviewSelect>>", self._table_selected)
        bottom = ttk.Frame(self, style="App.TFrame", padding=(18, 0, 18, 14)); bottom.pack(fill="x")
        ttk.Button(bottom, text="Export QC TXT", style="Secondary.TButton", command=self.export).pack(side="right")

    def _make_counter_row(self, label, status=None, informational=False):
        card = ttk.Frame(self.card_frame, style="Card.TFrame", padding=(14, 10)); card.pack(side="left", fill="x", expand=True, padx=(0, 8))
        title = ttk.Label(card, text=label, style="CardLabel.TLabel"); title.pack(anchor="w")
        value = ttk.Label(card, text="—", style="CardValue.TLabel"); value.pack(anchor="w")
        if informational:
            self.matched_value = value
            return
        nav = ttk.Frame(card, style="Card.TFrame"); nav.pack(fill="x", pady=(3, 0))
        position = ttk.Label(nav, text="", style="CardLabel.TLabel"); position.pack(side="left")
        ttk.Button(nav, text="<", width=3, command=lambda s=status: self._navigate(s, -1)).pack(side="right", padx=(3, 0))
        ttk.Button(nav, text=">", width=3, command=lambda s=status: self._navigate(s, 1)).pack(side="right")
        value.bind("<Button-1>", lambda _event, s=status: self._navigate(s, 1)); title.bind("<Button-1>", lambda _event, s=status: self._navigate(s, 1))
        setattr(self, f"{status.lower()}_value", value); setattr(self, f"{status.lower()}_position", position)

    def _apply_theme(self):
        t = self.theme; s = self.style
        self.configure(bg=t["background"])
        s.configure("App.TFrame", background=t["background"]); s.configure("Panel.TLabelframe", background=t["panel"], foreground=t["text"], bordercolor=t["border"]); s.configure("Panel.TLabelframe.Label", background=t["panel"], foreground=t["text"]); s.configure("Panel.TLabel", background=t["panel"], foreground=t["text"])
        s.configure("Title.TLabel", background=t["background"], foreground=t["text"], font=("Segoe UI", 18, "bold")); s.configure("Section.TLabel", background=t["background"], foreground=t["text"], font=("Segoe UI", 11, "bold")); s.configure("Secondary.TLabel", background=t["background"], foreground=t["secondary"]); s.configure("Metric.TLabel", background=t["background"], foreground=t["secondary"])
        s.configure("Card.TFrame", background=t["panel"], bordercolor=t["border"], relief="solid", borderwidth=1); s.configure("CardLabel.TLabel", background=t["panel"], foreground=t["secondary"]); s.configure("CardValue.TLabel", background=t["panel"], foreground=t["text"], font=("Segoe UI", 18, "bold"))
        s.configure("Accent.TButton", background=t["accent"], foreground="#FFFFFF", padding=(14, 8)); s.map("Accent.TButton", background=[("active", t["accent"])])
        s.configure("Secondary.TButton", padding=(12, 6)); s.configure("Treeview", background=t["panel"], fieldbackground=t["panel"], foreground=t["text"], bordercolor=t["border"], rowheight=28); s.configure("Treeview.Heading", background=t["panel_secondary"], foreground=t["text"], relief="flat", padding=(8, 6)); s.map("Treeview", background=[("selected", t["selected"])], foreground=[("selected", t["text"])])
        s.configure("TCombobox", fieldbackground=t["panel"], background=t["panel"], foreground=t["text"]); s.configure("TEntry", fieldbackground=t["panel"], foreground=t["text"])
        self.tree.tag_configure("MATCHED", foreground=t["matched"]); self.tree.tag_configure("EIVA_ONLY", foreground=t["eiva_only"]); self.tree.tag_configure("REVIEW", foreground=t["review"]); self.tree.tag_configure("RECORDER_INVALID", foreground=t["recorder_invalid"])
        self.timeline.configure(bg=t["panel"], highlightbackground=t["border"]); self.status_dots.configure(bg=t["background"]); self.status_dots.delete("all")
        for x, color in ((7, t["eiva_only"]), (21, t["review"]), (35, t["matched"])): self.status_dots.create_oval(x, 4, x + 10, 14, fill=color, outline=color)
        if self.results: self._populate_table(); self._draw_timeline()

    def _theme_changed(self, _event=None):
        self.theme = get_theme("Light" if self.theme_name.get() == "System" else self.theme_name.get()); self._apply_theme()

    def analyse(self):
        eiva_path, recorder_path = self.eiva_path.get().strip(), self.recorder_path.get().strip()
        if not eiva_path and not recorder_path: self._show_error("Input files", "Please select both input files."); return
        if not eiva_path: self._show_error("Input files", "Please select an EIVA log file."); return
        if not recorder_path: self._show_error("Input files", "Please select a recorder header file."); return
        try: parameters = AnalysisParameters(self.shot_interval.get().strip().replace(",", "."))
        except ValueError as exc: self._show_error("Shot interval", "Enter a finite positive shot interval in metres.", str(exc)); return
        if not self._validate_path(eiva_path, "EIVA") or not self._validate_path(recorder_path, "recorder"): return
        self._clear_analysis()
        try: eiva_records = parse_eiva(eiva_path)
        except PermissionError as exc: self._show_error("EIVA file", "Unable to open the selected EIVA file.", str(exc)); return
        except (OSError, ValueError) as exc: self._show_error("EIVA file", "Unable to parse the selected EIVA file.", str(exc)); return
        try: recorder = parse_recorder(recorder_path)
        except PermissionError as exc: self._show_error("Recorder file", "Unable to open the selected recorder file.", str(exc)); return
        except (OSError, ValueError) as exc: self._show_error("Recorder file", "Unable to parse the selected recorder file.", str(exc)); return
        self.eiva_records, self.results, self.analysis_parameters = eiva_records, match_records(eiva_records, recorder, parameters), parameters; self._configure_columns(); self._populate_table(); self._update_counters(); self._draw_timeline()

    def _configure_columns(self):
        self.column_defs = {"eiva_ffid":"EIVA FFID", "recorder_ffid":"Recorder FFID", "eiva_coord":"EIVA Coordinate", "recorder_coord":"Recorder Coordinate", "distance":"Distance (m)", "status":"Status", "diagnostic":"Diagnostic", "recorder_x":"Recorder SOU_X", "recorder_y":"Recorder SOU_Y"}
        for header in (self.eiva_records[0].original_values_by_column if self.eiva_records else {}): self.column_defs.setdefault("eiva_raw:" + header, "EIVA " + header)
        defaults = {"eiva_ffid", "recorder_ffid", "eiva_coord", "recorder_coord", "distance", "status"}; old = {key for key, var in self.column_vars.items() if var.get()}; self.column_vars = {key: tk.BooleanVar(value=(key in old if old else key in defaults)) for key in self.column_defs}

    def _visible_columns(self): return [key for key in self.column_defs if self.column_vars.get(key, tk.BooleanVar()).get()]

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
        for key in columns: self.tree.heading(key, text=self.column_defs[key]); self.tree.column(key, width=145, anchor="w")
        for item in self.tree.get_children(): self.tree.delete(item)
        for index, result in enumerate(self.results): self.tree.insert("", "end", iid=str(index), values=[self._value(result, key) for key in columns], tags=(result.status,))

    def _columns_dialog(self):
        if not self.results: return
        window = tk.Toplevel(self); window.title("Visible columns"); window.transient(self); window.resizable(False, True)
        body = ttk.Frame(window, padding=10); body.pack(fill="both", expand=True); ttk.Label(body, text="Choose columns", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        canvas = tk.Canvas(body, width=310, height=min(430, max(150, len(self.column_defs) * 26)), highlightthickness=0, bg=self.theme["panel"]); scroll = ttk.Scrollbar(body, orient="vertical", command=canvas.yview); checks = ttk.Frame(canvas, style="App.TFrame"); canvas.create_window((0, 0), window=checks, anchor="nw"); canvas.configure(yscrollcommand=scroll.set); checks.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))); canvas.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        for row, key in enumerate(self.column_defs): ttk.Checkbutton(checks, text=self.column_defs[key], variable=self.column_vars[key]).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        ttk.Button(body, text="Apply", style="Accent.TButton", command=lambda: (self._populate_table(), window.destroy())).pack(fill="x", pady=(10, 0)); window.update_idletasks(); x = self.columns_button.winfo_rootx(); y = self.columns_button.winfo_rooty() + self.columns_button.winfo_height() + 4; width, height = window.winfo_reqwidth(), window.winfo_reqheight(); x = max(0, min(x, self.winfo_screenwidth() - width - 8)); y = max(0, min(y, self.winfo_screenheight() - height - 8)); window.geometry(f"{width}x{height}+{x}+{y}"); window.grab_set()

    def _update_counters(self):
        counts = {status: len(problem_result_indices(self.results, status)) for status in ("EIVA_ONLY", "RECORDER_INVALID", "REVIEW")}; self.matched_value.config(text=str(sum(r.status == "MATCHED" for r in self.results)))
        for status in counts: getattr(self, f"{status.lower()}_value").config(text=str(counts[status])); getattr(self, f"{status.lower()}_position").config(text=f"{'1' if counts[status] else '0'} / {counts[status]}")
        flagged = sum(counts.values()); events = anomaly_event_count(self.results); freq = anomaly_frequency_per_1000(self.results, len(self.eiva_records)); jumps = ffid_discontinuities(self.eiva_records); jump_text = "none" if not jumps else ", ".join(f"{before}→{after}" for before, after in jumps); self.metrics.config(text=f"Flagged records: {flagged}   Anomaly events: {events}   Anomaly frequency: {freq:.2f} / 1000 shots   FFID jumps: {jump_text}"); self.nav_positions = {status: problem_result_indices(self.results, status) for status in counts}; self.nav_current = {}

    def _navigate(self, status, step):
        index = next_cycle(self.nav_positions.get(status, []), self.nav_current.get(status), step)
        if index is None: return
        self.nav_current[status] = index; positions = self.nav_positions[status]; getattr(self, f"{status.lower()}_position").config(text=f"{positions.index(index)+1} / {len(positions)}"); self._select_result(index)

    def _select_result(self, index):
        iid = str(index); self.tree.selection_set(iid); self.tree.focus(iid); self.tree.see(iid); self._ensure_timeline_visible(index)

    def _result_position(self, index):
        result = self.results[index]
        if result.eiva_record: return next((i for i, e in enumerate(self.eiva_records) if e.source_line_number == result.eiva_record.source_line_number), 0)
        for later in range(index + 1, len(self.results)):
            if self.results[later].eiva_record: return self._result_position(later)
        for earlier in range(index - 1, -1, -1):
            if self.results[earlier].eiva_record: return self._result_position(earlier)
        return 0

    def _ensure_timeline_visible(self, result_index):
        if not self.eiva_records: return
        x = self._result_position(result_index) * self.TIMELINE_STEP; visible = max(1, self.timeline.winfo_width()); total = max(visible, len(self.eiva_records) * self.TIMELINE_STEP); left = max(0, min(total - visible, x - visible // 2)); self.timeline.xview_moveto(left / total); self._update_range_label()

    def _table_selected(self, _event):
        selection = self.tree.selection()
        if selection: self._ensure_timeline_visible(int(selection[0]))

    def _draw_timeline(self):
        self.timeline.delete("all"); self._timeline_hits = []
        if not self.eiva_records: self.range_label.config(text="Positions —"); return
        total = max(self.timeline.winfo_width(), len(self.eiva_records) * self.TIMELINE_STEP); self.timeline.configure(scrollregion=(0, 0, total, 52)); priority = {"MATCHED":0, "EIVA_ONLY":1, "REVIEW":2, "RECORDER_INVALID":3}; colors = {"MATCHED":self.theme["matched"], "EIVA_ONLY":self.theme["eiva_only"], "REVIEW":self.theme["review"], "RECORDER_INVALID":self.theme["recorder_invalid"]}; by_pixel = {}
        for result_index, result in enumerate(self.results):
            x = self._result_position(result_index) * self.TIMELINE_STEP + 1; current = by_pixel.get(x)
            if current is None or priority[result.status] > priority[current[0]]: by_pixel[x] = (result.status, result_index)
            if result.status in {"EIVA_ONLY", "REVIEW", "RECORDER_INVALID"}: self._timeline_hits.append((x, result_index))
        for x, (status, result_index) in by_pixel.items(): self.timeline.create_rectangle(x, 8, x + 4, 40, fill=colors[status], outline=colors[status], width=2 if status != "MATCHED" else 1, tags=(f"result_{result_index}",))
        self._update_range_label()

    def _timeline_press(self, event): self._timeline_press_x, self._timeline_dragging = event.x, False; self.timeline.scan_mark(event.x, event.y)
    def _timeline_drag(self, event):
        if abs(event.x - self._timeline_press_x) > 3: self._timeline_dragging = True
        self.timeline.scan_dragto(event.x, event.y, gain=1)
    def _timeline_release(self, event):
        if not self._timeline_dragging: self._timeline_click(event)
    def _timeline_wheel(self, event): self.timeline.xview_scroll((-1 if event.delta > 0 else 1) * 3, "units"); return "break"
    def _timeline_click(self, event):
        x = self.timeline.canvasx(event.x); nearby = [(abs(x - marker), index) for marker, index in self._timeline_hits if abs(x - marker) <= self.TIMELINE_STEP * 2]
        if nearby: self._select_result(min(nearby)[1])

    def _update_range_label(self):
        if not self.eiva_records: return
        visible = max(1, self.timeline.winfo_width()); left = int(self.timeline.canvasx(0) / self.TIMELINE_STEP) + 1; count = max(1, visible // self.TIMELINE_STEP); right = min(len(self.eiva_records), left + count - 1); self.range_label.config(text=f"Positions {left}–{right} of {len(self.eiva_records)}")
    def _timeline_xscroll(self, *args): self.timeline_scroll.set(*args); self._update_range_label()

    def _validate_path(self, value, label):
        path = Path(value)
        if not path.exists(): self._show_error("Input file", f"The selected {label} file does not exist:\n{value}"); return False
        if not path.is_file(): self._show_error("Input file", f"The selected {label} path is not a file:\n{value}"); return False
        return True
    def _show_error(self, title, message, detail=None): messagebox.showerror(title, f"{message}\n\nDetails: {detail}" if detail else message)
    def _clear_analysis(self):
        self.results, self.eiva_records, self.nav_positions, self.nav_current = [], [], {}, {}
        for item in self.tree.get_children(): self.tree.delete(item)
        self.timeline.delete("all"); self.timeline.configure(scrollregion=(0, 0, 0, 52)); self.range_label.config(text="Positions —"); self.matched_value.config(text="—")
        for status in ("EIVA_ONLY", "RECORDER_INVALID", "REVIEW"): getattr(self, f"{status.lower()}_value").config(text="—"); getattr(self, f"{status.lower()}_position").config(text="")
        self.metrics.config(text="Flagged records: —   Anomaly events: —   Anomaly frequency: —")
    def export(self):
        if not self.results: self._show_error("Export QC TXT", "Please analyse a valid EIVA and recorder file pair first."); return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not path: return
        try: export_txt(path, self.results, self.analysis_parameters)
        except PermissionError as exc: self._show_error("Export QC TXT", "Unable to write the QC TXT file.", str(exc))
        except OSError as exc: self._show_error("Export QC TXT", "Unable to write the QC TXT file.", str(exc))


if __name__ == "__main__": App().mainloop()
