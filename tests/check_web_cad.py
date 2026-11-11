"""Read browser CAD exports with the same libraries used by the Python app."""

from dataclasses import replace
from io import BytesIO, StringIO
import json
import math
from pathlib import Path
import subprocess
import sys

import ezdxf
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Gear_system_Designer_Python"))

from gear_export import ordered_segments, write_step
from gear_system_designer import DEFAULT_DATA, load_gear_set, make_gears


class MemoryFile:
    def write_bytes(self, content):
        self.content = content


def step_volume(content):
    reader = STEPControl_Reader()
    assert reader.ReadStream("gear.step", BytesIO(content)) == IFSelect_RetDone
    assert reader.TransferRoots() == 1
    shape = reader.OneShape()
    solids = TopExp_Explorer(shape, TopAbs_SOLID)
    assert solids.More() and BRepCheck_Analyzer(shape).IsValid()
    solids.Next()
    assert not solids.More()
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties)
    assert properties.Mass() > 0
    assert math.isclose(properties.CentreOfMass().Z(), 2.5, abs_tol=1e-7)
    return properties.Mass()


def main():
    exports = subprocess.check_output(
        ["node", "--input-type=module", "-e", """
import {defaultDesign, makeGears} from "./docs/assets/gear-model.js";
import {writeStep, writeDxf} from "./docs/assets/cad-export.js";
const gears = makeGears(defaultDesign());
process.stdout.write(JSON.stringify([...gears, {...gears[0], bore: 0}].map(gear => ({
  dxf: writeDxf(gear, 85.2), step: writeStep(gear, 85.2, 5),
}))));
"""],
        cwd=ROOT,
    )
    design = load_gear_set(DEFAULT_DATA)
    gears = make_gears(design)
    gears.append(replace(gears[0], bore_diameter=0))
    for gear, files in zip(gears, json.loads(exports), strict=True):
        radius = 42.6 if gear.internal else gear.bore_diameter / 2
        dxf = ezdxf.read(StringIO(files["dxf"], newline=None))
        assert dxf.units == ezdxf.units.MM and not dxf.audit().errors
        outline, *circles = list(dxf.modelspace())
        assert outline.dxftype() == "LWPOLYLINE" and outline.closed
        assert len(circles) == int(radius > 0)
        if circles:
            assert circles[0].dxftype() == "CIRCLE"
            assert math.isclose(circles[0].dxf.radius, radius)
        assert sum(vertex[-1] != 0 for vertex in outline.get_points("xyb")) == 2 * gear.teeth

        native = MemoryFile()
        write_step(native, list(ordered_segments(gear, design.module)), radius, 5, internal=gear.internal)
        web_volume, native_volume = step_volume(files["step"].encode("ascii")), step_volume(native.content)
        assert math.isclose(web_volume, native_volume, rel_tol=1e-4), (web_volume, native_volume)
    print("Verified closed DXF profiles and valid STEP solids for four gears and a solid sun gear.")


if __name__ == "__main__":
    main()
