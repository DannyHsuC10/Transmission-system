import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import {
  centerDistances, defaultDesign, findGearCombinations, gearEnvelope, makeGears, meshPhases,
  planetPhaseStep, profileSegments, readGearCsv, readProfileValues, segmentPoint, TAU,
} from "../docs/assets/gear-model.js";
import {cadCircleRadius, writeStep} from "../docs/assets/cad-export.js";

const near = (value, expected, tolerance = 1e-9) => assert.ok(Math.abs(value - expected) <= tolerance,
  `${value} differs from ${expected}`);
const defaults = defaultDesign();
const gears = makeGears(defaults);

test("browser defaults match the desktop CSV and its geometry", () => {
  const {profiles, ...values} = defaults;
  for (const file of ["../Gear_system_Designer_Python/data/tooth.csv", "../docs/assets/tooth.csv"]) {
    const csv = readFileSync(new URL(file, import.meta.url), "utf-8");
    assert.deepEqual(readGearCsv(csv), values);
  }
  assert.throws(() => readGearCsv("name,value\nTs,21"), /缺少必要參數/);
  near(gears[0].geometry.pitch_diameter, 16.8);
  near(gears[0].geometry.tip_diameter, 18.4);
  near(gears[0].geometry.root_diameter, 14.8);
  near(gears[0].geometry.fillet_radius, 0.1888);
  near(gears[3].geometry.tip_diameter, 80);
  near(gears[3].geometry.root_diameter, 83.6);
  centerDistances(defaults).forEach((distance) => near(distance, 31.2));
  near(gearEnvelope(gears), 109.6);
});

test("all tooth profiles close and an explicit bore stays independent of the default", () => {
  const modified = {...defaults, profiles: defaults.profiles.map((profile, role) => role === 0
    ? readProfileValues({...profile, addendum_ratio: "0.9", bore_diameter: "7"}, false) : profile)};
  const custom = makeGears(modified);
  near(custom[0].geometry.tip_radius, 9.12);
  assert.equal(custom[0].bore, 7);
  assert.equal(custom[1].bore, 10);
  for (const gear of custom) {
    const segments = [...profileSegments(gear)];
    assert.equal(segments.filter((segment) => segment.kind === "flank").length, 2 * gear.teeth);
    for (let i = 0; i < segments.length; i++) {
      const [x, y] = segmentPoint(segments[i], 1);
      const [nx, ny] = segmentPoint(segments[(i + 1) % segments.length], 0);
      near(Math.hypot(x - nx, y - ny), 0);
    }
  }
  assert.throws(() => cadCircleRadius(gears[3], 83), /外徑須大於/);
  assert.throws(() => writeStep(gears[0], null, 0), /厚度須大於零/);
});

test("invalid assemblies report center distance, pressure angle and shared phase issues", () => {
  assert.equal(meshPhases(defaults, gears).warnings.length, 0);
  assert.throws(() => meshPhases({...defaults, Tp2: 25}, gears), /中心距不一致/);
  const settings = {...defaults, profiles: [...defaults.profiles.slice(0, 3), {...defaults.profiles[3], pressure_angle: 22}]};
  assert.throws(() => meshPhases(settings, makeGears(settings)), /壓力角須相同/);
  assert.match(meshPhases({...defaults, n: 4}, gears).warnings[0], /無法讓所有等角分布的行星同時嚙合/);
  const step = planetPhaseStep(20, 52, 34, 106, 3);
  assert.ok(step > 0);
  for (let i = 0; i < 3; i++) {
    for (const phase of [52 * i * step / TAU - 20 * i / 3, 34 * i * step / TAU + 106 * i / 3]) {
      near(phase, Math.round(phase));
    }
  }
});

test("search matches Python counts, ordering, spacing and diameter boundary", () => {
  const criteria = {M: 0.8, max_diameter: 110, min_ratio: 8, min_teeth: 20, n: 3};
  const result = findGearCombinations(defaults, criteria);
  assert.equal(result.total, 193);
  const best = result.candidates[0];
  assert.deepEqual([best.design.Ts, best.design.Tp1, best.design.Tp2, best.design.Tr], [24, 51, 27, 102]);
  near(best.ratio, 8.027777777777779);
  near(best.diameter, 102.4);
  assert.equal(best.maxPlanets, 4);
  assert.equal(findGearCombinations(defaults, {...criteria, max_diameter: 90.4}).total, 8);
  assert.equal(findGearCombinations(defaults, {...criteria, max_diameter: 90.4, n: 4}).total, 3);
  assert.ok(!findGearCombinations(defaults, {...criteria, max_diameter: 90.39}).candidates
    .some(({design}) => design.Ts === 21 && design.Tp1 === 45 && design.Tp2 === 24));
  const larger = findGearCombinations(defaults, {...criteria, max_diameter: 140});
  assert.equal(larger.total, 1557);
  assert.equal(larger.candidates.length, 200);
  assert.throws(() => findGearCombinations(defaults, {...criteria, max_diameter: 300}), /搜尋範圍過大/);
});
