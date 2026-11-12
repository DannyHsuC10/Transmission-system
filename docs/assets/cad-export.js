import {numberInput, polar, profileSegments, segmentPoint, TAU} from "./gear-model.js";

export function cadCircleRadius(gear, outerDiameter) {
  if (!gear.internal) return gear.bore / 2;
  const diameterLabel = `${gear.name}外徑`;
  const diameter = numberInput(outerDiameter, diameterLabel);
  if (diameter <= gear.geometry.root_diameter) {
    throw new Error(`${diameterLabel}須大於齒根圓直徑 ${gear.geometry.root_diameter.toPrecision(8)} mm。`);
  }
  return diameter / 2;
}

export function writeDxf(gear, outerDiameter) {
  const circle = cadCircleRadius(gear, outerDiameter);
  const vertices = [];
  for (const segment of profileSegments(gear)) {
    if (segment.kind === "flank") {
      for (let i = 0; i < 99; i++) vertices.push([...segmentPoint(segment, i / 99), 0]);
    } else {
      const bulge = segment.kind === "arc" ? Math.tan((segment.a1 - segment.a0) / 4) : 0;
      vertices.push([...segmentPoint(segment, 0), bulge]);
    }
  }
  const lines = [];
  const write = (...pairs) => lines.push(...pairs);
  write(0, "SECTION", 2, "HEADER", 9, "$ACADVER", 1, "AC1024", 9, "$INSUNITS", 70, 4, 0, "ENDSEC");
  write(0, "SECTION", 2, "ENTITIES");
  write(0, "LWPOLYLINE", 5, "100", 100, "AcDbEntity", 8, 0, 100, "AcDbPolyline", 90, vertices.length, 70, 1);
  for (const [x, y, bulge] of vertices) write(10, x, 20, y, 42, bulge);
  if (circle > 0) write(0, "CIRCLE", 5, "101", 100, "AcDbEntity", 8, 0, 100, "AcDbCircle", 10, 0, 20, 0, 30, 0, 40, circle);
  write(0, "ENDSEC", 0, "EOF");
  return lines.join("\r\n") + "\r\n";
}

const flag = (value) => value ? ".T." : ".F.";
const tuple = (values) => `(${values.join(",")})`;
function real(value) {
  if (!Number.isFinite(value)) throw new Error("STEP 幾何尺寸超出可匯出範圍。");
  const [mantissa, exponent] = Number(value.toPrecision(15)).toString().split("e");
  return (mantissa.includes(".") ? mantissa : mantissa + ".") + (exponent == null ? "" : `E${exponent}`);
}

// The radius derivative of the involute polar angle is roll / radius.
// Cubic Hermite pieces share this analytic tangent and use the desktop sample
// locations (every fifth of the 100 preview samples, plus the end point).
function flankControls(segment) {
  const parameters = Array.from({length: 21}, (_, index) => Math.min(1, index * 5 / 99));
  const points = parameters.map((t) => segmentPoint(segment, t));
  const tangents = points.map(([x, y], index) => {
    const dr = segment.r1 - segment.r0;
    const r = segment.r0 + dr * parameters[index];
    const roll = segment.sign * Math.sqrt(Math.max(0, (r / segment.base) ** 2 - 1));
    return [(x - y * roll) * (dr / r), (y + x * roll) * (dr / r)];
  });
  const controls = [points[0]];
  for (let i = 1; i < points.length; i++) {
    const delta = (parameters[i] - parameters[i - 1]) / 3;
    controls.push(points[i - 1].map((v, j) => v + delta * tangents[i - 1][j]));
    controls.push(points[i].map((v, j) => v - delta * tangents[i][j]));
    controls.push(points[i]);
  }
  return {controls, parameters};
}

// AP214 advanced B-rep: shared edges, a closed shell, analytic circles and
// planes, and splines swept along Z. It has no faceted or mesh-only entities.
export function writeStep(gear, outerDiameter, rawThickness) {
  const radius = cadCircleRadius(gear, outerDiameter);
  const thickness = numberInput(rawThickness, "齒輪厚度");
  if (thickness <= 0) throw new Error("STEP 齒輪厚度須大於零。");
  const teeth = [...profileSegments(gear)];
  const circle = radius > 0 ? Array.from({length: 4}, (_, i) => ({
    kind: "arc", radius, a0: i * TAU / 4, a1: (i + 1) * TAU / 4,
  })) : null;
  const entities = [];
  function add(record) {
    const id = `#${entities.length + 1}`;
    entities.push(`${id}=${record};`);
    return id;
  }
  const point = (coordinates) => add(`CARTESIAN_POINT('',${tuple(coordinates.map(real))})`);
  const direction = (coordinates) => add(`DIRECTION('',${tuple(coordinates.map(real))})`);
  const vertex = (coordinates) => add(`VERTEX_POINT('',${point(coordinates)})`);
  const zUp = direction([0, 0, 1]), zDown = direction([0, 0, -1]), xRight = direction([1, 0, 0]);
  const vector = (dir) => add(`VECTOR('',${dir},1.)`);
  const vertical = vector(zUp);
  const axis = (coordinates, normal = zUp, ref = xRight) =>
    add(`AXIS2_PLACEMENT_3D('',${point(coordinates)},${normal},${ref})`);
  const z0 = axis([0, 0, 0]), z1 = axis([0, 0, thickness]);
  const line = (coordinates, dir) => add(`LINE('',${point(coordinates)},${dir})`);
  const plane = (placement) => add(`PLANE('',${placement})`);
  const edge = (start, end, curve) => add(`EDGE_CURVE('',${start},${end},${curve},.T.)`);
  const orient = (ref, forward) => add(`ORIENTED_EDGE('',*,*,${ref},${flag(forward)})`);
  const loop = (edges) => add(`EDGE_LOOP('',${tuple(edges)})`);
  const bound = (ref, outer) => add(`FACE${outer ? "_OUTER" : ""}_BOUND('',${ref},.T.)`);
  const face = (bounds, surface, forward) => add(`ADVANCED_FACE('',${tuple(bounds)},${surface},${flag(forward)})`);
  const spline = ({controls, parameters}, z) => {
    const points = controls.map((coordinates) => point([...coordinates, z]));
    const multiplicities = parameters.map((_, i) => i === 0 || i === parameters.length - 1 ? 4 : 3);
    return add(`B_SPLINE_CURVE_WITH_KNOTS('',3,${tuple(points)},.UNSPECIFIED.,.F.,.F.,${tuple(multiplicities)},${tuple(parameters.map(real))},.UNSPECIFIED.)`);
  };

  const sideFaces = [];
  function walls(segments, outside) {
    const starts = segments.map((segment) => segmentPoint(segment, 0));
    const bottom = starts.map((p) => vertex([...p, 0]));
    const top = starts.map((p) => vertex([...p, thickness]));
    const up = starts.map((p, i) => edge(bottom[i], top[i], line([...p, 0], vertical)));
    const lower = [], upper = [];
    for (const [i, segment] of segments.entries()) {
      const j = (i + 1) % segments.length;
      const p = starts[i];
      let low, high, surface;
      if (segment.kind === "arc") {
        const r = real(segment.radius);
        low = add(`CIRCLE('',${z0},${r})`);
        high = add(`CIRCLE('',${z1},${r})`);
        surface = add(`CYLINDRICAL_SURFACE('',${z0},${r})`);
      } else if (segment.kind === "line") {
        const sign = Math.sign(segment.r1 - segment.r0);
        const tangent = polar(sign, segment.angle);
        const x = direction([...tangent, 0]), outward = direction([tangent[1], -tangent[0], 0]);
        const along = vector(x);
        low = line([...p, 0], along);
        high = line([...p, thickness], along);
        surface = plane(axis([...p, 0], outward, x));
      } else {
        const controls = flankControls(segment);
        low = spline(controls, 0);
        high = spline(controls, thickness);
        surface = add(`SURFACE_OF_LINEAR_EXTRUSION('',${low},${vertical})`);
      }
      lower.push(edge(bottom[i], bottom[j], low));
      upper.push(edge(top[i], top[j], high));
      const edges = [[lower[i], true], [up[j], true], [upper[i], false], [up[i], false]];
      if (!outside) edges.reverse().forEach((entry) => { entry[1] = !entry[1]; });
      sideFaces.push(face([bound(loop(edges.map(([id, dir]) => orient(id, dir))), true)], surface, outside));
    }
    return {lower, upper};
  }

  const outside = walls(gear.internal ? circle : teeth, true);
  const hole = gear.internal ? walls(teeth, false) : circle ? walls(circle, false) : null;
  function cap(edges, holeEdges, up) {
    const boundary = (list, forward, outer) => {
      const ordered = forward ? list : [...list].reverse();
      return bound(loop(ordered.map((ref) => orient(ref, forward))), outer);
    };
    const bounds = [boundary(edges, up, true)];
    if (holeEdges) bounds.push(boundary(holeEdges, !up, false));
    return face(bounds, plane(up ? z1 : axis([0, 0, 0], zDown)), true);
  }
  const shell = add(`CLOSED_SHELL('',${tuple([...sideFaces, cap(outside.lower, hole?.lower, false),
    cap(outside.upper, hole?.upper, true)])})`);
  const solid = add(`MANIFOLD_SOLID_BREP('Gear',${shell})`);

  const lengthUnit = add("(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))");
  const angleUnit = add("(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))");
  const solidAngleUnit = add("(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT())");
  const uncertainty = add(`UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),${lengthUnit},'distance_accuracy_value','')`);
  const geometryContext = add(`(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((${uncertainty})) GLOBAL_UNIT_ASSIGNED_CONTEXT((${lengthUnit},${angleUnit},${solidAngleUnit})) REPRESENTATION_CONTEXT('','3D'))`);
  const representation = add(`ADVANCED_BREP_SHAPE_REPRESENTATION('',(${z0},${solid}),${geometryContext})`);
  const context = add("APPLICATION_CONTEXT('core data for automotive mechanical design processes')");
  add(`APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,${context})`);
  const productContext = add(`PRODUCT_CONTEXT('',${context},'mechanical')`);
  const definitionContext = add(`PRODUCT_DEFINITION_CONTEXT('part definition',${context},'design')`);
  const name = `Gear ${gear.teeth}T`;
  const product = add(`PRODUCT('${name}','${name}','',(${productContext}))`);
  const formation = add(`PRODUCT_DEFINITION_FORMATION('','',${product})`);
  const definition = add(`PRODUCT_DEFINITION('design','',${formation},${definitionContext})`);
  const shape = add(`PRODUCT_DEFINITION_SHAPE('','',${definition})`);
  add(`SHAPE_DEFINITION_REPRESENTATION(${shape},${representation})`);
  add(`PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(${product}))`);

  return [
    "ISO-10303-21;", "HEADER;", "FILE_DESCRIPTION(('Extruded involute gear'),'2;1');",
    `FILE_NAME('gear.step','${new Date().toISOString().slice(0, 19)}',(''),(''),'Gear System Designer','','');`,
    "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));",
    "ENDSEC;", "DATA;", ...entities, "ENDSEC;", "END-ISO-10303-21;", "",
  ].join("\n");
}
