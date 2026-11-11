"""Calculate and plot the compound planetary gear set from the MATLAB example."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.figure import Figure
from numpy.typing import NDArray


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data" / "tooth.csv"
PRESSURE_ANGLE_DEG = 20.0
SAMPLES_PER_CURVE = 100
CJK_FONT_CANDIDATES = (
    "Microsoft JhengHei",
    "Microsoft YaHei",
    "Noto Sans CJK TC",
    "SimHei",
)
AVAILABLE_FONTS = {font.name for font in font_manager.fontManager.ttflist}
for font_name in CJK_FONT_CANDIDATES:
    if font_name in AVAILABLE_FONTS:
        plt.rcParams["font.family"] = font_name
        break
plt.rcParams["axes.unicode_minus"] = False


@dataclass(frozen=True)
class GearSettings:
    addendum_ratio: float = 1.0
    dedendum_ratio: float = 1.25
    space_ratio: float = 1.0
    pressure_angle: float = PRESSURE_ANGLE_DEG
    fillet_ratio: float = 0.236
    bore_diameter: float | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("齒頂倍率", self.addendum_ratio), ("齒根倍率", self.dedendum_ratio),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label}必須大於零。")
        if not 0 < self.space_ratio < 2:
            raise ValueError("齒間倍率必須介於 0 和 2 之間。")
        if not 0 < self.pressure_angle < 90:
            raise ValueError("壓力角必須介於 0° 和 90° 之間。")
        if not math.isfinite(self.fillet_ratio) or self.fillet_ratio < 0:
            raise ValueError("齒根圓角倍率必須是非負數。")
        if self.bore_diameter is not None and (
            not math.isfinite(self.bore_diameter) or self.bore_diameter < 0
        ):
            raise ValueError("軸孔直徑必須是非負數。")


STANDARD_SETTINGS = GearSettings()


@dataclass(frozen=True)
class GearSet:
    sun_teeth: int
    ring_teeth: int
    planet1_teeth: int
    planet2_teeth: int
    module: float
    planet_count: int
    axle_diameter: float
    gear_settings: tuple[GearSettings, ...] = (STANDARD_SETTINGS,) * 4


@dataclass(frozen=True)
class Gear:
    name: str
    teeth: int
    bore_diameter: float
    internal: bool = False
    settings: GearSettings = STANDARD_SETTINGS


@dataclass(frozen=True)
class GearGeometry:
    pitch_diameter: float
    pitch_radius: float
    pitch_circumference: float
    tip_diameter: float
    tip_radius: float
    root_diameter: float
    root_radius: float
    base_diameter: float
    base_radius: float
    addendum: float
    dedendum: float
    tooth_height: float
    working_depth: float
    clearance: float
    circular_pitch: float
    tooth_thickness: float
    tooth_space: float
    fillet_radius: float
    diametral_pitch: float
    pitch_angle: float
    half_pitch_angle: float


@dataclass(frozen=True)
class GearMeshPhases:
    sun: float
    planet1: float
    planet2: float
    ring: float


def load_gear_set(path: Path) -> GearSet:
    """Load named gear parameters from the MATLAB-compatible CSV format."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames or not {"name", "value"}.issubset(reader.fieldnames):
                raise ValueError("CSV 必須包含 name 和 value 欄位。")
            values = {
                row["name"].strip(): float(row["value"])
                for row in reader
                if row.get("name") and row.get("value")
            }
    except OSError as exc:
        raise ValueError(f"無法讀取參數檔：{path}") from exc
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("CSV 必須"):
            raise
        raise ValueError(f"CSV 中的齒輪參數必須是數值：{path}") from exc

    return gear_set_from_values(values)


def gear_set_from_values(values: dict[str, float]) -> GearSet:
    """Validate the named inputs shared by the CSV and the form."""
    required = {"Ts", "Tr", "Tp1", "Tp2", "M", "n", "axle"}
    missing = sorted(required - values.keys())
    if missing:
        raise ValueError(f"CSV 缺少必要參數：{', '.join(missing)}")

    integer_keys = ("Ts", "Tr", "Tp1", "Tp2", "n")
    for key in integer_keys:
        value = values[key]
        if not math.isfinite(value) or value <= 0 or not value.is_integer():
            raise ValueError(f"{key} 必須是正整數。")
    for key in ("M", "axle"):
        if not math.isfinite(values[key]) or values[key] <= 0:
            raise ValueError(f"{key} 必須大於零。")

    return GearSet(
        sun_teeth=int(values["Ts"]),
        ring_teeth=int(values["Tr"]),
        planet1_teeth=int(values["Tp1"]),
        planet2_teeth=int(values["Tp2"]),
        module=values["M"],
        planet_count=int(values["n"]),
        axle_diameter=values["axle"],
    )


def gear_geometry(
    module: float,
    teeth: int,
    *,
    internal: bool = False,
    settings: GearSettings = STANDARD_SETTINGS,
) -> GearGeometry:
    """Calculate external- or internal-gear geometry for one design."""
    pitch_diameter = module * teeth
    pitch_radius = pitch_diameter / 2
    direction = -1 if internal else 1
    addendum = settings.addendum_ratio * module
    dedendum = settings.dedendum_ratio * module
    tip_diameter = pitch_diameter + direction * 2 * addendum
    root_diameter = pitch_diameter - direction * 2 * dedendum
    base_diameter = pitch_diameter * math.cos(math.radians(settings.pressure_angle))
    circular_pitch = module * math.pi
    tooth_space = circular_pitch * settings.space_ratio / 2
    return GearGeometry(
        pitch_diameter=pitch_diameter,
        pitch_radius=pitch_radius,
        pitch_circumference=math.pi * pitch_diameter,
        tip_diameter=tip_diameter,
        tip_radius=tip_diameter / 2,
        root_diameter=root_diameter,
        root_radius=root_diameter / 2,
        base_diameter=base_diameter,
        base_radius=base_diameter / 2,
        addendum=addendum,
        dedendum=dedendum,
        tooth_height=addendum + dedendum,
        working_depth=2 * addendum,
        clearance=dedendum - addendum,
        circular_pitch=circular_pitch,
        tooth_thickness=circular_pitch - tooth_space,
        tooth_space=tooth_space,
        fillet_radius=settings.fillet_ratio * module,
        diametral_pitch=2.54 / module,
        pitch_angle=2 * math.pi / teeth,
        half_pitch_angle=math.pi / teeth,
    )


def make_gears(gear_set: GearSet) -> list[Gear]:
    roles = (
        ("太陽齒輪", gear_set.sun_teeth, False),
        ("行星齒輪", gear_set.planet1_teeth, False),
        ("行星齒輪2", gear_set.planet2_teeth, False),
        ("內齒輪", gear_set.ring_teeth, True),
    )
    gears = []
    for (name, teeth, internal), settings in zip(roles, gear_set.gear_settings, strict=True):
        bore = gear_set.axle_diameter if settings.bore_diameter is None else settings.bore_diameter
        if internal:
            bore = gear_geometry(gear_set.module, teeth, internal=True, settings=settings).tip_diameter
        gears.append(Gear(name, teeth, bore, internal=internal, settings=settings))
    return gears


def print_calculations(gear_set: GearSet, gears: list[Gear], output: TextIO) -> None:
    print(
        f"行星齒輪數量: {gear_set.planet_count}, 模數: {gear_set.module:g} mm",
        file=output,
    )
    for gear in gears:
        values = gear_geometry(
            gear_set.module, gear.teeth, internal=gear.internal, settings=gear.settings
        )
        print(
            f"\n齒輪: {gear.name} (齒數: {gear.teeth}, 壓力角: {gear.settings.pressure_angle:g}°)",
            file=output,
        )
        print(
            f"節徑: {values.pitch_diameter:.6f}, "
            f"節圓半徑: {values.pitch_radius:.6f}, "
            f"節圓周長: {values.pitch_circumference:.6f}",
            file=output,
        )
        print(
            f"齒頂圓直徑: {values.tip_diameter:.6f}, "
            f"齒頂圓半徑: {values.tip_radius:.6f}",
            file=output,
        )
        print(
            f"齒根圓直徑: {values.root_diameter:.6f}, "
            f"齒根圓半徑: {values.root_radius:.6f}",
            file=output,
        )
        print(
            f"基圓直徑: {values.base_diameter:.6f}, "
            f"基圓半徑: {values.base_radius:.6f}",
            file=output,
        )
        print(
            f"齒頂: {values.addendum:.6f}, 齒根: {values.dedendum:.6f}, "
            f"齒高: {values.tooth_height:.6f}",
            file=output,
        )
        print(
            f"工作深度: {values.working_depth:.6f}, "
            f"間隙: {values.clearance:.6f}, "
            f"周節: {values.circular_pitch:.6f}",
            file=output,
        )
        print(
            f"齒厚: {values.tooth_thickness:.6f}, "
            f"齒間: {values.tooth_space:.6f}, "
            f"齒根圓角半徑: {values.fillet_radius:.6f}",
            file=output,
        )
        print(
            f"徑節: {values.diametral_pitch:.6f}, "
            f"周節角度: {values.pitch_angle:.6f} rad, "
            f"半周節角度: {values.half_pitch_angle:.6f} rad",
            file=output,
        )
        print("." * 39, file=output)


def mesh_center_distances(gear_set: GearSet) -> tuple[float, float]:
    return (
        (gear_set.sun_teeth + gear_set.planet1_teeth) * gear_set.module / 2,
        (gear_set.ring_teeth - gear_set.planet2_teeth) * gear_set.module / 2,
    )


def print_mesh_phases(gear_set: GearSet, output: TextIO) -> None:
    phases = gear_mesh_phases(gear_set)
    external_center_distance, internal_center_distance = mesh_center_distances(gear_set)
    print("\n嚙合相位校正:", file=output)
    print(
        f"太陽輪-行星輪1 / 行星輪2-內齒圈中心距: "
        f"{external_center_distance:.6f} / {internal_center_distance:.6f} mm",
        file=output,
    )
    print(
        "齒形相位 (deg): "
        f"太陽輪 {math.degrees(phases.sun):.6f}, "
        f"行星輪1 {math.degrees(phases.planet1):.6f}, "
        f"行星輪2 {math.degrees(phases.planet2):.6f}, "
        f"內齒圈 {math.degrees(phases.ring):.6f}",
        file=output,
    )
    warning = mesh_phase_warning(gear_set)
    if warning:
        print(warning, file=output)


def planet_phase_step(sun: int, planet1: int, planet2: int, ring: int, count: int) -> float | None:
    """Extra rotation per planet station, shared by both wheels of a compound planet."""
    common = math.gcd(planet1, planet2)
    numerator = sun * planet2 + ring * planet1
    if numerator % (count * common):
        return None
    period = planet1 // common
    # Choose a whole number of first-planet tooth pitches that also aligns the second wheel.
    tooth_steps = -(numerator // (count * common)) * pow(planet2 // common, -1, period)
    turns_numerator = (sun + count * tooth_steps) % (count * period)
    return math.tau * turns_numerator / (count * planet1)


def mesh_profile_warnings(settings: tuple[GearSettings, ...]) -> list[str]:
    warnings = []
    for first_index, second_index, label in (
        (0, 1, "太陽輪與第一行星輪"), (2, 3, "第二行星輪與內齒圈"),
    ):
        first = settings[first_index]
        second = settings[second_index]
        if first.space_ratio + second.space_ratio < 2 - 1e-9:
            warnings.append(f"{label}的節圓齒厚總和大於周節。")
        if (
            first.addendum_ratio > second.dedendum_ratio
            or second.addendum_ratio > first.dedendum_ratio
        ):
            warnings.append(f"{label}的齒頂超過配對齒輪的齒根深度。")
    return warnings


def mesh_phase_warning(gear_set: GearSet) -> str | None:
    warnings = mesh_profile_warnings(gear_set.gear_settings)
    if planet_phase_step(
        gear_set.sun_teeth, gear_set.planet1_teeth, gear_set.planet2_teeth,
        gear_set.ring_teeth, gear_set.planet_count,
    ) is None:
        warnings.insert(0, "此齒數與行星組數無法讓所有等角分布的行星同時嚙合。圖中以第一組對齒。")
    return "\n".join(warnings) or None


def involute_angle(radius: NDArray[np.float64], base_radius: float) -> NDArray[np.float64]:
    """Return the polar angle of the involute from its start on the base circle."""
    angles = np.full_like(radius, np.nan, dtype=float)
    valid = radius >= base_radius
    roll = np.sqrt((radius[valid] / base_radius) ** 2 - 1)
    angles[valid] = roll - np.arctan(roll)
    return angles


def external_tooth_center_offset(
    module: float, teeth: int, *, settings: GearSettings = STANDARD_SETTINGS
) -> float:
    """Return one tooth's angular center at its pitch circle."""
    geometry = gear_geometry(module, teeth, settings=settings)
    involute_at_pitch = float(
        involute_angle(np.array([geometry.pitch_radius]), geometry.base_radius)[0]
    )
    # The first tooth sits between the right flank and the next left flank.
    space_angle = geometry.tooth_space / geometry.pitch_radius
    return (geometry.pitch_angle + space_angle) / 2 - involute_at_pitch


def gear_mesh_phases(gear_set: GearSet) -> GearMeshPhases:
    """Set tooth/gap centers on the sun and ring contact lines for planet 0."""
    module = gear_set.module
    sun_geometry = gear_geometry(module, gear_set.sun_teeth)
    ring_geometry = gear_geometry(module, gear_set.ring_teeth, internal=True)
    external_center_distance, internal_center_distance = mesh_center_distances(gear_set)
    if not math.isclose(
        external_center_distance,
        internal_center_distance,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ValueError(
            "無法校正嚙合：太陽輪/第一行星輪與第二行星輪/內齒圈"
            "的節圓中心距不一致。"
        )
    validate_mesh_pressure_angles(gear_set.gear_settings)
    sun, planet1, planet2, _ = gear_set.gear_settings
    return GearMeshPhases(
        sun=-(external_tooth_center_offset(module, gear_set.sun_teeth, settings=sun)
             + sun_geometry.half_pitch_angle),
        planet1=math.pi - external_tooth_center_offset(module, gear_set.planet1_teeth, settings=planet1),
        planet2=-external_tooth_center_offset(module, gear_set.planet2_teeth, settings=planet2),
        ring=-ring_geometry.half_pitch_angle,
    )


def validate_mesh_pressure_angles(settings: tuple[GearSettings, ...]) -> None:
    sun, planet1, planet2, ring = settings
    if not math.isclose(sun.pressure_angle, planet1.pressure_angle):
        raise ValueError("太陽輪與第一行星輪的壓力角須相同才能嚙合。")
    if not math.isclose(planet2.pressure_angle, ring.pressure_angle):
        raise ValueError("第二行星輪與內齒圈的壓力角須相同才能嚙合。")


def validate_gear_profile(values: GearGeometry, *, internal: bool) -> float:
    rp, rb = values.pitch_radius, values.base_radius
    rt, rr = values.tip_radius, values.root_radius
    if internal and rt < rb:
        raise ValueError("內齒輪齒頂圓半徑小於基圓半徑，無法產生有效漸開線。")
    if rr <= 0:
        raise ValueError("齒根圓半徑須大於零，請調整齒數或齒根倍率。")

    start = rt if internal else max(rr, rb)
    end = rr if internal else rt
    at_pitch, at_start, at_end = involute_angle(np.array([rp, start, end]), rb)
    if internal:
        half_width = values.tooth_thickness / (2 * rp)
        if half_width + at_start - at_pitch <= 0 or half_width + at_end - at_pitch >= values.half_pitch_angle:
            raise ValueError("內齒輪的齒面交疊，請調整齒間、齒頂或齒根倍率。")
    else:
        base_gap = values.tooth_space / rp - 2 * at_pitch
        if base_gap + 2 * at_start <= 0 or base_gap + 2 * at_end >= values.pitch_angle:
            raise ValueError("外齒輪的齒面交疊，請調整齒間、齒頂或齒根倍率。")
    return float(at_pitch)


def gear_curves(
    module: float,
    teeth: int,
    offset: float = 0.0,
    *,
    internal: bool = False,
    settings: GearSettings = STANDARD_SETTINGS,
) -> list[tuple[str, NDArray[np.float64], NDArray[np.float64]]]:
    """Generate line segments for one external or internal involute gear."""
    values = gear_geometry(module, teeth, internal=internal, settings=settings)
    rp, rb = values.pitch_radius, values.base_radius
    rt, rr = values.tip_radius, values.root_radius
    pitch_angle = values.pitch_angle
    involute_at_pitch = validate_gear_profile(values, internal=internal)
    curves = []

    if internal:
        radii = np.linspace(rt, rr, SAMPLES_PER_CURVE)
        # An internal tooth thickens outward, from its tip to its root.
        half_widths = values.tooth_thickness / (2 * rp) + involute_angle(radii, rb) - involute_at_pitch
        tip_half_width, root_half_width = half_widths[0], half_widths[-1]
        for tooth_index in range(teeth):
            rotation = pitch_angle * tooth_index + offset

            tip_angles = np.linspace(
                rotation - tip_half_width, rotation + tip_half_width, SAMPLES_PER_CURVE
            )
            curves.append(
                ("red", rt * np.cos(tip_angles), rt * np.sin(tip_angles))
            )

            root_angles = np.linspace(
                rotation + root_half_width,
                rotation + pitch_angle - root_half_width,
                SAMPLES_PER_CURVE,
            )
            curves.append(
                ("red", rr * np.cos(root_angles), rr * np.sin(root_angles))
            )

            left_angles = rotation - half_widths
            right_angles = rotation + half_widths
            curves.append(
                ("blue", radii * np.cos(left_angles), radii * np.sin(left_angles))
            )
            curves.append(
                ("blue", radii * np.cos(right_angles), radii * np.sin(right_angles))
            )

        bore_radius = rt
    else:
        base_gap = values.tooth_space / rp - 2 * involute_at_pitch
        radii = np.linspace(max(rr, rb), rt, SAMPLES_PER_CURVE)
        flank_angles = involute_angle(radii, rb)
        start_angle, tip_angle = flank_angles[0], flank_angles[-1]
        for tooth_index in range(teeth):
            rotation = pitch_angle * tooth_index + offset
            if rb > rr:
                root_connector = np.linspace(rr, rb, SAMPLES_PER_CURVE)
                for angle in (rotation, rotation + base_gap):
                    curves.append(
                        (
                            "green",
                            root_connector * np.cos(angle),
                            root_connector * np.sin(angle),
                        )
                    )

            theta = rotation - flank_angles[::-1]
            curves.append(("blue", radii[::-1] * np.cos(theta), radii[::-1] * np.sin(theta)))

            theta = rotation + base_gap + flank_angles
            curves.append(("blue", radii * np.cos(theta), radii * np.sin(theta)))

            theta = rotation + np.linspace(
                base_gap + tip_angle, pitch_angle - tip_angle, SAMPLES_PER_CURVE
            )
            curves.append(("red", rt * np.cos(theta), rt * np.sin(theta)))

            theta = rotation + np.linspace(
                -start_angle, base_gap + start_angle, SAMPLES_PER_CURVE
            )
            curves.append(("red", rr * np.cos(theta), rr * np.sin(theta)))
        bore_radius = 1.0

    bore_theta = np.linspace(0, 2 * math.pi, 200)
    curves.append(
        ("white", bore_radius * np.cos(bore_theta), bore_radius * np.sin(bore_theta))
    )
    return curves


def draw_gear(
    axes: plt.Axes,
    gear: Gear,
    module: float,
    center: tuple[float, float] = (0.0, 0.0),
    offset: float = 0.0,
    *,
    internal: bool = False,
) -> None:
    """Draw the gear outline and its bore on the given axes."""
    center_x, center_y = center
    is_internal = gear.internal or internal
    if not is_internal and gear.settings.bore_diameter is not None:
        root_diameter = gear_geometry(module, gear.teeth, settings=gear.settings).root_diameter
        if gear.bore_diameter >= root_diameter:
            raise ValueError(f"{gear.name}的軸孔直徑須小於齒根圓直徑。")
    for color, x, y in gear_curves(
        module, gear.teeth, offset, internal=is_internal, settings=gear.settings,
    ):
        if color == "white":
            if is_internal or gear.bore_diameter == 0:
                continue
            radius = gear.bore_diameter / 2
            theta = np.linspace(0, 2 * math.pi, 200)
            x = radius * np.cos(theta)
            y = radius * np.sin(theta)
            color = "0.35"
        axes.plot(x + center_x, y + center_y, color=color, linewidth=0.65)


def gear_centers(gear_set: GearSet) -> list[tuple[float, float, float]]:
    """Return angular positions and centers following the MATLAB layout."""
    sun_radius = gear_geometry(gear_set.module, gear_set.sun_teeth).pitch_radius
    planet_radius = gear_geometry(gear_set.module, gear_set.planet1_teeth).pitch_radius
    center_distance = sun_radius + planet_radius
    return [
        (
            index * 2 * math.pi / gear_set.planet_count,
            center_distance * math.cos(index * 2 * math.pi / gear_set.planet_count),
            center_distance * math.sin(index * 2 * math.pi / gear_set.planet_count),
        )
        for index in range(gear_set.planet_count)
    ]


def plot_layout(
    gear_set: GearSet, gears: list[Gear], *, figure: Figure | None = None
) -> Figure:
    fig = figure if figure is not None else plt.figure(figsize=(8, 8))
    axes = fig.subplots()
    sun = gears[0]
    planet1 = gears[1]
    planet2 = gears[2]
    ring = gears[3]
    for gear, center, color in (
        (sun, (0.0, 0.0), "tab:blue"),
        (ring, (0.0, 0.0), "tab:green"),
    ):
        radius = gear_geometry(gear_set.module, gear.teeth).pitch_radius
        axes.add_patch(
            plt.Circle(center, radius, fill=False, color=color, linewidth=1.5)
        )
    planet1_radius = gear_geometry(gear_set.module, planet1.teeth).pitch_radius
    planet2_radius = gear_geometry(gear_set.module, planet2.teeth).pitch_radius
    centers = gear_centers(gear_set)
    for _, x, y in centers:
        axes.add_patch(
            plt.Circle((x, y), planet1_radius, fill=False, color="tab:red", linewidth=1.2)
        )
        axes.add_patch(
            plt.Circle(
                (x, y),
                planet2_radius,
                fill=False,
                color="tab:orange",
                linewidth=1.0,
            )
        )
    ring_radius = gear_geometry(gear_set.module, ring.teeth).pitch_radius
    extent = max(
        ring_radius,
        *(
            math.hypot(x, y) + max(planet1_radius, planet2_radius)
            for _, x, y in centers
        ),
    )
    extent *= 1.05
    axes.set_xlim(-extent, extent)
    axes.set_ylim(-extent, extent)
    axes.set_title("行星齒輪系節圓配置圖")
    axes.set_xlabel("X (mm)")
    axes.set_ylabel("Y (mm)")
    axes.grid(True)
    axes.set_aspect("equal", adjustable="box")
    return fig


def plot_individual_gears(
    gear_set: GearSet, gears: list[Gear], *, figure: Figure | None = None
) -> Figure:
    fig = figure if figure is not None else plt.figure(figsize=(10, 10))
    axes_array = fig.subplots(2, 2)
    for axes, gear in zip(axes_array.flat, gears):
        draw_gear(axes, gear, gear_set.module)
        axes.set_title(f"{gear.name} ({gear.teeth} 齒)")
        axes.set_aspect("equal", adjustable="datalim")
        axes.grid(True)
    fig.suptitle("各齒輪齒形")
    if figure is None:
        fig.tight_layout()
    return fig


def plot_assembly(
    gear_set: GearSet,
    gears: list[Gear],
    *,
    figure: Figure | None = None,
    overlay: bool = False,
) -> Figure:
    phases = gear_mesh_phases(gear_set)
    size = (10, 10) if overlay else (14, 7)
    fig = figure if figure is not None else plt.figure(figsize=size, layout="constrained")
    if overlay:
        external_axes = internal_axes = fig.subplots()
        panels = ((external_axes, "齒輪系全組合（兩層軸向投影）"),)
    else:
        external_axes, internal_axes = fig.subplots(1, 2)
        panels = (
            (external_axes, "第一層：太陽輪／第一行星輪"),
            (internal_axes, "第二層：第二行星輪／內齒圈"),
        )
    draw_gear(external_axes, gears[0], gear_set.module, offset=phases.sun)
    phase_step = planet_phase_step(
        gear_set.sun_teeth, gear_set.planet1_teeth, gear_set.planet2_teeth,
        gear_set.ring_teeth, gear_set.planet_count,
    ) or 0.0
    for index, (angle, center_x, center_y) in enumerate(gear_centers(gear_set)):
        rotation = angle + index * phase_step
        draw_gear(
            external_axes,
            gears[1],
            gear_set.module,
            (center_x, center_y),
            rotation + phases.planet1,
        )
        draw_gear(
            internal_axes,
            gears[2],
            gear_set.module,
            (center_x, center_y),
            rotation + phases.planet2,
        )
    draw_gear(
        internal_axes,
        gears[3],
        gear_set.module,
        offset=phases.ring,
        internal=True,
    )
    for axes, title in panels:
        axes.set_title(title)
        axes.set_xlabel("X (mm)")
        axes.set_ylabel("Y (mm)")
        axes.grid(True)
        axes.set_aspect("equal", adjustable="box")
    return fig


def show_figures() -> None:
    if plt.get_backend().lower() != "agg":
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="行星齒輪系幾何計算與繪圖工具")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="齒輪參數 CSV")
    parser.add_argument("--save-dir", type=Path, help="可選：儲存三張結果圖的資料夾")
    args = parser.parse_args()

    gear_set = load_gear_set(args.data)
    gears = make_gears(gear_set)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print_calculations(gear_set, gears, output=sys.stdout)
    print_mesh_phases(gear_set, output=sys.stdout)

    figures = [
        ("gear_layout.png", plot_layout(gear_set, gears)),
        ("gear_profiles.png", plot_individual_gears(gear_set, gears)),
        ("gear_assembly.png", plot_assembly(gear_set, gears)),
    ]
    if args.save_dir:
        args.save_dir.mkdir(parents=True, exist_ok=True)
        for filename, figure in figures:
            figure.savefig(args.save_dir / filename, dpi=180, bbox_inches="tight")
    show_figures()


if __name__ == "__main__":
    main()
