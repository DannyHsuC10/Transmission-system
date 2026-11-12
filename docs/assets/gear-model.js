// Browser port of gear_system_designer.py and gear_search.py.
export const TAU = 2 * Math.PI;
export const RAD = Math.PI / 180;
export const GEAR_NAMES = ["太陽輪", "第一行星輪", "第二行星輪", "內齒輪 (內齒環)"];
export const TEETH_KEYS = ["Ts", "Tp1", "Tp2", "Tr"];
export const SYSTEM_FIELDS = [
  ["Ts", "太陽輪齒數", "齒"], ["Tp1", "第一行星輪齒數", "齒"],
  ["Tp2", "第二行星輪齒數", "齒"], ["Tr", `${GEAR_NAMES[3]}齒數`, "齒"],
  ["M", "模數", "mm"], ["n", "行星輪組數", "組"], ["axle", "預設軸孔", "mm"],
];
export const PROFILE_FIELDS = [
  ["addendum_ratio", "齒頂倍率"], ["dedendum_ratio", "齒根倍率"],
  ["space_ratio", "齒間倍率"], ["pressure_angle", "壓力角", "°"],
  ["fillet_ratio", "齒根圓角倍率（參考）"], ["bore_diameter", "軸孔直徑", "mm"],
];
export const GEOMETRY_ROWS = [
  ["pitch_diameter", "節圓直徑（節徑）", "mm"],
  ["pitch_radius", "節圓半徑", "mm"],
  ["pitch_circumference", "節圓周長", "mm"],
  ["tip_diameter", "齒頂圓直徑", "mm"], ["tip_radius", "齒頂圓半徑", "mm"],
  ["root_diameter", "齒根圓直徑", "mm"], ["root_radius", "齒根圓半徑", "mm"],
  ["base_diameter", "基圓直徑", "mm"], ["base_radius", "基圓半徑", "mm"],
  ["addendum", "齒頂高", "mm"], ["dedendum", "齒根高", "mm"], ["tooth_height", "齒高", "mm"],
  ["working_depth", "工作深度", "mm"], ["clearance", "齒輪間隙", "mm"],
  ["circular_pitch", "周節", "mm"], ["tooth_thickness", "節圓齒厚", "mm"],
  ["tooth_space", "節圓齒間", "mm"], ["fillet_radius", "齒根圓角半徑（參考）", "mm"],
  ["diametral_pitch", "徑節（MATLAB 2.54/M）", ""],
  ["pitch_angle", "周節角度", "rad"], ["half_pitch_angle", "半周節角度", "rad"],
];
export const STANDARD_SETTINGS = Object.freeze({
  addendum_ratio: 1, dedendum_ratio: 1.25, space_ratio: 1, pressure_angle: 20,
  fillet_ratio: 0.236, bore_diameter: null,
});
const DEFAULT_VALUES = Object.freeze({Ts: 21, Tp1: 57, Tp2: 24, Tr: 102, M: 0.8, n: 3, axle: 10});
const EPS = 1e-9;
// Keep the browser responsive and all integer phase calculations exact.
export const MAX_TEETH = 2000;
export const MAX_PLANETS = 100;

export function defaultDesign() {
  return {...DEFAULT_VALUES, profiles: Array.from({length: 4}, () => ({...STANDARD_SETTINGS}))};
}

export function numberInput(raw, label) {
  if (typeof raw === "string" && /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw.trim())) {
    raw = Number(raw);
  }
  if (!Number.isFinite(raw)) throw new Error(`${label}請輸入有效數字。`);
  return raw;
}

function positive(value, label) {
  if (value <= 0) throw new Error(`${label}必須大於零。`);
  return value;
}

function boundedInteger(value, label, max) {
  if (!Number.isSafeInteger(value) || value < 1 || value > max) {
    throw new Error(`${label}須為 1 至 ${max} 的整數。`);
  }
  return value;
}

export function readSystemValues(values) {
  const parsed = {};
  for (const [key, label] of SYSTEM_FIELDS) {
    const value = numberInput(values[key], label);
    parsed[key] = key === "M" || key === "axle" ? positive(value, label)
      : boundedInteger(value, label, key === "n" ? MAX_PLANETS : MAX_TEETH);
  }
  return parsed;
}

export function readProfileValues(values, internal) {
  const settings = {};
  for (const [key, label] of PROFILE_FIELDS) {
    const raw = values[key];
    if (key === "bore_diameter" && (internal || raw == null || String(raw).trim() === "")) {
      settings[key] = null;
    } else {
      settings[key] = numberInput(raw, label);
    }
  }
  positive(settings.addendum_ratio, "齒頂倍率");
  positive(settings.dedendum_ratio, "齒根倍率");
  if (!(settings.space_ratio > 0 && settings.space_ratio < 2)) {
    throw new Error("齒間倍率必須大於 0 且小於 2。");
  }
  if (!(settings.pressure_angle > 0 && settings.pressure_angle < 90)) {
    throw new Error("壓力角必須大於 0° 且小於 90°。");
  }
  if (settings.fillet_ratio < 0 || settings.bore_diameter < 0) {
    throw new Error("參考圓角倍率及軸孔直徑須為非負數。");
  }
  return settings;
}

export function readTeeth(raw) {
  return boundedInteger(numberInput(raw, "齒數"), "齒數", MAX_TEETH);
}

// CSV format shared with the desktop CLI, including quoted cells and a UTF-8 BOM.
export function readGearCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  const input = text.replace(/^\uFEFF/, "");
  for (let index = 0; index < input.length; index++) {
    const char = input[index];
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') {
        cell += '"';
        index++;
      } else if (char === '"') quoted = false;
      else cell += char;
    } else if (char === '"' && !cell) {
      quoted = true;
    } else if (char === "," || char === "\n" || char === "\r") {
      row.push(cell);
      cell = "";
      if (char === ",") continue;
      if (char === "\r" && input[index + 1] === "\n") index++;
      rows.push(row);
      row = [];
    } else cell += char;
  }
  if (quoted) throw new Error("CSV 有未關閉的引號。");
  if (row.length || cell) rows.push([...row, cell]);
  const headers = rows.shift()?.map((field) => field.trim()) ?? [];
  const nameColumn = headers.indexOf("name"), valueColumn = headers.indexOf("value");
  if (nameColumn < 0 || valueColumn < 0) throw new Error("CSV 必須包含 name 和 value 欄位。");
  const values = new Map(rows.map((fields) => [fields[nameColumn]?.trim(), fields[valueColumn]]));
  const missing = SYSTEM_FIELDS.map(([key]) => key).filter((key) => !values.has(key));
  if (missing.length) throw new Error(`CSV 缺少必要參數：${missing.join("、")}。`);
  return readSystemValues(Object.fromEntries(values));
}

export function gearGeometry(module, teeth, internal = false, settings = STANDARD_SETTINGS) {
  const pitch_diameter = module * teeth;
  const pitch_radius = pitch_diameter / 2;
  const direction = internal ? -1 : 1;
  const addendum = settings.addendum_ratio * module;
  const dedendum = settings.dedendum_ratio * module;
  const tip_diameter = pitch_diameter + direction * 2 * addendum;
  const root_diameter = pitch_diameter - direction * 2 * dedendum;
  const base_diameter = pitch_diameter * Math.cos(settings.pressure_angle * RAD);
  const circular_pitch = module * Math.PI;
  const tooth_space = circular_pitch * settings.space_ratio / 2;
  return {
    pitch_diameter, pitch_radius, pitch_circumference: Math.PI * pitch_diameter,
    tip_diameter, tip_radius: tip_diameter / 2, root_diameter, root_radius: root_diameter / 2,
    base_diameter, base_radius: base_diameter / 2, addendum, dedendum,
    tooth_height: addendum + dedendum, working_depth: 2 * addendum, clearance: dedendum - addendum,
    circular_pitch, tooth_thickness: circular_pitch - tooth_space, tooth_space,
    fillet_radius: settings.fillet_ratio * module, diametral_pitch: 2.54 / module,
    pitch_angle: TAU / teeth, half_pitch_angle: Math.PI / teeth,
  };
}

export function makeGears(design) {
  return TEETH_KEYS.map((key, role) => {
    const internal = role === 3;
    const teeth = design[key], settings = design.profiles[role];
    const geometry = gearGeometry(design.M, teeth, internal, settings);
    if (!Object.values(geometry).every(Number.isFinite) || !(geometry.pitch_radius > 0)) {
      throw new Error("幾何尺寸超出可計算範圍，請調整模數與齒形設定。");
    }
    return {
      name: GEAR_NAMES[role], role, internal, teeth, settings, geometry,
      bore: internal ? 0 : settings.bore_diameter ?? design.axle,
    };
  });
}

export function centerDistances({Ts, Tp1, Tp2, Tr, M}) {
  return [(Ts + Tp1) * M / 2, (Tr - Tp2) * M / 2];
}

export function gearRatio({Ts, Tp1, Tp2, Tr}) {
  return (Tp1 * Tr) / (Ts * Tp2);
}

export function fixedCarrierSpeedRatios(design) {
  // External mesh reverses direction. The two planet wheels share a shaft,
  // and the internal mesh keeps the direction of that shaft.
  const planet = -design.Ts / design.Tp1;
  return [1, planet, planet, -1 / gearRatio(design)];
}

export function gearEnvelope(gears) {
  const [sun, first, second, ring] = gears.map((gear) => gear.geometry);
  return Math.max(
    sun.pitch_diameter + first.pitch_diameter + Math.max(first.tip_diameter, second.tip_diameter),
    ring.root_diameter,
  );
}

export function planetCenters(design) {
  const [distance] = centerDistances(design);
  return Array.from({length: design.n}, (_, index) => {
    const angle = index * TAU / design.n;
    return {angle, x: distance * Math.cos(angle), y: distance * Math.sin(angle)};
  });
}

const mod = (value, modulus) => ((value % modulus) + modulus) % modulus;
function gcd(a, b) {
  while (b) [a, b] = [b, a % b];
  return a;
}

function inverseMod(a, modulus) {
  let [r, next, t, nextT] = [modulus, a, 0, 1];
  while (next) {
    const quotient = Math.floor(r / next);
    [r, next, t, nextT] = [next, r - quotient * next, nextT, t - quotient * nextT];
  }
  return mod(t, modulus);
}

export function planetPhaseStep(sun, planet1, planet2, ring, count) {
  const common = gcd(planet1, planet2);
  const numerator = sun * planet2 + ring * planet1;
  if (numerator % (count * common)) return null;
  const period = planet1 / common;
  const toothSteps = -(numerator / (count * common)) * inverseMod(planet2 / common, period);
  return TAU * mod(sun + count * toothSteps, count * period) / (count * planet1);
}

export function validateMeshPressureAngles(profiles) {
  for (const [first, second, label] of [
    [0, 1, "太陽輪與第一行星輪"], [2, 3, `第二行星輪與${GEAR_NAMES[3]}`],
  ]) {
    const a = profiles[first].pressure_angle, b = profiles[second].pressure_angle;
    if (Math.abs(a - b) > EPS * Math.max(Math.abs(a), Math.abs(b))) {
      throw new Error(`${label}的壓力角須相同才能嚙合。`);
    }
  }
}

export function meshProfileWarnings(profiles) {
  const warnings = [];
  for (const [a, b, label] of [[0, 1, "太陽輪與第一行星輪"], [2, 3, `第二行星輪與${GEAR_NAMES[3]}`]]) {
    const first = profiles[a], second = profiles[b];
    if (first.space_ratio + second.space_ratio < 2 - EPS) {
      warnings.push(`${label}的節圓齒厚總和大於周節。`);
    }
    if (first.addendum_ratio > second.dedendum_ratio || second.addendum_ratio > first.dedendum_ratio) {
      warnings.push(`${label}的齒頂超過配對齒輪的齒根深度。`);
    }
  }
  return warnings;
}

export function meshPhases(design, gears) {
  if (design.Ts + design.Tp1 !== design.Tr - design.Tp2) {
    const [external, internal] = centerDistances(design);
    throw new Error(`兩層嚙合的節圓中心距不一致（${external.toFixed(3)} 與 ${internal.toFixed(3)} mm）。請確認 Tr = Ts + Tp1 + Tp2。`);
  }
  validateMeshPressureAngles(design.profiles);
  const [sun, first, second, ring] = gears.map((gear) => gear.geometry);
  const offset = (g) => (g.pitch_angle + g.tooth_space / g.pitch_radius) / 2
    - involuteAngle(g.pitch_radius, g.base_radius);
  const step = planetPhaseStep(design.Ts, design.Tp1, design.Tp2, design.Tr, design.n);
  const warnings = meshProfileWarnings(design.profiles);
  if (step === null) {
    warnings.unshift("此齒數與行星組數無法讓所有等角分布的行星同時嚙合。圖中以第一組對齒。");
  }
  return {
    phases: [-offset(sun) - sun.half_pitch_angle, Math.PI - offset(first), -offset(second), -ring.half_pitch_angle],
    step: step ?? 0, warnings,
  };
}

export function involuteAngle(radius, base) {
  const roll = Math.sqrt(Math.max(0, (radius / base) ** 2 - 1));
  return roll - Math.atan(roll);
}

export function validateGearProfile(g, internal) {
  const {pitch_radius: rp, base_radius: rb, tip_radius: rt, root_radius: rr} = g;
  if (internal && rt < rb) {
    throw new Error(`${GEAR_NAMES[3]}的齒頂圓半徑小於基圓半徑，無法產生有效漸開線。`);
  }
  if (rr <= 0) throw new Error("齒根圓半徑須大於零，請調整齒數或齒根倍率。");
  const start = internal ? rt : Math.max(rr, rb);
  const end = internal ? rr : rt;
  const atPitch = involuteAngle(rp, rb);
  const atStart = involuteAngle(start, rb), atEnd = involuteAngle(end, rb);
  if (internal) {
    const half = g.tooth_thickness / (2 * rp);
    if (half + atStart - atPitch <= 0 || half + atEnd - atPitch >= g.half_pitch_angle) {
      throw new Error(`${GEAR_NAMES[3]}的齒面交疊，請調整齒間、齒頂或齒根倍率。`);
    }
  } else {
    const gap = g.tooth_space / rp - 2 * atPitch;
    if (gap + 2 * atStart <= 0 || gap + 2 * atEnd >= g.pitch_angle) {
      throw new Error("外齒輪的齒面交疊，請調整齒間、齒頂或齒根倍率。");
    }
  }
  return atPitch;
}

export const polar = (r, angle) => [r * Math.cos(angle), r * Math.sin(angle)];

// A counterclockwise boundary. Arcs and radial lines are exact; flank angles
// use the same involute equation as the desktop designer.
export function* profileSegments(gear) {
  const g = gear.geometry, internal = gear.internal;
  const {pitch_radius: rp, base_radius: rb, tip_radius: rt, root_radius: rr, pitch_angle: pitch} = g;
  const atPitch = validateGearProfile(g, internal);
  if (!internal && gear.bore >= g.root_diameter) {
    throw new Error(`${gear.name}的軸孔直徑須小於齒根圓直徑。`);
  }
  const arc = (radius, a0, a1) => ({kind: "arc", radius, a0, a1});
  const radial = (r0, r1, angle) => ({kind: "line", r0, r1, angle});
  const flank = (r0, r1, angle, sign) => ({kind: "flank", r0, r1, angle, sign, base: rb});
  if (internal) {
    const half = g.tooth_thickness / (2 * rp) - atPitch;
    const tipHalf = half + involuteAngle(rt, rb), rootHalf = half + involuteAngle(rr, rb);
    for (let i = 0; i < gear.teeth; i++) {
      const angle = i * pitch, next = (i + 1) * pitch;
      yield flank(rr, rt, angle - half, -1);
      yield arc(rt, angle - tipHalf, angle + tipHalf);
      yield flank(rt, rr, angle + half, 1);
      yield arc(rr, angle + rootHalf, next - rootHalf);
    }
  } else {
    const start = Math.max(rr, rb);
    const startAngle = involuteAngle(start, rb), tipAngle = involuteAngle(rt, rb);
    const gap = g.tooth_space / rp - 2 * atPitch;
    for (let i = 0; i < gear.teeth; i++) {
      const angle = i * pitch, next = (i + 1) * pitch;
      yield arc(rr, angle - startAngle, angle + gap + startAngle);
      if (rb > rr) yield radial(rr, rb, angle + gap);
      yield flank(start, rt, angle + gap, 1);
      yield arc(rt, angle + gap + tipAngle, next - tipAngle);
      yield flank(rt, start, next, -1);
      if (rb > rr) yield radial(rb, rr, next);
    }
  }
}

export function segmentPoint(segment, t) {
  if (segment.kind === "arc") return polar(segment.radius, segment.a0 + t * (segment.a1 - segment.a0));
  const radius = segment.r0 + t * (segment.r1 - segment.r0);
  const angle = segment.angle + (segment.kind === "flank" ? segment.sign * involuteAngle(radius, segment.base) : 0);
  return polar(radius, angle);
}

export function readSearchValues(values) {
  const criteria = {};
  for (const [key, label] of [
    ["M", "模數"], ["max_diameter", "最大齒輪外廓"], ["min_ratio", "最低齒比"],
    ["min_teeth", "最小齒數"], ["n", "行星輪組數"],
  ]) {
    const value = numberInput(values[key], label);
    criteria[key] = key === "min_teeth" ? boundedInteger(value, label, MAX_TEETH)
      : key === "n" ? boundedInteger(value, label, MAX_PLANETS) : positive(value, label);
  }
  return criteria;
}

export function findGearCombinations(base, values) {
  const {M, max_diameter, min_ratio, min_teeth, n} = readSearchValues(values);
  validateMeshPressureAngles(base.profiles);
  const warnings = meshProfileWarnings(base.profiles);
  if (warnings.length) throw new Error(`請先調整單顆設計。\n${warnings.join("\n")}`);
  const [, first, second, ring] = base.profiles;
  const diameterModules = max_diameter / M;
  const maxRing = Math.floor(diameterModules - 2 * ring.dedendum_ratio + EPS);
  const span = maxRing - 3 * min_teeth;
  const candidates = [];
  if (span < 0) return {total: 0, candidates};
  if ((span + 3) * (span + 2) * (span + 1) / 6 > 2_000_000 || maxRing > MAX_TEETH) {
    throw new Error("搜尋範圍過大，請縮小外廓上限、提高模數或提高最小齒數。");
  }

  const cache = Array.from({length: 4}, () => new Map());
  function profileFits(role, teeth) {
    if (cache[role].has(teeth)) return cache[role].get(teeth);
    const settings = base.profiles[role], internal = role === 3;
    const geometry = gearGeometry(M, teeth, internal, settings);
    let fits = Object.values(geometry).every(Number.isFinite) &&
      (internal || (settings.bore_diameter ?? base.axle) < geometry.root_diameter);
    if (fits) {
      try { validateGearProfile(geometry, internal); }
      catch { fits = false; }
    }
    cache[role].set(teeth, fits);
    return fits;
  }

  const spacing = n > 1 ? Math.sin(Math.PI / n) : Infinity;
  const limit = 200;
  const compare = (a, b) => a.ratio - b.ratio || a.diameter - b.diameter;
  let total = 0;
  for (let Ts = min_teeth; Ts <= maxRing - 2 * min_teeth; Ts++) {
    if (!profileFits(0, Ts)) continue;
    const largestFirst = Math.min(
      maxRing - Ts - min_teeth, Math.floor((diameterModules - Ts) / 2 - first.addendum_ratio + EPS),
    );
    for (let Tp1 = min_teeth; Tp1 <= largestFirst; Tp1++) {
      const orbit = Ts + Tp1, allowedTip = orbit * spacing, tip1 = Tp1 + 2 * first.addendum_ratio;
      if (tip1 > allowedTip + EPS || !profileFits(1, Tp1)) continue;
      for (let Tp2 = min_teeth; Tp2 <= maxRing - orbit; Tp2++) {
        const Tr = orbit + Tp2, ratio = gearRatio({Ts, Tp1, Tp2, Tr}), tip2 = Tp2 + 2 * second.addendum_ratio;
        if (ratio <= min_ratio || tip2 > allowedTip + EPS) break;
        const common = gcd(Tp1, Tp2);
        if (common === 1 || (Ts * Tp2 + Tr * Tp1) % (n * common)) continue;
        const diameter = M * Math.max(orbit + Math.max(tip1, tip2), Tr + 2 * ring.dedendum_ratio);
        if (diameter > max_diameter + EPS) break;
        if (!profileFits(2, Tp2) || !profileFits(3, Tr)) continue;
        total++;
        const candidate = {design: {...base, Ts, Tp1, Tp2, Tr, M, n}, ratio, diameter};
        if (candidates.length === limit && compare(candidate, candidates.at(-1)) >= 0) continue;
        const tipRatio = Math.max(tip1, tip2) / orbit;
        candidate.maxPlanets = tipRatio > 1 ? 1 : Math.floor(Math.PI / Math.asin(tipRatio) + EPS);
        let lo = 0, hi = candidates.length;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          if (compare(candidate, candidates[mid]) < 0) hi = mid;
          else lo = mid + 1;
        }
        candidates.splice(lo, 0, candidate);
        if (candidates.length > limit) candidates.pop();
      }
    }
  }
  return {total, candidates};
}
