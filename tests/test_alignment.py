"""Directional ordered one-to-one alignment (reference -> target).

The low-level tests use plain coordinate tuples so they exercise the algorithm and nothing else: no file
formats, no vendor names.  The brute-force oracle enumerates every order-preserving one-to-one assignment on
small random instances and checks that the dynamic programme finds the true minimum of the same cost.
"""
import itertools
import math
import random

import pytest

from shotlogfixer.alignment import (CORRIDOR_HALF_WIDTH, SKIP_EVENT_COST, UNIT, align_records, embed_ordered)
from shotlogfixer.analysis_parameters import AnalysisParameters
from shotlogfixer.models import REFERENCE, TARGET, SourceRecord

CAP = 15.625  # 5 x 3.125 m


def line(count, step=3.125, x0=1000.0, y0=2000.0):
    return [(x0 + step * i, y0) for i in range(count)]


def cost_units(a, b, cap=CAP):
    if a is None or b is None:
        return round(cap * UNIT)
    d = math.hypot(a[0] - b[0], a[1] - b[1])
    return round(cap * UNIT) if d >= cap else round(d * UNIT)


def assignment_cost(a_pts, b_pts, targets, cap=CAP):
    """Total cost of an assignment under the documented cost: saturating spatial + one unit per skip event."""
    total = sum(cost_units(a_pts[i], b_pts[j], cap) for i, j in enumerate(targets))
    slack = len(b_pts) - len(a_pts)
    offsets = [j - i for i, j in enumerate(targets)]
    events = (1 if offsets[0] > 0 else 0) + sum(1 for p, q in zip(offsets, offsets[1:]) if q > p) + (1 if offsets[-1] < slack else 0)
    return total + events * SKIP_EVENT_COST


def brute_force_minimum(a_pts, b_pts, cap=CAP):
    return min(assignment_cost(a_pts, b_pts, combo, cap)
               for combo in itertools.combinations(range(len(b_pts)), len(a_pts)))


# ---------------------------------------------------------------------------------------------------
# Invariants and the exhaustive oracle
# ---------------------------------------------------------------------------------------------------

def assert_valid(emb, m, n):
    assert len(emb.targets) == m
    assert len(set(emb.targets)) == m, "one target row must never be used twice"
    assert all(a < b for a, b in zip(emb.targets, emb.targets[1:])), "assignment must preserve acquisition order"
    assert all(0 <= t < n for t in emb.targets)


@pytest.mark.parametrize("seed", range(60))
def test_dp_matches_exhaustive_minimum_on_random_instances(seed):
    rng = random.Random(seed)
    m = rng.randint(1, 6)
    n = m + rng.randint(0, 4)
    base = line(n, step=rng.choice([1.0, 3.125, 5.0]))
    a_pts = []
    # reference rows are noisy copies of a random increasing subset of the target rows
    chosen = sorted(rng.sample(range(n), m))
    for j in chosen:
        x, y = base[j]
        r = rng.random()
        if r < 0.15:                      # gross anomaly: far away
            a_pts.append((x + rng.uniform(80, 300), y + rng.uniform(-300, 300)))
        elif r < 0.25:                    # moderately wrong coordinate
            a_pts.append((x + rng.uniform(-2, 2), y + rng.uniform(-2, 2)))
        else:
            a_pts.append((x + rng.gauss(0, 0.4), y + rng.gauss(0, 0.4)))
    b_pts = list(base)
    for k in rng.sample(range(n), rng.randint(0, 1)):
        b_pts[k] = None                   # a target row without a usable position stays a candidate
    emb = embed_ordered(a_pts, b_pts, CAP)
    assert_valid(emb, m, n)
    assert emb.cost_units == brute_force_minimum(a_pts, b_pts)
    assert assignment_cost(a_pts, b_pts, emb.targets) == emb.cost_units, "reported cost must equal the cost of the returned path"


def test_ties_break_deterministically():
    a = [(0.0, 0.0), (10.0, 0.0)]
    b = [(0.0, 0.0), (0.0, 0.0), (10.0, 0.0)]
    first = embed_ordered(a, b, CAP)
    assert first.targets == embed_ordered(a, b, CAP).targets
    assert first.targets == [0, 2], "equal-cost placements prefer the earliest rows (skips as late as possible)"


# ---------------------------------------------------------------------------------------------------
# Required behaviours (cases 1-7 of the brief)
# ---------------------------------------------------------------------------------------------------

def test_case1_normal_nearest_alignment():
    ref = [(1000.0, 2000.0), (1003.1, 2000.0), (1006.3, 2000.0)]
    tgt = [(1000.2, 2000.1), (1003.0, 1999.9), (1006.4, 2000.0)]
    emb = embed_ordered(ref, tgt, CAP)
    assert emb.targets == [0, 1, 2]
    assert not any(emb.saturated)
    assert all(not alts for alts in emb.alternatives)


@pytest.mark.parametrize("extra_at", [0, 1, 2, 3])
def test_case2_extra_target_row_is_the_one_left_unassigned(extra_at):
    pts = line(3)
    tgt = list(pts)
    tgt.insert(extra_at, (pts[0][0] - 1.5 + extra_at * 3.125, 2040.0))   # an extra shot well off the line
    emb = embed_ordered(pts, tgt, CAP)
    assert_valid(emb, 3, 4)
    assert extra_at not in emb.targets
    assert len(emb.targets) == 3


def test_case4_recorder_coordinate_anomaly_keeps_the_sequence_consistent_row():
    ref = line(6)
    ref[3] = (ref[3][0] + 200.0, ref[3][1] + 80.0)            # one coordinate jumps ~215 m
    tgt = line(6)
    emb = embed_ordered(ref, tgt, CAP)
    assert emb.targets == [0, 1, 2, 3, 4, 5]
    assert emb.saturated[3] and emb.distance_m[3] > 200
    assert not any(emb.saturated[i] for i in (0, 1, 2, 4, 5))


def test_case4_anomaly_between_clean_neighbours_takes_the_only_row_between_them():
    ref = line(6)
    ref[3] = (ref[3][0] + 200.0, ref[3][1])
    tgt = line(8)                                  # two spare rows exist after the sequence
    emb = embed_ordered(ref, tgt, CAP)
    assert emb.targets[:3] == [0, 1, 2]
    assert emb.targets[3] == 3, "its clean neighbours leave exactly one row for it"
    assert emb.targets[4:] == [4, 5]
    assert emb.saturated[3] and not emb.alternatives[3]


def test_case4_terminal_anomaly_is_retained_and_takes_the_next_row():
    ref = line(5)
    ref[4] = (ref[4][0] + 180.0, ref[4][1] + 100.0)            # last record jumps ~205 m
    tgt = line(7)                                  # two spare target rows after the anomalous record
    emb = embed_ordered(ref, tgt, CAP)
    assert emb.targets == [0, 1, 2, 3, 4], "the terminal record takes the sequence-next row; trailing rows stay unassigned"
    assert emb.saturated[4]
    assert emb.alternatives[4], "its placement among the trailing rows is flagged as ambiguous"


def test_case5_competing_nearest_candidates_resolve_one_to_one_by_order():
    # Independent nearest-neighbour matching would give both reference rows the same target row (10.2).
    ref = [(10.0, 0.0), (10.3, 0.0)]
    tgt = [(9.0, 0.0), (10.2, 0.0), (11.0, 0.0)]
    nearest = [min(range(3), key=lambda j: abs(tgt[j][0] - r[0])) for r in ref]
    assert nearest == [1, 1], "the scenario really is a nearest-neighbour collision"
    emb = embed_ordered(ref, tgt, CAP)
    assert emb.targets == [1, 2]
    assert len(set(emb.targets)) == 2


def test_case6_full_decimal_precision_decides_between_candidates():
    # Same integer easting/northing for both candidates; only the decimals separate them.
    ref = [(615190.23, 4645679.70)]
    tgt = [(615190.90, 4645679.20), (615190.10, 4645679.75)]
    emb = embed_ordered(ref, tgt, CAP)
    assert emb.targets == [1]
    assert emb.distance_m[0] == pytest.approx(math.hypot(0.13, 0.05))


def test_case7_large_distance_but_deterministic_sequence_is_still_assigned():
    ref = line(4)
    ref[1] = (ref[1][0] + 1000.0, ref[1][1] - 1000.0)
    tgt = line(4)
    emb = embed_ordered(ref, tgt, CAP)
    assert emb.targets == [0, 1, 2, 3]
    assert emb.saturated[1]


def test_unusable_target_position_is_a_candidate_placed_by_sequence():
    ref = line(3)
    tgt = [ref[0], None, ref[2]]
    emb = embed_ordered(ref, tgt, CAP)
    assert emb.targets == [0, 1, 2]
    assert emb.saturated[1] and emb.distance_m[1] is None


def test_no_distance_threshold_can_reject_a_reference_record():
    ref = [(0.0, 0.0), (1.0e6, 1.0e6), (6.0, 0.0)]
    tgt = [(0.0, 0.0), (3.0, 0.0), (6.0, 0.0)]
    assert embed_ordered(ref, tgt, 0.001).targets == [0, 1, 2]
    assert embed_ordered(ref, tgt, 1.0e9).targets == [0, 1, 2]


def test_min_marginal_ambiguity_marks_only_genuinely_competing_placements():
    # Two identical spare rows around a reference point: the placement is genuinely ambiguous.
    emb = embed_ordered([(0.0, 0.0)], [(0.0, 0.0), (0.0, 0.0)], CAP)
    assert emb.targets == [0] and emb.alternatives[0] == (1,)
    # A forced placement (no spare rows) can never be ambiguous, however similar the points are.
    forced = embed_ordered([(0.0, 0.0), (0.0, 0.1)], [(0.0, 0.0), (0.0, 0.1)], CAP)
    assert forced.alternatives == [(), ()]


def test_shorter_target_is_rejected_by_the_low_level_embedding():
    with pytest.raises(ValueError):
        embed_ordered(line(3), line(2), CAP)


# ---------------------------------------------------------------------------------------------------
# Large slack: corridor search must agree with the exact search
# ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(3))
def test_corridor_search_agrees_with_exact_search(seed):
    rng = random.Random(seed)
    n = 900
    base = line(n, step=3.125)
    chosen = sorted(rng.sample(range(n), 700))
    ref = [(base[j][0] + rng.gauss(0, 0.3), base[j][1] + rng.gauss(0, 0.3)) for j in chosen]
    ref[350] = (ref[350][0] + 400.0, ref[350][1])           # an anomaly the corridor must survive
    exact = embed_ordered(ref, base, CAP, full_band_max_slack=10_000)
    corridor = embed_ordered(ref, base, CAP, full_band_max_slack=50)
    assert corridor.windowed and not exact.windowed
    assert_valid(corridor, len(ref), n)
    assert corridor.cost_units == exact.cost_units
    assert corridor.targets == exact.targets


def test_corridor_search_is_fast_for_very_large_slack():
    import time
    n, m = 20_000, 6_000
    base = line(n)
    chosen = sorted(random.Random(7).sample(range(n), m))
    ref = [base[j] for j in chosen]
    started = time.perf_counter()
    emb = embed_ordered(ref, base, CAP)
    assert time.perf_counter() - started < 20
    assert emb.windowed and emb.targets == chosen


# ---------------------------------------------------------------------------------------------------
# Record level: roles, validity, partial results
# ---------------------------------------------------------------------------------------------------

def rec(role, index, x, y, classification="VALID", ffid=None):
    return SourceRecord(role, index, index + 1, index + 1, "", (), ffid if ffid is not None else str(100 + index),
                        x, y, classification)


PARAMS = AnalysisParameters(3.125)


def test_record_level_only_valid_reference_rows_take_part_and_rows_keep_their_identity():
    ref = [rec(REFERENCE, 0, 0, 0), rec(REFERENCE, 1, 0, 0, "INVALID"), rec(REFERENCE, 2, 3.1, 0),
           rec(REFERENCE, 3, 0, 0, "NO_SHOT")]
    tgt = [rec(TARGET, 0, 0, 0), rec(TARGET, 1, 3.1, 0), rec(TARGET, 2, 6.2, 0)]
    result = align_records(ref, tgt, PARAMS)
    assert result.complete and result.reference_valid == 2
    assert {a.reference_row: a.target_row for a in result.associations} == {0: 0, 2: 1}
    assert set(result.by_target) == {0, 1}


def test_record_level_incomplete_when_target_has_fewer_rows_than_valid_reference_records():
    ref = [rec(REFERENCE, i, 3.125 * i, 0) for i in range(4)]
    tgt = [rec(TARGET, i, 3.125 * i, 0) for i in range(3)]
    result = align_records(ref, tgt, PARAMS)
    assert not result.complete and result.direction == "TARGET_TO_REFERENCE"
    assert len(result.associations) == 3 and len(result.unplaced_reference_rows) == 1
    assert len(set(a.target_row for a in result.associations)) == 3
