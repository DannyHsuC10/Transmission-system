import io
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np

from gear_search import find_gear_combinations
from gear_system_designer import (
    DEFAULT_DATA,
    GearSettings,
    gear_centers,
    gear_curves,
    gear_geometry,
    gear_mesh_phases,
    external_tooth_center_offset,
    involute_angle,
    load_gear_set,
    make_gears,
    planet_phase_step,
    plot_assembly,
    plot_layout,
    print_calculations,
    show_figures,
)


class GearSystemDesignerTests(unittest.TestCase):
    def assert_phase_matches(self, phase, pitch_angle):
        pitch_count = phase / pitch_angle
        self.assertAlmostEqual(pitch_count, round(pitch_count))

    def test_default_csv_matches_matlab_example(self):
        gear_set = load_gear_set(DEFAULT_DATA)
        self.assertEqual(
            (gear_set.sun_teeth, gear_set.ring_teeth, gear_set.planet1_teeth,
             gear_set.planet2_teeth, gear_set.planet_count),
            (21, 102, 57, 24, 3),
        )
        self.assertEqual(gear_set.module, 0.8)

    def test_geometry_matches_matlab_formulas(self):
        geometry = gear_geometry(0.8, 21)
        self.assertAlmostEqual(geometry.pitch_diameter, 16.8)
        self.assertAlmostEqual(geometry.tip_diameter, 18.4)
        self.assertAlmostEqual(geometry.root_diameter, 14.8)
        self.assertAlmostEqual(
            geometry.base_diameter,
            16.8 * math.cos(math.radians(20)),
        )

    def test_internal_ring_uses_inward_addendum_and_outward_dedendum(self):
        geometry = gear_geometry(0.8, 102, internal=True)
        self.assertAlmostEqual(geometry.tip_diameter, 80.0)
        self.assertAlmostEqual(geometry.root_diameter, 83.6)

    def test_gear_profiles_are_finite_and_include_all_teeth(self):
        curves = gear_curves(0.8, 21)
        self.assertTrue(curves)
        for _, x, y in curves:
            self.assertTrue(np.isfinite(x).all())
            self.assertTrue(np.isfinite(y).all())

    def test_involute_angle_matches_cartesian_unwinding(self):
        base_radius = 10.0
        roll = np.array([0, math.tan(math.radians(20)), 0.65])
        x = base_radius * (np.cos(roll) + roll * np.sin(roll))
        y = base_radius * (np.sin(roll) - roll * np.cos(roll))
        np.testing.assert_allclose(
            involute_angle(np.hypot(x, y), base_radius), np.arctan2(y, x), atol=1e-12
        )

    def test_external_root_arc_meets_flanks_above_base_circle(self):
        gear_set = load_gear_set(DEFAULT_DATA)
        left, right, _, root = gear_curves(gear_set.module, gear_set.planet1_teeth)[:4]
        np.testing.assert_allclose(
            np.column_stack(root[1:])[[0, -1]],
            [np.column_stack(left[1:])[-1], np.column_stack(right[1:])[0]],
            atol=1e-12,
        )

    def test_internal_ring_profile_points_inward(self):
        gear_set = load_gear_set(DEFAULT_DATA)
        curves = gear_curves(gear_set.module, gear_set.ring_teeth, internal=True)
        radii = np.concatenate(
            [
                np.hypot(x, y)
                for color, x, y in curves
                if color != "white"
            ]
        )
        pitch_radius = gear_geometry(
            gear_set.module, gear_set.ring_teeth
        ).pitch_radius

        self.assertAlmostEqual(radii.min(), pitch_radius - gear_set.module)
        self.assertAlmostEqual(radii.max(), pitch_radius + 1.25 * gear_set.module)

    def test_default_planet_profiles_fit_inside_ring_opening(self):
        gear_set = load_gear_set(DEFAULT_DATA)
        phases = gear_mesh_phases(gear_set)
        ring = gear_curves(gear_set.module, gear_set.ring_teeth, phases.ring, internal=True)
        opening = []
        for index in range(0, 4 * gear_set.ring_teeth, 4):
            tip, root, left, right = ring[index:index + 4]
            opening.extend((
                np.column_stack(left[1:])[::-1], np.column_stack(tip[1:]),
                np.column_stack(right[1:]), np.column_stack(root[1:]),
            ))
        ring_x, ring_y = np.concatenate(opening).T
        ring_angles = np.unwrap(np.arctan2(ring_y, ring_x))
        ring_radii = np.hypot(ring_x, ring_y)
        self.assertGreaterEqual(np.min(np.diff(ring_angles)), -1e-12)

        # Allow for the error from approximating each curved segment by chords.
        for angle, x, y in gear_centers(gear_set):
            planet = gear_curves(gear_set.module, gear_set.planet2_teeth, angle + phases.planet2)
            planet_x, planet_y = np.concatenate([
                np.column_stack(segment[1:]) for segment in planet if segment[0] != "white"
            ]).T
            planet_x += x
            planet_y += y
            planet_angles = np.arctan2(planet_y, planet_x)
            query = ring_angles[0] + (planet_angles - ring_angles[0]) % (2 * math.pi)
            clearance = np.interp(query, ring_angles, ring_radii) - np.hypot(planet_x, planet_y)
            self.assertGreaterEqual(clearance.min(), -0.00005)

    def test_mesh_phases_align_contact_tooth_and_gap_centers(self):
        gear_set = load_gear_set(DEFAULT_DATA)
        phases = gear_mesh_phases(gear_set)

        sun = gear_geometry(gear_set.module, gear_set.sun_teeth)
        ring = gear_geometry(gear_set.module, gear_set.ring_teeth)
        sun_tooth_center = external_tooth_center_offset(
            gear_set.module, gear_set.sun_teeth
        )
        planet1_tooth_center = external_tooth_center_offset(
            gear_set.module, gear_set.planet1_teeth
        )
        planet2_tooth_center = external_tooth_center_offset(
            gear_set.module, gear_set.planet2_teeth
        )
        self.assert_phase_matches(
            phases.sun + sun_tooth_center + sun.half_pitch_angle,
            sun.pitch_angle,
        )
        self.assert_phase_matches(
            phases.planet1 + planet1_tooth_center - math.pi,
            gear_geometry(gear_set.module, gear_set.planet1_teeth).pitch_angle,
        )
        self.assert_phase_matches(
            phases.planet2 + planet2_tooth_center,
            gear_geometry(gear_set.module, gear_set.planet2_teeth).pitch_angle,
        )
        self.assert_phase_matches(
            phases.ring + ring.half_pitch_angle,
            ring.pitch_angle,
        )

        for index in range(gear_set.planet_count):
            position = 2 * math.pi * index / gear_set.planet_count
            self.assert_phase_matches(position, sun.pitch_angle)
            self.assert_phase_matches(position, ring.pitch_angle)

    def test_mesh_phase_calculation_rejects_mismatched_center_distances(self):
        gear_set = replace(load_gear_set(DEFAULT_DATA), planet2_teeth=25)
        with self.assertRaisesRegex(ValueError, "中心距不一致"):
            gear_mesh_phases(gear_set)

    def test_individual_profile_is_used_in_assembly(self):
        defaults = load_gear_set(DEFAULT_DATA)
        sun = GearSettings(addendum_ratio=0.9, space_ratio=1.05, bore_diameter=7)
        gear_set = replace(defaults, gear_settings=(sun, *defaults.gear_settings[1:]))
        gears = make_gears(gear_set)
        self.assertEqual(gears[1].bore_diameter, defaults.axle_diameter)
        figure = plot_assembly(gear_set, gears)
        self.addCleanup(plt.close, figure)
        curves = figure.axes[0].lines[:6 * gear_set.sun_teeth + 1]
        tip_radius = (gear_set.sun_teeth / 2 + 0.9) * gear_set.module
        self.assertAlmostEqual(max(np.hypot(line.get_xdata(), line.get_ydata()).max()
                                   for line in curves), tip_radius)
        self.assertAlmostEqual(np.hypot(curves[-1].get_xdata(), curves[-1].get_ydata()).max(), 3.5)

    def test_mesh_phase_calculation_rejects_mismatched_pressure_angles(self):
        defaults = load_gear_set(DEFAULT_DATA)
        settings = (*defaults.gear_settings[:3], GearSettings(pressure_angle=22))
        gear_set = replace(defaults, gear_settings=settings)
        with self.assertRaisesRegex(ValueError, "壓力角須相同"):
            gear_mesh_phases(gear_set)

    def test_search_applies_diameter_and_planet_spacing_limits(self):
        base = load_gear_set(DEFAULT_DATA)
        criteria = dict(module=0.8, min_ratio=8, min_teeth=20, max_diameter=90.4)
        _, results = find_gear_combinations(base, **criteria, planet_count=3)
        gear_set = replace(base, planet1_teeth=45, ring_teeth=90)
        candidate = next(candidate for candidate in results if candidate.gear_set == gear_set)
        self.assertAlmostEqual(candidate.diameter, 90.4)
        self.assertEqual(candidate.max_planets, 3)
        _, results = find_gear_combinations(base, **criteria, planet_count=4)
        self.assertTrue(all(candidate.gear_set.planet1_teeth != 45
                            or candidate.gear_set.sun_teeth != 21
                            or candidate.gear_set.planet2_teeth != 24 for candidate in results))
        criteria["max_diameter"] = 90.39
        _, results = find_gear_combinations(base, **criteria, planet_count=3)
        self.assertNotIn(gear_set, [candidate.gear_set for candidate in results])

    def test_search_candidate_uses_a_shared_rotation_to_mesh_both_wheels(self):
        base = load_gear_set(DEFAULT_DATA)
        _, results = find_gear_combinations(
            base, module=0.8, max_diameter=102, min_ratio=8, min_teeth=20, planet_count=3,
        )
        gear_set = replace(base, sun_teeth=20, planet1_teeth=52, planet2_teeth=34, ring_teeth=106)
        self.assertIn(gear_set, [candidate.gear_set for candidate in results])
        step = planet_phase_step(20, 52, 34, 106, 3)
        self.assertNotEqual(step, 0)
        for index in range(3):
            station = index / 3
            turns = index * step / math.tau
            self.assertAlmostEqual(52 * turns - 20 * station, round(52 * turns - 20 * station))
            self.assertAlmostEqual(34 * turns + 106 * station, round(34 * turns + 106 * station))

    def test_layout_axis_limits_contain_all_gear_pitch_circles(self):
        gear_set = load_gear_set(DEFAULT_DATA)
        gears = make_gears(gear_set)
        figure = plot_layout(gear_set, gears)
        axes = figure.axes[0]

        self.assertEqual(len(axes.patches), 2 + 2 * gear_set.planet_count)
        self.assertLessEqual(axes.get_xlim()[0], -54)
        self.assertGreaterEqual(axes.get_xlim()[1], 54)
        self.assertLessEqual(axes.get_ylim()[0], -54)
        self.assertGreaterEqual(axes.get_ylim()[1], 54)
        plt.close(figure)

    def test_calculations_print_all_gear_names(self):
        gear_set = load_gear_set(DEFAULT_DATA)
        output = io.StringIO()
        print_calculations(gear_set, make_gears(gear_set), output)
        report = output.getvalue()
        for name in ("太陽齒輪", "行星齒輪", "行星齒輪2", "內齒輪"):
            self.assertIn(name, report)
        self.assertIn("基圓直徑", report)
        self.assertIn("半周節角度", report)

    def test_missing_parameter_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.csv"
            path.write_text("name,value\nTs,21\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "缺少必要參數"):
                load_gear_set(path)

    def test_tkagg_backend_shows_figures(self):
        with (
            patch.object(plt, "get_backend", return_value="TkAgg"),
            patch.object(plt, "show") as show,
        ):
            show_figures()
        show.assert_called_once_with()

    def test_agg_backend_does_not_try_to_show_figures(self):
        with (
            patch.object(plt, "get_backend", return_value="agg"),
            patch.object(plt, "show") as show,
        ):
            show_figures()
        show.assert_not_called()


if __name__ == "__main__":
    unittest.main()
