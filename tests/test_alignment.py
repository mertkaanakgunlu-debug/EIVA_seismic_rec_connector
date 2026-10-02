"""Directional ordered one-to-one alignment (reference -> target): spatial proximity first.

The low-level tests use plain coordinate tuples so they exercise the algorithm and nothing else: no file formats, no
vendor names.  The brute-force oracle enumerates every order-preserving one-to-one (partial) assignment on small random
instances and checks that the chain search reaches the true minimum of the documented cost: a record placed on a row costs
min(distance, cap) and an unassigned record costs cap.
"""
import math
import random
import time

import pytest

import shotlogfixer.alignment as alignment_module
from shotlogfixer.alignment import SEQUENCE, SPATIAL, UNIT, align_points, align_records
from shotlogfixer.analysis_parameters import AnalysisParameters
from shotlogfixer.models import REFERENCE, TARGET, SourceRecord

CAP = 15.625  # 5 x 3.125 m
SPACING = 3.125


def line(count, step=SPACING, x0=1000.0, y0=2000.0):
    return [(x0 + step * i, y0) for i in range(count)]


def cost_units(a, b, cap=CAP):
    if a is None or b is None:
        return round(cap * UNIT)
    d = math.hypot(a[0] - b[0], a[1] - b[1])
    return round(cap * UNIT) if d >= cap else round(d * UNIT)


def partial_matchings(m, n, first_row=0, first_target=0):
    """Every strictly increasing partial assignment of reference rows to target rows."""
    if first_row == m:
        yield []
        return
    yield from partial_matchings(m, n, first_row + 1, first_target)               # this record stays unassigned
    for j in range(first_target, n):
        for rest in partial_matchings(m, n, first_row + 1, j + 1):
            yield [(first_row, j)] + rest


def matching_cost(a_pts, b_pts, matching, cap=CAP):
    return (sum(cost_units(a_pts[i], b_pts[j], cap) for i, j in matching)
            + (len(a_pts) - len(matching)) * round(cap * UNIT))


def brute_force_minimum(a_pts, b_pts, cap=CAP):
    return min(matching_cost(a_pts, b_pts, matching, cap) for matching in partial_matchings(len(a_pts), len(b_pts)))


# ---------------------------------------------------------------------------------------------------
# Invariants and the exhaustive oracle
# ---------------------------------------------------------------------------------------------------

def assert_valid(out, m, n):
    assert len(out.targets) == m
    assigned = [t for t in out.targets if t is not None]
    assert len(set(assigned)) == len(assigned), "one target row must never be used twice"
    assert all(a < b for a, b in zip(assigned, assigned[1:])), "assignment must preserve acquisition order"
    assert all(0 <= t < n for t in assigned)
    pairs = [(i, j) for i, j in enumerate(out.targets) if j is not None]
    anchors = [(-1, -1)] + pairs + [(m, n)]
    for (ia, ja), (ib, jb) in zip(anchors, anchors[1:]):
        assert not (ib - ia > 1 and jb - ja > 1), "a record was left unassigned although a free row lay between its neighbours"


@pytest.mark.parametrize("seed", range(250))
def test_alignment_matches_exhaustive_minimum_on_random_instances(seed):
    rng = random.Random(seed)
    m = rng.randint(1, 6)
    n = rng.randint(max(1, m - 2), m + 4)               # sometimes fewer target rows than reference records
    base = line(n, step=rng.choice([1.0, 3.125, 5.0]))
    a_pts = []
    for k in range(m):
        x, y = base[min(k, n - 1)] if rng.random() < 0.8 else base[rng.randrange(n)]   # duplicates make real conflicts
        r = rng.random()
        if r < 0.15:                      # gross anomaly: far away
            a_pts.append((x + rng.uniform(80, 300), y + rng.uniform(-300, 300)))
        elif r < 0.30:                    # moderately wrong coordinate
            a_pts.append((x + rng.uniform(-6, 6), y + rng.uniform(-6, 6)))
        else:
            a_pts.append((x + rng.gauss(0, 0.4), y + rng.gauss(0, 0.4)))
    b_pts = list(base)
    for k in rng.sample(range(n), rng.randint(0, 1)):
        b_pts[k] = None                   # a target row without a usable position stays a candidate
    out = align_points(a_pts, b_pts, CAP)
    assert_valid(out, m, n)
    assert out.cost_units == brute_force_minimum(a_pts, b_pts), "must reach the exhaustive minimum of the documented cost"
    pairs = [(i, j) for i, j in enumerate(out.targets) if j is not None]
    assert matching_cost(a_pts, b_pts, pairs) == out.cost_units, "reported cost must equal the cost of the returned assignment"


def test_ties_break_deterministically():
    a = [(0.0, 0.0), (10.0, 0.0)]
    b = [(0.0, 0.0), (0.0, 0.0), (10.0, 0.0)]
    first = align_points(a, b, CAP)
    assert first.targets == align_points(a, b, CAP).targets
    assert first.targets == [0, 2], "equal-fit placements prefer the earliest rows (unused rows are skipped as late as possible)"


# ---------------------------------------------------------------------------------------------------
# Required behaviours (cases 1-7 of the brief)
# ---------------------------------------------------------------------------------------------------

def test_case1_normal_nearest_alignment():
    ref = [(1000.0, 2000.0), (1003.1, 2000.0), (1006.3, 2000.0)]
    tgt = [(1000.2, 2000.1), (1003.0, 1999.9), (1006.4, 2000.0)]
    out = align_points(ref, tgt, CAP)
    assert out.targets == [0, 1, 2]
    assert out.basis == [SPATIAL] * 3
    assert all(not alts for alts in out.alternatives)


@pytest.mark.parametrize("extra_at", [0, 1, 2, 3])
def test_case2_extra_target_row_is_the_one_left_unassigned(extra_at):
    pts = line(3)
    tgt = list(pts)
    tgt.insert(extra_at, (pts[0][0] - 1.5 + extra_at * 3.125, 2040.0))   # an extra shot well off the line
    out = align_points(pts, tgt, CAP)
    assert_valid(out, 3, 4)
    assert extra_at not in out.targets
    assert all(t is not None for t in out.targets)


def test_case4_recorder_coordinate_anomaly_keeps_the_sequence_consistent_row():
    ref = line(6)
    ref[3] = (ref[3][0] + 200.0, ref[3][1] + 80.0)            # one coordinate jumps ~215 m
    out = align_points(ref, line(6), CAP)
    assert out.targets == [0, 1, 2, 3, 4, 5]
    assert out.basis[3] == SEQUENCE and out.distance_m[3] > 200
    assert [out.basis[i] for i in (0, 1, 2, 4, 5)] == [SPATIAL] * 5


def test_case4_anomaly_between_clean_neighbours_takes_the_only_row_between_them():
    ref = line(6)
    ref[3] = (ref[3][0] + 200.0, ref[3][1])
    out = align_points(ref, line(8), CAP)                        # two spare rows exist after the sequence
    assert out.targets == [0, 1, 2, 3, 4, 5], "its clean neighbours leave exactly one row for it"
    assert out.basis[3] == SEQUENCE and not out.alternatives[3]


def test_case4_terminal_anomaly_is_retained_and_takes_the_next_free_row():
    ref = line(5)
    ref[4] = (ref[4][0] + 180.0, ref[4][1] + 100.0)            # last record jumps ~205 m
    out = align_points(ref, line(7), CAP)                       # two spare target rows after the anomalous record
    assert out.targets == [0, 1, 2, 3, 4], "the terminal record takes the first free row; trailing rows stay unused"
    assert out.basis[4] == SEQUENCE
    assert out.alternatives[4] == (5, 6), "its placement among the trailing rows is flagged as ambiguous"


def test_case5_competing_nearest_candidates_resolve_one_to_one_by_order():
    # Independent nearest-neighbour matching would give both reference rows the same target row (10.2).
    ref = [(10.0, 0.0), (10.3, 0.0)]
    tgt = [(9.0, 0.0), (10.2, 0.0), (11.0, 0.0)]
    nearest = [min(range(3), key=lambda j: abs(tgt[j][0] - r[0])) for r in ref]
    assert nearest == [1, 1], "the scenario really is a nearest-neighbour collision"
    out = align_points(ref, tgt, CAP)
    assert out.targets == [1, 2]


def test_case6_full_decimal_precision_decides_between_candidates():
    # Same integer easting/northing for both candidates; only the decimals separate them.
    ref = [(615190.23, 4645679.70)]
    tgt = [(615190.90, 4645679.20), (615190.10, 4645679.75)]
    out = align_points(ref, tgt, CAP)
    assert out.targets == [1]
    assert out.distance_m[0] == pytest.approx(math.hypot(0.13, 0.05))


def test_case7_large_distance_but_deterministic_sequence_is_still_assigned():
    ref = line(4)
    ref[1] = (ref[1][0] + 1000.0, ref[1][1] - 1000.0)
    out = align_points(ref, line(4), CAP)
    assert out.targets == [0, 1, 2, 3]
    assert out.basis[1] == SEQUENCE


def test_unusable_target_position_is_a_candidate_placed_by_sequence():
    ref = line(3)
    out = align_points(ref, [ref[0], None, ref[2]], CAP)
    assert out.targets == [0, 1, 2]
    assert out.basis[1] == SEQUENCE and out.distance_m[1] is None


def test_no_distance_threshold_can_reject_a_reference_record():
    ref = [(0.0, 0.0), (1.0e6, 1.0e6), (6.0, 0.0)]
    tgt = [(0.0, 0.0), (3.0, 0.0), (6.0, 0.0)]
    assert align_points(ref, tgt, 0.001).targets == [0, 1, 2]
    assert align_points(ref, tgt, 1.0e9).targets == [0, 1, 2]


def test_min_marginal_ambiguity_marks_only_genuinely_competing_placements():
    # Two identical spare rows around a reference point: the placement is genuinely ambiguous.
    out = align_points([(0.0, 0.0)], [(0.0, 0.0), (0.0, 0.0)], CAP)
    assert out.targets == [0] and out.alternatives[0] == (1,)
    # A forced placement (no spare rows) can never be ambiguous, however similar the points are.
    forced = align_points([(0.0, 0.0), (0.0, 0.1)], [(0.0, 0.0), (0.0, 0.1)], CAP)
    assert forced.alternatives == [(), ()]


# ---------------------------------------------------------------------------------------------------
# Spatial proximity first: no lag, no penalty for unused target rows
# ---------------------------------------------------------------------------------------------------

def test_recorder_outage_pairs_each_shot_with_the_row_at_its_position():
    """Recorder FFID 105 follows 104 after a ten minute outage while the navigation log kept running."""
    base = line(400)
    chosen = [0, 1, 2, 3, 4, 5, 107, 108, 109, 250, 251, 399]          # ~100 and ~140 unused rows between shots
    ref = [(base[j][0] + 0.2, base[j][1] - 0.1) for j in chosen]
    out = align_points(ref, base, CAP)
    assert out.targets == chosen
    assert out.basis == [SPATIAL] * len(chosen)
    assert chosen[6] - chosen[5] == 102, "the reference record after the outage sits 102 rows further on"


@pytest.mark.parametrize("seed", range(6))
def test_any_number_of_unused_target_rows_costs_nothing(seed):
    rng = random.Random(seed)
    n = 3000
    base = line(n, step=2.5)
    chosen, j = [], rng.randrange(0, 20)
    while j < n and len(chosen) < 600:
        chosen.append(j)
        j += 1 + rng.choice([0, 0, 0, 0, 1, 2, 7, 40, 150])         # long runs of rows the recorder never saw
    ref = [(base[j][0] + rng.gauss(0, 0.2), base[j][1] + rng.gauss(0, 0.2)) for j in chosen]
    out = align_points(ref, base, 12.5)
    assert out.targets == chosen, "no stable lag is assumed: every record goes to the row at its own position"
    assert_valid(out, len(ref), n)


def test_a_row_index_lag_never_outweighs_a_better_spatial_match():
    """The recorder is one shot ahead of the target labels; spatial proximity, not the row index, decides."""
    base = line(60)
    ref = [base[i + 1] for i in range(58)]                      # reference i sits on target row i + 1
    out = align_points(ref, base, CAP)
    assert out.targets == [i + 1 for i in range(58)]
    assert all(d == pytest.approx(0.0) for d in out.distance_m)


def displaced_instance(rows_to_ghost, count=60):
    """A reference shot recorded twice at one place where the target has a single row, and a spare target row later.

    Insisting that every reference record keeps a row would shift every record between the two by one row.  The second
    recording sits 0.3 m off, so it is the one that has no row."""
    base = line(count)
    k = 10
    duplicate = (base[k][0] + 0.3, base[k][1])
    reference = base[:k + 1] + [duplicate] + base[k + 1:]
    ghost_at = k + 1 + rows_to_ghost
    ghost = (base[ghost_at - 1][0] + 0.5, base[ghost_at - 1][1])               # a spare target row on the track
    target = base[:ghost_at] + [ghost] + base[ghost_at:]
    return reference, target, k + 1, ghost_at


def test_an_unplaceable_record_never_displaces_better_fitting_neighbours():
    reference, target, orphan, ghost_at = displaced_instance(rows_to_ghost=40, count=80)
    out = align_points(reference, target, CAP)
    assert_valid(out, len(reference), len(target))
    assert [i for i, t in enumerate(out.targets) if t is None] == [orphan]
    # Every other record sits exactly on its own position: not one of the 40 records between was moved.
    assert max(d for i, d in enumerate(out.distance_m) if i != orphan) == pytest.approx(0.0, abs=1e-9)
    price = out.unplaced[orphan]
    assert price.shift_side == "AFTER" and price.shift_records == 40
    assert price.shift_cost_m == pytest.approx(39 * SPACING + 0.5), "39 records move a full spacing, the last onto the spare row"
    assert price.shift_end == ghost_at, "the shift would end at the spare row"


@pytest.mark.parametrize("rows_to_ghost", [1, 2, 3])
def test_a_short_displacement_is_preferred_to_leaving_a_record_unassigned(rows_to_ghost):
    reference, target, _, _ = displaced_instance(rows_to_ghost)
    out = align_points(reference, target, CAP)
    assert_valid(out, len(reference), len(target))
    assert all(t is not None for t in out.targets), "making room costs less than an unplaced record, so every record keeps a row"


@pytest.mark.parametrize("rows_to_ghost", [6, 12, 30])
def test_a_long_displacement_is_not_worth_one_record(rows_to_ghost):
    reference, target, orphan, _ = displaced_instance(rows_to_ghost)
    out = align_points(reference, target, CAP)
    assert [i for i, t in enumerate(out.targets) if t is None] == [orphan]
    assert out.unplaced[orphan].shift_records == rows_to_ghost


def test_terminal_record_without_a_free_row_is_left_unassigned_and_priced():
    """The last reference record has an anomalous coordinate and the target already ends at the previous shot."""
    base = line(50)
    ghost = (base[19][0] + 0.5, base[19][1])
    target = base[:20] + [ghost] + base[20:]                                     # 51 rows; the spare one is on the track
    reference = base + [(base[-1][0] + 400.0, base[-1][1] + 100.0)]              # 51 records, the last one anomalous
    out = align_points(reference, target, CAP)
    assert [i for i, t in enumerate(out.targets) if t is None] == [50]
    price = out.unplaced[50]
    assert price.nearest_target is None, "no target row lies within the spatial range of its coordinate"
    assert price.shift_side == "BEFORE" and price.shift_records == 30 and price.shift_end == 20
    assert price.shift_cost_m == pytest.approx(29 * SPACING + (SPACING - 0.5))


def test_more_reference_records_than_target_rows_leaves_the_worst_fitting_ones_unassigned():
    ref, tgt = line(6), line(6)[:3] + line(6)[4:]                                # the target lacks row 3
    out = align_points(ref, tgt, CAP)
    assert_valid(out, 6, 5)
    assert sum(t is None for t in out.targets) == 1
    assert out.targets[:3] == [0, 1, 2]


def test_no_spatial_evidence_at_all_falls_back_to_sequence_order():
    ref = [(i * 1000.0, 5.0e6) for i in range(4)]
    out = align_points(ref, line(6), CAP)
    assert out.targets == [0, 1, 2, 3] and out.basis == [SEQUENCE] * 4
    assert out.alternatives[0] == (1, 2), "which free rows they take is undetermined, so the placement is flagged"


def test_candidate_truncation_still_gives_a_valid_assignment():
    ref, tgt = line(40, step=0.2), line(60, step=0.2)
    out = align_points(ref, tgt, CAP, per_row=2)
    assert_valid(out, 40, 60)


def test_a_wrongly_entered_shot_interval_fails_fast_instead_of_hanging(monkeypatch):
    monkeypatch.setattr(alignment_module, "MAX_EXAMINED_PAIRS", 50)
    with pytest.raises(ValueError, match="shot interval"):
        align_points(line(30), line(30), CAP)


def test_large_files_with_long_outages_are_aligned_quickly_and_exactly():
    n, m = 20_000, 6_000
    base = line(n)
    chosen = sorted(random.Random(7).sample(range(n), m))
    started = time.perf_counter()
    out = align_points([base[j] for j in chosen], base, CAP)
    assert time.perf_counter() - started < 20
    assert out.targets == chosen


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
    assert result.complete and result.reference_valid == 2 and result.direction == "REFERENCE_TO_TARGET"
    assert {a.reference_row: a.target_row for a in result.associations} == {0: 0, 2: 1}
    assert set(result.by_target) == {0, 1}


def test_record_level_unassigned_records_are_reported_with_their_evidence():
    ref = [rec(REFERENCE, i, 3.125 * i, 0) for i in range(4)]
    tgt = [rec(TARGET, i, 3.125 * i, 0) for i in range(3)]
    result = align_records(ref, tgt, PARAMS)
    assert not result.complete and result.direction == "REFERENCE_TO_TARGET"
    assert len(result.associations) == 3 and len(result.unplaced_reference_rows) == 1
    assert len(set(a.target_row for a in result.associations)) == 3
    (row,) = result.unplaced_reference_rows
    assert result.unplaced[row].reference_row == row
    assert result.cost_m >= PARAMS.alignment_cap_m, "an unassigned record is charged the saturated cost"


def test_record_level_outage_keeps_each_record_on_the_row_at_its_position():
    ref = [rec(REFERENCE, 0, 0, 0), rec(REFERENCE, 1, 3.1, 0), rec(REFERENCE, 2, 312.5, 0)]       # FFID 100, 101, 102
    tgt = [rec(TARGET, i, 3.125 * i, 0, ffid=900 + i) for i in range(102)]                        # the log kept running
    result = align_records(ref, tgt, PARAMS)
    assert {a.reference_row: a.target_row for a in result.associations} == {0: 0, 1: 1, 2: 100}
    assert result.complete
