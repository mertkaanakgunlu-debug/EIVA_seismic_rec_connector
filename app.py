"""Legacy Tkinter fallback UI. It drives the same engine as the Electron app: the recorder (reference) is authoritative,
the EIVA log (target) is corrected, and QC observations never decide the correction."""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from shotlogfixer import engine_cli
from shotlogfixer.presentation import ASSOCIATION_LABELS, qc_label
from shotlogfixer.theme import get_theme

GROUPS = (("TARGET_ONLY", "Target-only"), ("INVALID", "Invalid"), ("BLOCKED", "Blocked"), ("QC_SEVERE", "QC severe"), ("QC_WARNING", "QC warnings"))
TONES = {"ok": "matched", "warning": "review", "severe": "recorder_invalid", "target-only": "eiva_only", "invalid": "recorder_invalid"}


def tone(row):
    if row["association"] == "TARGET_ONLY": return "target-only"
    if row["association"] != "ASSIGNED": return "invalid"
    return {"SEVERE": "severe", "WARNING": "warning"}.get(row["qc_severity"], "ok")


def cell(row, key):
    dash = "—"
    if key == "reference_ffid": return row["reference_ffid"] or dash
    if key == "target_ffid": return row["target_ffid"] or dash
    if key == "corrected_ffid": return row["corrected_ffid"] or dash
    if key == "reference_coord": return f"{row['reference_x']:.2f}, {row['reference_y']:.2f}" if row["reference_x"] is not None else dash
    if key == "target_coord": return f"{row['target_x']:.2f}, {row['target_y']:.2f}" if row["target_x"] is not None else dash
    if key == "distance": return f"{row['distance_m']:.3f}" if row["distance_m"] is not None else dash
    if key == "association": return ASSOCIATION_LABELS[row["association"]]
    if key == "qc":
        codes = row["qc_codes"]
        return "OK" if row["qc_severity"] == "OK" or not codes else qc_label(codes[0]) + (f" +{len(codes) - 1}" if len(codes) > 1 else "")
    if key == "diagnostic": return row["diagnostic"] or dash
    return row["target_values"].get(key.split(":", 1)[1], dash) if key.startswith("target_raw:") else ""


def group_indices(rows):
    groups = {key: [] for key, _ in GROUPS}
    for index, row in enumerate(rows):
        if row["association"] == "TARGET_ONLY": groups["TARGET_ONLY"].append(index)
        elif row["association"] in ("INVALID", "NO_SHOT"): groups["INVALID"].append(index)
        elif row["association"] == "BLOCKED": groups["BLOCKED"].append(index)
        if row["qc_severity"] == "SEVERE": groups["QC_SEVERE"].append(index)
        elif row["qc_severity"] == "WARNING": groups["QC_WARNING"].append(index)
    return groups


class App(tk.Tk):
    TIMELINE_STEP = 6

    def __init__(self):
        super().__init__()
        self.title("ShotLogFixer")
        self.geometry("1160x800")
        self.minsize(900, 650)
        self.theme_name = tk.StringVar(value="Light")
        self.theme = get_theme("Light")
        self.reference_path, self.target_path = tk.StringVar(), tk.StringVar()
        self.shot_interval = tk.StringVar(value="3.125")
        self.response, self.rows, self.groups = None, [], {}
        self.nav_current = {}
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
        self.subtitle = ttk.Label(title_box, text="Recorder-authoritative reconciliation (fallback UI)", style="Secondary.TLabel"); self.subtitle.pack(anchor="w")
        theme_box = ttk.Frame(header, style="App.TFrame"); theme_box.pack(side="right")
        ttk.Label(theme_box, text="Theme", style="Secondary.TLabel").pack(side="left", padx=(0, 6))
        self.theme_choice = ttk.Combobox(theme_box, textvariable=self.theme_name, values=("Light", "Dark", "System"), state="readonly", width=9)
        self.theme_choice.pack(side="left"); self.theme_choice.bind("<<ComboboxSelected>>", self._theme_changed)

        inputs = ttk.LabelFrame(self, text="Input files", style="Panel.TLabelframe", padding=12); inputs.pack(fill="x", padx=18, pady=(0, 8))
        for row, (label, variable) in enumerate((("Reference (Recorder)", self.reference_path), ("Target (EIVA)", self.target_path))):
            ttk.Label(inputs, text=label, width=20, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(inputs, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            ttk.Button(inputs, text="Browse…", command=lambda v=variable: v.set(filedialog.askopenfilename() or v.get())).grid(row=row, column=2, pady=4)
        ttk.Label(inputs, text="Shot Interval", width=20, style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(inputs, textvariable=self.shot_interval, width=12).grid(row=2, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(inputs, text="m  (sets QC distance bands only)", style="Secondary.TLabel").grid(row=2, column=2, sticky="w", pady=4)
        inputs.columnconfigure(1, weight=1)
        self.analyse_button = ttk.Button(inputs, text="ANALYSE", style="Accent.TButton", command=self.analyse); self.analyse_button.grid(row=0, column=3, rowspan=3, padx=(16, 0), sticky="ns")

        self.summary = ttk.Frame(self, style="App.TFrame", padding=(18, 4, 18, 6)); self.summary.pack(fill="x")
        self.card_frame = ttk.Frame(self.summary, style="App.TFrame"); self.card_frame.pack(fill="x")
        self._make_counter("Assigned")
        for key, label in GROUPS: self._make_counter(label, key)
        self.metrics = ttk.Label(self.summary, text="Correction: —", style="Metric.TLabel"); self.metrics.pack(anchor="w", pady=(8, 0))

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
        ttk.Button(bottom, text="Save Corrected EIVA", style="Accent.TButton", command=self.save_corrected).pack(side="right")
        ttk.Button(bottom, text="Export QC TXT", style="Secondary.TButton", command=self.export).pack(side="right", padx=(0, 8))

    def _make_counter(self, label, group=None):
        card = ttk.Frame(self.card_frame, style="Card.TFrame", padding=(14, 10)); card.pack(side="left", fill="x", expand=True, padx=(0, 8))
        title = ttk.Label(card, text=label, style="CardLabel.TLabel"); title.pack(anchor="w")
        value = ttk.Label(card, text="—", style="CardValue.TLabel"); value.pack(anchor="w")
        if group is None:
            self.assigned_value = value
            return
        nav = ttk.Frame(card, style="Card.TFrame"); nav.pack(fill="x", pady=(3, 0))
        position = ttk.Label(nav, text="", style="CardLabel.TLabel"); position.pack(side="left")
        ttk.Button(nav, text="<", width=3, command=lambda g=group: self._navigate(g, -1)).pack(side="right", padx=(3, 0))
        ttk.Button(nav, text=">", width=3, command=lambda g=group: self._navigate(g, 1)).pack(side="right")
        value.bind("<Button-1>", lambda _event, g=group: self._navigate(g, 1)); title.bind("<Button-1>", lambda _event, g=group: self._navigate(g, 1))
        setattr(self, f"{group.lower()}_value", value); setattr(self, f"{group.lower()}_position", position)

    def _apply_theme(self):
        t = self.theme; s = self.style
        self.configure(bg=t["background"])
        s.configure("App.TFrame", background=t["background"]); s.configure("Panel.TLabelframe", background=t["panel"], foreground=t["text"], bordercolor=t["border"]); s.configure("Panel.TLabelframe.Label", background=t["panel"], foreground=t["text"]); s.configure("Panel.TLabel", background=t["panel"], foreground=t["text"])
        s.configure("Title.TLabel", background=t["background"], foreground=t["text"], font=("Segoe UI", 18, "bold")); s.configure("Section.TLabel", background=t["background"], foreground=t["text"], font=("Segoe UI", 11, "bold")); s.configure("Secondary.TLabel", background=t["background"], foreground=t["secondary"]); s.configure("Metric.TLabel", background=t["background"], foreground=t["secondary"])
        s.configure("Card.TFrame", background=t["panel"], bordercolor=t["border"], relief="solid", borderwidth=1); s.configure("CardLabel.TLabel", background=t["panel"], foreground=t["secondary"]); s.configure("CardValue.TLabel", background=t["panel"], foreground=t["text"], font=("Segoe UI", 18, "bold"))
        s.configure("Accent.TButton", background=t["accent"], foreground="#FFFFFF", padding=(14, 8)); s.map("Accent.TButton", background=[("active", t["accent"])])
        s.configure("Secondary.TButton", padding=(12, 6)); s.configure("Treeview", background=t["panel"], fieldbackground=t["panel"], foreground=t["text"], bordercolor=t["border"], rowheight=28); s.configure("Treeview.Heading", background=t["panel_secondary"], foreground=t["text"], relief="flat", padding=(8, 6)); s.map("Treeview", background=[("selected", t["selected"])], foreground=[("selected", t["text"])])
        s.configure("TCombobox", fieldbackground=t["panel"], background=t["panel"], foreground=t["text"]); s.configure("TEntry", fieldbackground=t["panel"], foreground=t["text"])
        for name, colour in TONES.items(): self.tree.tag_configure(name, foreground=t[colour])
        self.timeline.configure(bg=t["panel"], highlightbackground=t["border"]); self.status_dots.configure(bg=t["background"]); self.status_dots.delete("all")
        for x, color in ((7, t["eiva_only"]), (21, t["review"]), (35, t["matched"])): self.status_dots.create_oval(x, 4, x + 10, 14, fill=color, outline=color)
        if self.rows: self._populate_table(); self._draw_timeline()

    def _theme_changed(self, _event=None):
        self.theme = get_theme("Light" if self.theme_name.get() == "System" else self.theme_name.get()); self._apply_theme()

    def _payload(self):
        return {"reference_path": self.reference_path.get().strip(), "target_path": self.target_path.get().strip(), "shot_interval_m": self.shot_interval.get().strip()}

    def analyse(self):
        payload = self._payload()
        if not payload["reference_path"] and not payload["target_path"]: self._show_error("Input files", "Please select both input files."); return
        self._clear_analysis()
        analysis, failure = engine_cli.prepare_analysis(payload)
        if failure: self._show_error("Analysis", failure["error"]["message"], failure["error"].get("detail")); return
        self.response = engine_cli.analyse_response(analysis)
        self.rows = self.response["records"]
        self.groups = group_indices(self.rows)
        self._configure_columns(); self._populate_table(); self._update_counters(); self._draw_timeline()

    def _configure_columns(self):
        self.column_defs = {"reference_ffid": "Recorder FFID", "target_ffid": "Target Original FFID", "corrected_ffid": "Corrected FFID", "reference_coord": "Recorder Coordinate", "target_coord": "Target Coordinate", "distance": "Distance (m)", "association": "Association", "qc": "QC", "diagnostic": "Diagnostic"}
        for header in self.response["target_headers"]: self.column_defs.setdefault("target_raw:" + header, "Target " + header)
        defaults = {"reference_ffid", "target_ffid", "corrected_ffid", "reference_coord", "target_coord", "distance", "association", "qc"}
        old = {key for key, var in self.column_vars.items() if var.get()}
        self.column_vars = {key: tk.BooleanVar(value=(key in old if old else key in defaults)) for key in self.column_defs}

    def _visible_columns(self): return [key for key in self.column_defs if self.column_vars.get(key, tk.BooleanVar()).get()]

    def _populate_table(self):
        columns = self._visible_columns(); self.tree.configure(columns=columns)
        for key in columns: self.tree.heading(key, text=self.column_defs[key]); self.tree.column(key, width=145, anchor="w")
        for item in self.tree.get_children(): self.tree.delete(item)
        for index, row in enumerate(self.rows): self.tree.insert("", "end", iid=str(index), values=[cell(row, key) for key in columns], tags=(tone(row),))

    def _columns_dialog(self):
        if not self.rows: return
        window = tk.Toplevel(self); window.title("Visible columns"); window.transient(self); window.resizable(False, True)
        body = ttk.Frame(window, padding=10); body.pack(fill="both", expand=True); ttk.Label(body, text="Choose columns", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        canvas = tk.Canvas(body, width=310, height=min(430, max(150, len(self.column_defs) * 26)), highlightthickness=0, bg=self.theme["panel"]); scroll = ttk.Scrollbar(body, orient="vertical", command=canvas.yview); checks = ttk.Frame(canvas, style="App.TFrame"); canvas.create_window((0, 0), window=checks, anchor="nw"); canvas.configure(yscrollcommand=scroll.set); checks.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))); canvas.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        for row, key in enumerate(self.column_defs): ttk.Checkbutton(checks, text=self.column_defs[key], variable=self.column_vars[key]).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        ttk.Button(body, text="Apply", style="Accent.TButton", command=lambda: (self._populate_table(), window.destroy())).pack(fill="x", pady=(10, 0)); window.update_idletasks(); x = self.columns_button.winfo_rootx(); y = self.columns_button.winfo_rooty() + self.columns_button.winfo_height() + 4; width, height = window.winfo_reqwidth(), window.winfo_reqheight(); x = max(0, min(x, self.winfo_screenwidth() - width - 8)); y = max(0, min(y, self.winfo_screenheight() - height - 8)); window.geometry(f"{width}x{height}+{x}+{y}"); window.grab_set()

    def _update_counters(self):
        summary, correction = self.response["summary"], self.response["correction"]
        self.assigned_value.config(text=str(summary["assigned"]))
        for key, _ in GROUPS:
            count = len(self.groups[key])
            getattr(self, f"{key.lower()}_value").config(text=str(count)); getattr(self, f"{key.lower()}_position").config(text=f"{'1' if count else '0'} / {count}")
        state = "ready" if correction["safe"] else "BLOCKED: " + "; ".join(b["message"] for b in correction["blockers"])
        without = correction.get("reference_without_target", 0)
        missing = f"   Recorder records without an EIVA row (not in the copy): {without}" if without else ""
        self.metrics.config(text=f"Correction {state}   Corrected rows: {correction['corrected_rows']} of {correction['expected_rows']} recorder records   Target-only removed: {correction['target_only_removed']}{missing}   QC warnings never block the corrected copy.")
        self.nav_current = {}

    def _navigate(self, group, step):
        indices = self.groups.get(group, [])
        if not indices: return
        current = self.nav_current.get(group)
        index = indices[0 if step >= 0 else -1] if current not in indices else indices[(indices.index(current) + step) % len(indices)]
        self.nav_current[group] = index; getattr(self, f"{group.lower()}_position").config(text=f"{indices.index(index) + 1} / {len(indices)}"); self._select_result(index)

    def _select_result(self, index):
        iid = str(index); self.tree.selection_set(iid); self.tree.focus(iid); self.tree.see(iid); self._ensure_timeline_visible(index)

    def _result_position(self, index): return max(0, self.rows[index]["acquisition_position"] - 1)

    def _ensure_timeline_visible(self, result_index):
        if not self.rows: return
        x = self._result_position(result_index) * self.TIMELINE_STEP; visible = max(1, self.timeline.winfo_width()); total = max(visible, self._timeline_total() * self.TIMELINE_STEP); left = max(0, min(total - visible, x - visible // 2)); self.timeline.xview_moveto(left / total); self._update_range_label()

    def _timeline_total(self): return self.response["summary"]["target_rows"] if self.response else 0

    def _table_selected(self, _event):
        selection = self.tree.selection()
        if selection: self._ensure_timeline_visible(int(selection[0]))

    def _draw_timeline(self):
        self.timeline.delete("all"); self._timeline_hits = []
        if not self.rows: self.range_label.config(text="Positions —"); return
        total = max(self.timeline.winfo_width(), self._timeline_total() * self.TIMELINE_STEP); self.timeline.configure(scrollregion=(0, 0, total, 52)); priority = {"ok": 0, "warning": 1, "severe": 2, "target-only": 3, "invalid": 3}; by_pixel = {}
        for result_index, row in enumerate(self.rows):
            x = self._result_position(result_index) * self.TIMELINE_STEP + 1; kind = tone(row); current = by_pixel.get(x)
            if current is None or priority[kind] > priority[current[0]]: by_pixel[x] = (kind, result_index)
            if kind != "ok": self._timeline_hits.append((x, result_index))
        for x, (kind, result_index) in by_pixel.items(): colour = self.theme[TONES[kind]]; self.timeline.create_rectangle(x, 8, x + 4, 40, fill=colour, outline=colour, width=2 if kind != "ok" else 1, tags=(f"result_{result_index}",))
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
        if not self.rows: return
        visible = max(1, self.timeline.winfo_width()); left = int(self.timeline.canvasx(0) / self.TIMELINE_STEP) + 1; count = max(1, visible // self.TIMELINE_STEP); total = self._timeline_total(); right = min(total, left + count - 1); self.range_label.config(text=f"Positions {left}–{right} of {total}")
    def _timeline_xscroll(self, *args): self.timeline_scroll.set(*args); self._update_range_label()

    def _show_error(self, title, message, detail=None): messagebox.showerror(title, f"{message}\n\nDetails: {detail}" if detail else message)
    def _clear_analysis(self):
        self.response, self.rows, self.groups, self.nav_current = None, [], {}, {}
        for item in self.tree.get_children(): self.tree.delete(item)
        self.timeline.delete("all"); self.timeline.configure(scrollregion=(0, 0, 0, 52)); self.range_label.config(text="Positions —"); self.assigned_value.config(text="—")
        for key, _ in GROUPS: getattr(self, f"{key.lower()}_value").config(text="—"); getattr(self, f"{key.lower()}_position").config(text="")
        self.metrics.config(text="Correction: —")

    def _run(self, action, path, **extra):
        response = engine_cli.dispatch({**self._payload(), "action": action, "output_path": path, "expected_hashes": self.response["input_hashes"], **extra})
        if not response["ok"]: self._show_error(action, response["error"]["message"], response["error"].get("detail"))
        return response["ok"]

    def export(self):
        if not self.response: self._show_error("Export QC TXT", "Please analyse a valid file pair first."); return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if path: self._run("export_qc", path)

    def save_corrected(self):
        if not self.response or not self.response["correction"]["safe"]: self._show_error("Save corrected copy", "Correction is blocked or no analysis is available; see the summary line."); return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")], title="Save corrected copy of the target (EIVA) file")
        if path and self._run("save_corrected_target", path, overwrite=True): messagebox.showinfo("Saved", f"Corrected copy written to {Path(path).name}. Both source files are unchanged.")


if __name__ == "__main__": App().mainloop()
