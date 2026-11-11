"""Screen compound planetary gear combinations from the two design analyses."""

import math
from dataclasses import dataclass, replace
from functools import cache
from heapq import nsmallest

from gear_system_designer import (
    GearSet,
    gear_geometry,
    mesh_profile_warnings,
    planet_phase_step,
    validate_gear_profile,
    validate_mesh_pressure_angles,
)


@dataclass(frozen=True)
class GearCandidate:
    gear_set: GearSet
    ratio: float
    diameter: float
    max_planets: int


def find_gear_combinations(
    base: GearSet,
    *,
    module: float,
    max_diameter: float,
    min_ratio: float,
    min_teeth: int,
    planet_count: int,
) -> tuple[int, list[GearCandidate]]:
    """Return the total count and up to 200 candidates, ordered by ratio and diameter."""
    if not all(math.isfinite(value) and value > 0 for value in (module, max_diameter, min_ratio)):
        raise ValueError("模數、外廓上限與最低齒比須為正數。")
    if min_teeth < 1 or planet_count < 1:
        raise ValueError("最小齒數與行星輪組數須為正整數。")

    validate_mesh_pressure_angles(base.gear_settings)
    warnings = mesh_profile_warnings(base.gear_settings)
    if warnings:
        raise ValueError("請先調整單顆設計。" + "\n".join(warnings))
    diameter_in_modules = max_diameter / module
    if not math.isfinite(diameter_in_modules):
        raise ValueError("搜尋範圍過大，請縮小外廓上限或提高模數。")

    _, first, second, ring = base.gear_settings
    ring_allowance = diameter_in_modules - 2 * ring.dedendum_ratio
    if ring_allowance < 3 * min_teeth - 1e-9:
        return 0, []
    max_ring = math.floor(ring_allowance + 1e-9)
    span = max_ring - 3 * min_teeth
    if math.comb(span + 3, 3) > 2_000_000:
        raise ValueError("搜尋範圍過大，請縮小外廓上限、提高模數或提高最小齒數。")

    @cache
    def profile_fits(role: int, teeth: int) -> bool:
        settings = base.gear_settings[role]
        internal = role == 3
        geometry = gear_geometry(module, teeth, internal=internal, settings=settings)
        try:
            validate_gear_profile(geometry, internal=internal)
        except ValueError:
            return False
        bore = base.axle_diameter if settings.bore_diameter is None else settings.bore_diameter
        return internal or bore < geometry.root_diameter

    spacing = math.sin(math.pi / planet_count) if planet_count > 1 else math.inf
    total = 0

    def matches():
        nonlocal total
        for sun in range(min_teeth, max_ring - 2 * min_teeth + 1):
            if not profile_fits(0, sun):
                continue
            largest_first = min(
                max_ring - sun - min_teeth,
                math.floor((diameter_in_modules - sun) / 2 - first.addendum_ratio + 1e-9),
            )
            for planet1 in range(min_teeth, largest_first + 1):
                orbit_diameter = sun + planet1
                allowed_tip = orbit_diameter * spacing
                tip1 = planet1 + 2 * first.addendum_ratio
                if tip1 > allowed_tip + 1e-9 or not profile_fits(1, planet1):
                    continue
                largest_second = max_ring - orbit_diameter
                for planet2 in range(min_teeth, largest_second + 1):
                    ring_teeth = orbit_diameter + planet2
                    ratio = planet1 * ring_teeth / (sun * planet2)
                    tip2 = planet2 + 2 * second.addendum_ratio
                    if ratio <= min_ratio or tip2 > allowed_tip + 1e-9:
                        break
                    if math.gcd(planet1, planet2) == 1:
                        continue
                    if planet_phase_step(sun, planet1, planet2, ring_teeth, planet_count) is None:
                        continue
                    diameter = module * max(
                        orbit_diameter + max(tip1, tip2),
                        ring_teeth + 2 * ring.dedendum_ratio,
                    )
                    if diameter > max_diameter + 1e-9:
                        break
                    if not profile_fits(2, planet2) or not profile_fits(3, ring_teeth):
                        continue
                    tip_ratio = max(tip1, tip2) / orbit_diameter
                    max_planets = 1 if tip_ratio > 1 else math.floor(
                        math.pi / math.asin(tip_ratio) + 1e-9
                    )
                    total += 1
                    yield GearCandidate(
                        replace(
                            base, sun_teeth=sun, planet1_teeth=planet1, planet2_teeth=planet2,
                            ring_teeth=ring_teeth, module=module, planet_count=planet_count,
                        ),
                        ratio,
                        diameter,
                        max_planets,
                    )

    best = nsmallest(200, matches(), key=lambda candidate: (candidate.ratio, candidate.diameter))
    return total, best
