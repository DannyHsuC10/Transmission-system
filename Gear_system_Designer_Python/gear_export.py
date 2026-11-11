"""Export a single designed gear as a drawing or CAD model."""

import math
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

import numpy as np
from matplotlib.figure import Figure
from numpy.typing import NDArray

from gear_system_designer import Gear, gear_curves, gear_geometry


Segment = tuple[str, NDArray[np.float64]]


def ordered_segments(gear: Gear, module: float) -> Iterator[Segment]:
    """Follow the preview segments counterclockwise around the tooth boundary."""
    curves = [
        (color, np.column_stack((x, y)))
        for color, x, y in gear_curves(module, gear.teeth, internal=gear.internal, settings=gear.settings)
        if color != "white"
    ]
    if gear.internal:
        for index in range(0, len(curves), 4):
            tip, root, left, right = curves[index:index + 4]
            yield left[0], left[1][::-1]
            yield tip
            yield right
            yield root
        return

    stride = len(curves) // gear.teeth
    has_connectors = stride == 6
    for index in range(0, len(curves), stride):
        next_index = (index + stride) % len(curves)
        _, right, tip, root = curves[index + stride - 4:index + stride]
        yield root
        if has_connectors:
            yield curves[index + 1]
        yield right
        yield tip
        yield curves[next_index + stride - 4]
        if has_connectors:
            color, points = curves[next_index]
            yield color, points[::-1]


def write_dxf(path: Path, segments: list[Segment], circle_radius: float) -> None:
    try:
        import ezdxf
        from ezdxf import units
    except ImportError as exc:
        raise ValueError("DXF 匯出需要 ezdxf，請先安裝 requirements.txt 中的套件。") from exc

    drawing = ezdxf.new("R2010", units=units.MM)
    model = drawing.modelspace()
    vertices = []
    for color, points in segments:
        if color == "red":
            start = math.atan2(points[0, 1], points[0, 0])
            end = math.atan2(points[-1, 1], points[-1, 0])
            sweep = math.remainder(end - start, math.tau)
            vertices.append((*points[0], math.tan(sweep / 4)))
        elif color == "green":
            vertices.append((*points[0], 0))
        else:
            vertices.extend((x, y, 0) for x, y in points[:-1])
    model.add_lwpolyline(vertices, format="xyb", close=True)
    if circle_radius > 0:
        model.add_circle((0, 0), circle_radius)
    drawing.saveas(path)


def write_step(
    path: Path, segments: list[Segment], circle_radius: float, thickness: float, *, internal: bool
) -> None:
    try:
        from OCP.BRepBuilderAPI import (
            BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire,
        )
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
        from OCP.GC import GC_MakeArcOfCircle
        from OCP.GeomAPI import GeomAPI_Interpolate
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
        from OCP.collections import HArray1_gp_Pnt
        from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pln, gp_Pnt, gp_Vec
    except ImportError as exc:
        raise ValueError("STEP 匯出需要 Open CASCADE 套件，請先安裝 requirements.txt 中的套件。") from exc

    wire_builder = BRepBuilderAPI_MakeWire()
    for color, points in segments:
        start = gp_Pnt(*points[0], 0)
        end = gp_Pnt(*points[-1], 0)
        if color == "red":
            midpoint = gp_Pnt(*points[len(points) // 2], 0)
            edge = BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(start, midpoint, end).Value())
        elif color == "green":
            edge = BRepBuilderAPI_MakeEdge(start, end)
        else:
            samples = np.concatenate((points[:-1:5], points[-1:]))
            interpolation_points = HArray1_gp_Pnt(1, len(samples))
            for index, (x, y) in enumerate(samples, 1):
                interpolation_points.SetValue(index, gp_Pnt(x, y, 0))
            spline = GeomAPI_Interpolate(interpolation_points, False, 1e-7)
            spline.Perform()
            edge = BRepBuilderAPI_MakeEdge(spline.Curve())
        wire_builder.Add(edge.Edge())
        if not wire_builder.IsDone():
            raise ValueError("齒形邊界無法連接成封閉輪廓。")

    teeth = wire_builder.Wire()
    origin, normal = gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)
    circle = None
    if circle_radius > 0:
        circle_edge = BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(origin, normal), circle_radius))
        circle = BRepBuilderAPI_MakeWire(circle_edge.Edge()).Wire()
    outer, hole = (circle, teeth) if internal else (teeth, circle)
    face = BRepBuilderAPI_MakeFace(gp_Pln(origin, normal), outer, True)
    if hole is not None:
        hole.Reverse()
        face.Add(hole)
    solid = BRepPrimAPI_MakePrism(face.Face(), gp_Vec(0, 0, thickness)).Shape()
    if not BRepCheck_Analyzer(solid).IsValid():
        raise ValueError("目前齒形無法建立有效的 STEP 實體。")

    writer = STEPControl_Writer()
    if writer.Transfer(solid, STEPControl_AsIs) != IFSelect_RetDone:
        raise ValueError("無法轉換 STEP 實體。")
    # Write through Python so filenames with non-ASCII characters work on Windows.
    stream = BytesIO()
    if writer.WriteStream(stream) != IFSelect_RetDone:
        raise ValueError("無法寫入 STEP 檔案。")
    path.write_bytes(stream.getvalue())


def export_gear(
    path: Path, gear: Gear, module: float, *, figure: Figure | None = None,
    thickness: float | None = None, outer_diameter: float | None = None,
) -> None:
    suffix = path.suffix.lower()
    if suffix not in {".png", ".svg", ".dxf", ".step", ".stp"}:
        raise ValueError("請選擇 PNG、SVG、DXF 或 STEP 格式。")

    # Replace the destination only once the exporter finishes successfully.
    with NamedTemporaryFile(dir=path.parent, suffix=suffix, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        if suffix in {".png", ".svg"}:
            if figure is None:
                raise ValueError("請先產生單顆齒輪預覽。")
            figure.savefig(temporary, dpi=300)
        else:
            geometry = gear_geometry(module, gear.teeth, internal=gear.internal, settings=gear.settings)
            if gear.internal:
                if (outer_diameter is None or not math.isfinite(outer_diameter)
                        or outer_diameter <= geometry.root_diameter):
                    raise ValueError(f"內齒圈外徑須大於齒根圓直徑 {geometry.root_diameter:g} mm。")
                circle_radius = outer_diameter / 2
            else:
                if gear.bore_diameter >= geometry.root_diameter:
                    raise ValueError("軸孔直徑須小於齒根圓直徑。")
                circle_radius = gear.bore_diameter / 2

            segments = list(ordered_segments(gear, module))
            if suffix == ".dxf":
                write_dxf(temporary, segments, circle_radius)
            else:
                if thickness is None or not math.isfinite(thickness) or thickness <= 0:
                    raise ValueError("STEP 齒輪厚度須大於零。")
                write_step(temporary, segments, circle_radius, thickness, internal=gear.internal)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
