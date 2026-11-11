"""Desktop interface for the compound planetary gear designer."""

import math
import tkinter as tk
from dataclasses import replace
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.transforms import Affine2D

from gear_export import export_gear
from gear_search import find_gear_combinations
from gear_system_designer import (
    DEFAULT_DATA,
    Gear,
    GearSet,
    GearSettings,
    draw_gear,
    gear_geometry,
    gear_set_from_values,
    load_gear_set,
    make_gears,
    mesh_phase_warning,
    plot_assembly,
    plot_layout,
)


FIELDS = (
    ("Ts", "太陽輪齒數", "sun_teeth"),
    ("Tp1", "第一行星輪齒數", "planet1_teeth"),
    ("Tp2", "第二行星輪齒數", "planet2_teeth"),
    ("Tr", "內齒圈齒數", "ring_teeth"),
    ("M", "模數 (mm)", "module"),
    ("n", "行星輪組數", "planet_count"),
    ("axle", "預設軸孔 (mm)", "axle_diameter"),
)

GEAR_NAMES = ("太陽輪", "第一行星輪", "第二行星輪", "內齒圈")
PROFILE_FIELDS = (
    ("addendum_ratio", "齒頂倍率"),
    ("dedendum_ratio", "齒根倍率"),
    ("space_ratio", "齒間倍率"),
    ("pressure_angle", "壓力角 (°)"),
    ("fillet_ratio", "齒根圓角倍率（參考）"),
    ("bore_diameter", "軸孔直徑 (mm)"),
)

GEOMETRY_ROWS = (
    ("pitch_diameter", "節圓直徑（節徑）", "mm"),
    ("pitch_radius", "節圓半徑", "mm"),
    ("pitch_circumference", "節圓周長", "mm"),
    ("tip_diameter", "齒頂圓直徑", "mm"),
    ("tip_radius", "齒頂圓半徑", "mm"),
    ("root_diameter", "齒根圓直徑", "mm"),
    ("root_radius", "齒根圓半徑", "mm"),
    ("base_diameter", "基圓直徑", "mm"),
    ("base_radius", "基圓半徑", "mm"),
    ("addendum", "齒頂高", "mm"),
    ("dedendum", "齒根高", "mm"),
    ("tooth_height", "齒高", "mm"),
    ("working_depth", "工作深度", "mm"),
    ("clearance", "齒輪間隙", "mm"),
    ("circular_pitch", "周節", "mm"),
    ("tooth_thickness", "節圓齒厚", "mm"),
    ("tooth_space", "節圓齒間", "mm"),
    ("fillet_radius", "齒根圓角半徑（參考）", "mm"),
    ("diametral_pitch", "徑節（MATLAB 2.54/M）", ""),
    ("pitch_angle", "周節角度", "rad"),
    ("half_pitch_angle", "半周節角度", "rad"),
)


class PlotTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, plot, *, show_phase_warning: bool = False):
        super().__init__(parent, padding=8)
        self.plot = plot
        self.show_phase_warning = show_phase_warning
        self.gear_set = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.notice = ttk.Label(self, wraplength=520, justify="left", foreground="#92400e")
        self.notice.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        self.notice.grid_remove()

        self.plot_area = ttk.Frame(self)
        self.plot_area.grid(row=1, column=0, sticky="nsew")
        self.figure = Figure(figsize=(6, 5), layout="constrained")
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.plot_area)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_area, pack_toolbar=False)
        self.toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def render(self, gear_set: GearSet, gears: list[Gear]) -> None:
        if self.gear_set == gear_set:
            return
        self.figure.clear(keep_observers=True)
        try:
            self.plot(gear_set, gears, figure=self.figure)
        except ValueError as exc:
            notice = str(exc)
            self.plot_area.grid_remove()
        else:
            notice = mesh_phase_warning(gear_set) if self.show_phase_warning else None
            self.plot_area.grid()
            self.toolbar.update()
            self.canvas.draw_idle()

        if notice:
            self.notice.configure(text=notice)
            self.notice.grid()
        else:
            self.notice.grid_remove()
        self.gear_set = gear_set


class GearSearchTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, form: ttk.Frame, defaults: GearSet, current_design, apply_design):
        super().__init__(parent, padding=12)
        self.current_design = current_design
        self.apply_design = apply_design
        self.candidates = []
        self.checked = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        gears = make_gears(defaults)
        dimensions = [
            gear_geometry(defaults.module, gear.teeth, internal=gear.internal, settings=gear.settings)
            for gear in gears
        ]
        orbit = dimensions[0].pitch_diameter + dimensions[1].pitch_diameter
        initial_diameter = math.ceil(max(
            orbit + max(dimensions[1].tip_diameter, dimensions[2].tip_diameter),
            dimensions[3].root_diameter,
        ))
        self.fields = (
            ("module", "模數 (mm)", defaults.module),
            ("max_diameter", "最大齒輪外廓 (mm)", initial_diameter),
            ("min_ratio", "最低齒比 z", 8),
            ("min_teeth", "最小齒數", 20),
            ("planet_count", "行星輪組數", defaults.planet_count),
        )
        self.values = {}
        for row, (key, label, initial) in enumerate(self.fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=6)
            value = tk.StringVar(form, str(initial))
            self.values[key] = value
            ttk.Entry(form, textvariable=value, width=10, justify="right").grid(
                row=row, column=1, padx=(12, 0), pady=6
            )
        ttk.Button(form, text="搜尋組合", command=self.search).grid(
            row=len(self.fields), column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

        results = ttk.Frame(self)
        results.grid(row=0, column=0, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)
        columns = (
            ("check", "選", 28), ("sun", "太陽", 46), ("planet1", "行星 1", 54),
            ("planet2", "行星 2", 54), ("ring", "齒圈", 46), ("ratio", "齒比 z", 65),
            ("diameter", "外廓 mm", 72), ("count", "幾何上限組數", 96),
        )
        self.table = ttk.Treeview(results, columns=[key for key, _, _ in columns],
                                  show="headings", selectmode="browse")
        for key, label, width in columns:
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=width, anchor="center")
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(results, orient="vertical", command=self.table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind("<<TreeviewSelect>>", self.select_candidate)

        footer = ttk.Frame(self)
        footer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.apply_button = ttk.Button(footer, text="產生齒輪系", command=self.apply_candidate, state="disabled")
        self.apply_button.pack(side="right", padx=(10, 0))
        self.notice = tk.StringVar(self, "輸入條件後按「搜尋組合」。")
        ttk.Label(footer, textvariable=self.notice, wraplength=355, justify="left").pack(side="left")
        ttk.Label(self, text="z 為行星架固定的齒比。齒圈固定、行星架輸出時，減速比為 1 + z。",
                  wraplength=470, foreground="#475569").grid(row=2, column=0, sticky="w", pady=(8, 0))
        for value in self.values.values():
            value.trace_add("write", self.clear_results)

    def clear_results(self, *_args) -> None:
        rows = self.table.get_children()
        if rows:
            self.table.delete(*rows)
        self.candidates = []
        self.checked = None
        self.apply_button.configure(state="disabled")
        self.notice.set("輸入條件後按「搜尋組合」。")

    def search(self) -> None:
        if str(self) in self.master.tabs():
            self.master.select(self)
        self.clear_results()
        arguments = {}
        for key, label, _ in self.fields:
            try:
                value = float(self.values[key].get())
                if key in ("min_teeth", "planet_count"):
                    if not math.isfinite(value) or value <= 0 or not value.is_integer():
                        raise ValueError
                    value = int(value)
            except ValueError:
                kind = "正整數" if key in ("min_teeth", "planet_count") else "數字"
                self.notice.set(f"{label}請輸入{kind}。")
                return
            arguments[key] = value
        try:
            total, self.candidates = find_gear_combinations(self.current_design(), **arguments)
        except ValueError as exc:
            self.notice.set(str(exc))
            return
        for index, candidate in enumerate(self.candidates):
            gears = candidate.gear_set
            self.table.insert("", "end", iid=str(index), values=(
                "☐", gears.sun_teeth, gears.planet1_teeth, gears.planet2_teeth, gears.ring_teeth,
                f"{candidate.ratio:.3f}", f"{candidate.diameter:.2f}", candidate.max_planets,
            ))
        if total:
            shown = f"，顯示前 {len(self.candidates)} 筆" if total > len(self.candidates) else ""
            self.notice.set(f"找到 {total:,} 組{shown}。點選一列後按「產生齒輪系」。")
        else:
            self.notice.set("找不到符合條件的組合。可放寬外廓上限、齒比門檻或行星輪組數。")

    def select_candidate(self, _event=None) -> None:
        if self.checked is not None and self.table.exists(self.checked):
            self.table.set(self.checked, "check", "☐")
        selection = self.table.selection()
        self.checked = selection[0] if selection else None
        if self.checked is not None:
            self.table.set(self.checked, "check", "☑")
        self.apply_button.configure(state="normal" if selection else "disabled")

    def apply_candidate(self) -> None:
        selection = self.table.selection()
        if selection:
            self.apply_design(self.candidates[int(selection[0])].gear_set)


class GearDetailsTab(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent, padding=12)
        self.last_render = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.summary = tk.StringVar(self)
        ttk.Label(self, textvariable=self.summary, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        self.table = ttk.Treeview(self, columns=("parameter", "unit", "value"), show="headings")
        for column, label, width, anchor in (
            ("parameter", "參數", 156, "w"),
            ("unit", "單位", 38, "center"),
            ("value", "數值", 100, "e"),
        ):
            self.table.heading(column, text=label)
            self.table.column(column, width=width, minwidth=width, anchor=anchor)
        self.table.grid(row=1, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(self, orient="vertical", command=self.table.yview)
        vertical.grid(row=1, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=2, column=0, sticky="ew")
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

    def render(self, module: float, gear: Gear, name: str) -> None:
        render_key = (module, gear, name)
        if render_key == self.last_render:
            return
        self.summary.set(f"{name}　模數 {module:g} mm")
        geometry = gear_geometry(module, gear.teeth, internal=gear.internal, settings=gear.settings)
        rows = [
            ("齒數", "齒", gear.teeth),
            ("壓力角", "°", f"{gear.settings.pressure_angle:g}"),
            ("軸孔直徑", "mm", "—" if gear.internal else f"{gear.bore_diameter:.6f}"),
        ]
        rows.extend(
            (label, unit, f"{getattr(geometry, field):.6f}")
            for field, label, unit in GEOMETRY_ROWS
        )

        for item in self.table.get_children():
            self.table.delete(item)
        for row in rows:
            self.table.insert("", "end", values=row)
        self.last_render = render_key


class GearDesignerApp:
    def __init__(self, root: tk.Tk, defaults: GearSet):
        self.root = root
        self.defaults = defaults
        self.gear_set = defaults
        self.gears = make_gears(defaults)
        self.inputs: dict[str, tk.StringVar] = {}
        self.status = tk.StringVar(root, "已載入預設參數。")
        self.rotation = Affine2D()
        self.rotation_timer: str | None = None

        root.title("齒輪設計工具")
        root.geometry("1100x740")
        root.minsize(900, 610)
        style = ttk.Style(root)
        style.configure("Gear.TNotebook.Tab", padding=(10, 7))

        body = ttk.Frame(root, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)
        ttk.Label(body, text="齒輪設計工具", font=("TkDefaultFont", 20, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 14)
        )

        sidebar = ttk.Frame(body)
        sidebar.grid(row=1, column=0, sticky="ns", padx=(0, 14))
        self.forms = ttk.Notebook(sidebar)
        self.forms.pack(fill="x")
        self.search_form = ttk.Frame(self.forms, padding=12)
        self.forms.add(self.search_form, text="尋找組合")
        form = ttk.Frame(self.forms, padding=12)
        self.system_form = form
        self.forms.add(form, text="齒輪系")
        for row, (key, label, attr) in enumerate(FIELDS):
            ttk.Label(form, text=f"{label}  {key}").grid(row=row, column=0, sticky="w", pady=6)
            value = tk.StringVar(form, str(getattr(defaults, attr)))
            value.trace_add("write", self.mark_pending)
            self.inputs[key] = value
            ttk.Entry(form, textvariable=value, width=10, justify="right").grid(
                row=row, column=1, padx=(12, 0), pady=6
            )

        ttk.Button(form, text="更新圖形", command=self.apply).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(14, 6)
        )
        ttk.Button(form, text="還原預設", command=self.reset).grid(
            row=8, column=0, columnspan=2, sticky="ew"
        )
        ttk.Label(
            form,
            text="組合圖的中心距條件\nTr = Ts + Tp1 + Tp2",
            foreground="#475569",
            justify="left",
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.editor = ttk.Frame(self.forms, padding=12)
        self.forms.add(self.editor, text="單顆設計")
        self.build_gear_editor()
        self.forms.select(self.system_form)
        ttk.Label(sidebar, textvariable=self.status, wraplength=250, justify="left").pack(
            anchor="w", padx=8, pady=8
        )

        self.notebook = ttk.Notebook(body, style="Gear.TNotebook")
        self.notebook.grid(row=1, column=1, sticky="nsew")
        self.tabs = {}
        self.system_tabs = {}
        for title, plot, show_phase_warning in (
            ("節圓配置", plot_layout, False),
            ("齒輪系組合", plot_assembly, True),
            ("全組合", partial(plot_assembly, overlay=True), True),
        ):
            tab = PlotTab(self.notebook, plot, show_phase_warning=show_phase_warning)
            self.system_tabs[tab] = title
            self.tabs[str(tab)] = tab
            if plot is plot_assembly:
                self.assembly_tab = tab
        self.single_tab = PlotTab(self.notebook, self.plot_selected_gear)
        self.tabs[str(self.single_tab)] = self.single_tab
        self.single_stats = tk.StringVar(root)
        footer = ttk.Frame(self.single_tab, padding=(8, 4))
        footer.grid(row=2, column=0, sticky="ew")
        self.rotation_button = ttk.Button(footer, text="旋轉預覽", command=self.toggle_rotation)
        self.rotation_button.pack(side="right", padx=(8, 0))
        ttk.Label(footer, textvariable=self.single_stats, justify="left").pack(side="left")
        self.search_tab = GearSearchTab(
            self.notebook, self.search_form, defaults, lambda: self.gear_set, self.apply_candidate
        )
        self.details_tab = GearDetailsTab(self.notebook)
        self.show_form_preview()
        self.notebook.enable_traversal()
        self.notebook.bind("<<NotebookTabChanged>>", self.show_selected)
        self.forms.bind("<<NotebookTabChanged>>", self.show_form_preview)
        root.bind("<Return>", self.apply_active_form)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_selected()

    def build_gear_editor(self) -> None:
        ttk.Label(self.editor, text="選擇齒輪").grid(row=0, column=0, sticky="w", pady=4)
        self.gear_picker = ttk.Combobox(self.editor, values=GEAR_NAMES, state="readonly", width=12)
        self.gear_picker.current(0)
        self.gear_picker.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=4)
        self.gear_picker.bind("<<ComboboxSelected>>", self.select_gear)
        self.module_label = tk.StringVar(self.editor, f"{self.gear_set.module:g} mm（共用）")
        ttk.Label(self.editor, text="模數").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(self.editor, textvariable=self.module_label).grid(row=1, column=1, sticky="e", pady=4)
        ttk.Label(self.editor, text="齒數").grid(row=2, column=0, sticky="w", pady=4)
        self.teeth_entry = ttk.Entry(self.editor, textvariable=self.inputs["Ts"], width=10, justify="right")
        self.teeth_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=4)

        self.profile_vars = []
        for settings in self.defaults.gear_settings:
            variables = {}
            for attr, _label in PROFILE_FIELDS:
                value = getattr(settings, attr)
                variable = tk.StringVar(self.editor, "" if value is None else str(value))
                variable.trace_add("write", self.mark_pending)
                variables[attr] = variable
            self.profile_vars.append(variables)
        self.profile_entries = {}
        for row, (attr, label) in enumerate(PROFILE_FIELDS, start=3):
            ttk.Label(self.editor, text=label).grid(row=row, column=0, sticky="w", pady=4)
            entry = ttk.Entry(self.editor, textvariable=self.profile_vars[0][attr], width=10, justify="right")
            entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=4)
            self.profile_entries[attr] = entry
        ttk.Label(self.editor, text="軸孔留白沿用預設，輸入 0 為實心。", wraplength=220).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Button(self.editor, text="套用到齒輪系", command=self.apply_gear).grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        self.export_format = ttk.Combobox(
            self.editor, values=("PNG", "SVG", "DXF", "STEP"), state="readonly", width=7
        )
        self.export_format.current(0)
        self.export_format.grid(row=11, column=0, sticky="w", pady=(8, 0))
        ttk.Button(self.editor, text="匯出齒輪…", command=self.export_selected_gear).grid(
            row=11, column=1, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

    def show_form_preview(self, _event=None) -> None:
        selected_form = self.forms.select()
        if selected_form == str(self.search_form):
            visible_tabs = {self.search_tab: "搜尋結果"}
            preferred = self.search_tab
        elif selected_form == str(self.editor):
            visible_tabs = {self.single_tab: "單顆預覽", self.details_tab: "詳細參數"}
            preferred = self.single_tab
        else:
            visible_tabs = self.system_tabs
            preferred = None

        current_tabs = self.notebook.tabs()
        visible_paths = {str(tab) for tab in visible_tabs}
        for index, (tab, title) in enumerate(visible_tabs.items()):
            if str(tab) not in current_tabs:
                self.notebook.add(tab, text=title)
            if self.notebook.index(tab) != index:
                self.notebook.insert(index, tab)
        if preferred is not None:
            self.notebook.select(preferred)
        elif self.notebook.select() not in visible_paths:
            self.notebook.select(next(iter(visible_tabs)))
        for tab in current_tabs:
            if tab not in visible_paths:
                self.notebook.forget(tab)

    def select_gear(self, _event=None) -> None:
        index = self.gear_picker.current()
        key, _, _ = FIELDS[index]
        self.teeth_entry.configure(textvariable=self.inputs[key])
        for attr, entry in self.profile_entries.items():
            entry.configure(textvariable=self.profile_vars[index][attr])
        self.profile_entries["bore_diameter"].configure(state="disabled" if index == 3 else "normal")
        self.single_tab.gear_set = None
        if self.notebook.select() != str(self.details_tab):
            self.show_form_preview()
        self.show_selected()

    def mark_pending(self, *_args) -> None:
        self.status.set("按目前頁面的套用按鈕或 Enter 更新。")

    def apply_active_form(self, _event=None) -> None:
        selected = self.forms.select()
        if selected == str(self.search_form):
            self.search_tab.search()
        elif selected == str(self.editor):
            self.apply_gear()
        else:
            self.apply()

    def apply(self, _event=None) -> None:
        values = {}
        for key, label, _attr in FIELDS:
            try:
                values[key] = float(self.inputs[key].get())
            except ValueError:
                self.status.set(f"{label}請輸入數字。仍顯示上次套用的結果。")
                return
        try:
            gear_set = gear_set_from_values(values)
        except ValueError as exc:
            self.status.set(f"{exc}仍顯示上次套用的結果。")
            return

        self.apply_design(replace(gear_set, gear_settings=self.gear_set.gear_settings))

    def apply_gear(self) -> None:
        index = self.gear_picker.current()
        key, _, teeth_attr = FIELDS[index]
        try:
            teeth = float(self.inputs[key].get())
            if not math.isfinite(teeth) or teeth <= 0 or not teeth.is_integer():
                raise ValueError
        except ValueError:
            self.status.set("齒數必須是正整數。")
            return

        values = {}
        for attr, label in PROFILE_FIELDS:
            raw = self.profile_vars[index][attr].get().strip()
            if attr == "bore_diameter" and (index == 3 or not raw):
                continue
            try:
                values[attr] = float(raw)
            except ValueError:
                self.status.set(f"{label}請輸入數字。")
                return
        try:
            settings = GearSettings(**values)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        profiles = list(self.gear_set.gear_settings)
        profiles[index] = settings
        if self.notebook.select() != str(self.details_tab):
            self.show_form_preview()
        self.apply_design(replace(
            self.gear_set, gear_settings=tuple(profiles), **{teeth_attr: int(teeth)}
        ))

    def apply_design(self, gear_set: GearSet) -> None:
        if (gear_set.axle_diameter, gear_set.gear_settings) != (
            self.gear_set.axle_diameter, self.gear_set.gear_settings,
        ):
            self.search_tab.clear_results()
        self.gear_set = gear_set
        self.gears = make_gears(gear_set)
        self.module_label.set(f"{gear_set.module:g} mm（共用）")
        self.show_selected()
        self.status.set("已套用參數。")

    def apply_candidate(self, gear_set: GearSet) -> None:
        for key, _, attr in FIELDS:
            self.inputs[key].set(str(getattr(gear_set, attr)))
        self.forms.select(self.system_form)
        self.show_form_preview()
        self.notebook.select(self.assembly_tab)
        self.apply_design(gear_set)
        self.status.set("已套用搜尋結果。")

    def reset(self) -> None:
        for key, _label, attr in FIELDS:
            self.inputs[key].set(str(getattr(self.defaults, attr)))
        for variables, settings in zip(self.profile_vars, self.defaults.gear_settings, strict=True):
            for attr, variable in variables.items():
                value = getattr(settings, attr)
                variable.set("" if value is None else str(value))
        self.apply_design(self.defaults)

    def show_selected(self, _event=None) -> None:
        selected = self.notebook.select()
        if selected == str(self.search_tab):
            self.stop_rotation()
            return
        if selected == str(self.details_tab):
            self.stop_rotation()
            index = self.gear_picker.current()
            self.details_tab.render(self.gear_set.module, self.gears[index], GEAR_NAMES[index])
            return
        tab = self.tabs[selected]
        if tab is not self.single_tab or tab.gear_set != self.gear_set:
            self.stop_rotation()
        tab.render(self.gear_set, self.gears)
        if tab is self.single_tab:
            self.rotation_button.configure(state="normal" if self.single_stats.get() else "disabled")

    def plot_selected_gear(self, gear_set: GearSet, gears: list[Gear], *, figure: Figure) -> None:
        index = self.gear_picker.current()
        gear = gears[index]
        self.single_stats.set("")
        axes = figure.subplots()
        draw_gear(axes, gear, gear_set.module)
        for line in axes.lines:
            line.set_transform(self.rotation + axes.transData)
        axes.set_title(f"{GEAR_NAMES[index]}（{gear.teeth} 齒）")
        axes.set_xlabel("X (mm)")
        axes.set_ylabel("Y (mm)")
        axes.set_aspect("equal", adjustable="box")
        axes.grid(True)
        geometry = gear_geometry(gear_set.module, gear.teeth, internal=gear.internal, settings=gear.settings)
        self.single_stats.set(
            f"節圓 Ø{geometry.pitch_diameter:.3f}   齒頂圓 Ø{geometry.tip_diameter:.3f}   "
            f"齒根圓 Ø{geometry.root_diameter:.3f} mm\n"
            f"齒厚 {geometry.tooth_thickness:.3f}   齒槽 {geometry.tooth_space:.3f}   "
            f"參考圓角 R{geometry.fillet_radius:.3f} mm"
        )

    def export_selected_gear(self) -> None:
        index = self.gear_picker.current()
        gear = self.gears[index]
        module = self.gear_set.module
        format_name = self.export_format.get()
        extension = f".{format_name.lower()}"
        extensions = (".step", ".stp") if format_name == "STEP" else (extension,)
        self.stop_rotation()

        thickness = outer_diameter = None
        figure = None
        if format_name in ("PNG", "SVG"):
            self.single_tab.render(self.gear_set, self.gears)
            if not self.single_stats.get():
                messagebox.showerror("無法匯出齒輪", self.single_tab.notice.cget("text"), parent=self.root)
                return
            figure = self.single_tab.figure
        elif gear.internal:
            geometry = gear_geometry(module, gear.teeth, internal=True, settings=gear.settings)
            outer_diameter = simpledialog.askfloat(
                "內齒圈外徑", f"輸入外徑 (mm)，須大於齒根圓直徑 {geometry.root_diameter:g} mm。",
                initialvalue=round(geometry.root_diameter + 2 * module, 6),
                minvalue=geometry.root_diameter, parent=self.root,
            )
            if outer_diameter is None:
                return
        if format_name == "STEP":
            thickness = simpledialog.askfloat(
                "齒輪厚度", "輸入齒輪厚度 (mm)。", initialvalue=5.0, minvalue=0, parent=self.root,
            )
            if thickness is None:
                return

        filename = filedialog.asksaveasfilename(
            parent=self.root, title="匯出已套用的齒輪", initialfile=f"{GEAR_NAMES[index]}_{gear.teeth}T{extension}",
            defaultextension=extension, filetypes=[(format_name, " ".join(f"*{ext}" for ext in extensions))],
        )
        if not filename:
            return
        destination = Path(filename)
        try:
            if destination.suffix.lower() not in extensions:
                raise ValueError(f"請使用 {format_name} 對應的副檔名。")
            export_gear(destination, gear, module, figure=figure, thickness=thickness, outer_diameter=outer_diameter)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("無法匯出齒輪", str(exc), parent=self.root)
        else:
            self.status.set(f"已匯出 {destination.name}")

    def toggle_rotation(self) -> None:
        if self.rotation_timer is not None:
            self.stop_rotation()
        else:
            self.rotation_button.configure(text="停止旋轉")
            self.rotate_preview()

    def rotate_preview(self) -> None:
        self.rotation.rotate_deg(4)
        self.single_tab.canvas.draw_idle()
        self.rotation_timer = self.root.after(50, self.rotate_preview)

    def stop_rotation(self) -> None:
        if self.rotation_timer is not None:
            self.root.after_cancel(self.rotation_timer)
            self.rotation_timer = None
            self.rotation.clear()
            self.rotation_button.configure(text="旋轉預覽")
            self.single_tab.canvas.draw_idle()

    def close(self) -> None:
        self.stop_rotation()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        defaults = load_gear_set(DEFAULT_DATA)
    except ValueError as exc:
        root.withdraw()
        messagebox.showerror("無法載入預設參數", str(exc), parent=root)
        root.destroy()
        return

    GearDesignerApp(root, defaults)
    root.mainloop()


if __name__ == "__main__":
    main()
