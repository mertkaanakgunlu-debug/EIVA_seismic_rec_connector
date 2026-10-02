"""Directional, ordered, one-to-one alignment: reference records -> target rows.

Authority model
    Every valid reference record is a real shot and its FFID is authoritative.  Distance ranks candidate target rows;
    it is never an existence test, and no threshold rejects a reference record.

Hierarchy of evidence, strongest first
    1. Spatial proximity.  The full-precision distance |R[i] - T[j]| is the primary association signal.  A target row
       is a candidate for a reference record when it lies within ``cap``; the closer the better.
    2. One-to-one (mandatory).  A target row is used at most once.
    3. Acquisition order.  Associations never cross: the map from reference rows to target rows is strictly increasing.
       This is a consistency constraint, not a lag model.  Nothing assumes a stable offset between the two files, and
       any number of target rows may lie between two consecutive associated records (the recorder may have been
       offline while the navigation log kept running).  Unused target rows cost nothing.
    4. Sequence context.  Reference records without usable spatial evidence (anomalous coordinate, target row without a
       position) take the free target rows between their associated neighbours, and exact ties go to the earliest row.

Objective
    A candidate pair (i, j) has gain ``cap - |R[i] - T[j]|``: distances saturate at ``cap``, beyond which a coordinate
    stops preferring one row over another.  The alignment is the strictly increasing chain of pairs with the largest total
    gain, which is the assignment of minimum total cost when a reference record placed on row j costs min(distance, cap)
    and an unassigned one costs cap.  The optimum is found exactly by a weighted longest-chain dynamic programme over the
    candidate pairs, O(P log n) for P pairs; it needs no band, window or lag, so a stretch of unused target rows of any
    length costs nothing.

    Reference records the chain leaves out take free target rows lying between their chained neighbours, left to right
    (the sequence fallback; their basis is SEQUENCE).  A record stays unassigned only when no such free row exists, that
    is, when giving it a row would take a better-fitting row away from another record.  Such records are reported with the
    price of making room for them (how many other records would have to move one row, and how much distance that adds), so
    the trade-off is visible instead of being decided silently.
"""

from dataclasses import dataclass, field
import math
from typing import Optional, Sequence

from config import AMBIGUITY_MARGIN_M
from .models import SourceRecord, VALID

UNIT = 10 ** 9                       # integer cost units per metre (nanometre resolution)
MAX_ALTERNATIVES = 4
MAX_CANDIDATES_PER_ROW = 128         # nearest candidates kept per reference record (a bound for degenerate data)
MAX_CANDIDATE_PAIRS = 3_000_000
MAX_EXAMINED_PAIRS = 40_000_000      # distance evaluations allowed while looking for candidates
MAX_SHIFT_SCAN = 20_000              # records examined when pricing the shift that would make room for one

SPATIAL, SEQUENCE = "SPATIAL", "SEQUENCE"

Point = Optional[tuple[float, float]]


@dataclass(frozen=True, slots=True)
class Unplaced:
    """Why a reference record has no target row, and what giving it one would cost the others."""
    nearest_target: Optional[int]       # nearest target row within the spatial range, if any
    nearest_distance_m: Optional[float]
    shift_records: Optional[int] = None     # records that would each have to move one target row to make room
    shift_cost_m: Optional[float] = None    # distance that moving them would add in total
    shift_end: Optional[int] = None         # the unused target row that absorbs the shift
    shift_side: Optional[str] = None        # AFTER or BEFORE the unplaced record


@dataclass
class PointAlignment:
    """Alignment of two coordinate sequences; every list is indexed by reference row."""
    targets: list[Optional[int]]                 # target index, None when the record could not be given a row
    distance_m: list[Optional[float]]            # true distance, None when a position is unknown
    basis: list[Optional[str]]                   # SPATIAL (ranked by distance) or SEQUENCE (placed by continuity)
    alternatives: list[tuple[int, ...]]          # other target rows that fit equally well
    unplaced: dict[int, Unplaced] = field(default_factory=dict)
    cost_units: int = 0
    pairs: int = 0                               # candidate pairs examined


class _MaxTree:
    """Fenwick tree for prefix maxima that also remembers where each maximum came from."""
    __slots__ = ("size", "value", "origin")

    def __init__(self, size: int):
        self.size, self.value, self.origin = size, [0] * (size + 1), [-1] * (size + 1)

    def update(self, position: int, value: int, origin: int):
        position += 1
        while position <= self.size:
            if value > self.value[position]:
                self.value[position], self.origin[position] = value, origin
            position += position & -position

    def best_before(self, position: int) -> tuple[int, int]:
        """Largest value stored at a position below ``position``: (0, -1) when there is none."""
        best, origin = 0, -1
        while position > 0:
            if self.value[position] > best:
                best, origin = self.value[position], self.origin[position]
            position -= position & -position
        return best, origin


def _candidate_pairs(a_pts: Sequence[Point], b_pts: Sequence[Point], cap_m: float, cap_units: int, per_row: int):
    """For every reference row, the target rows within ``cap``: [(distance_units, target, distance_m)], nearest first."""
    cell = cap_m
    grid: dict[tuple[int, int], list[int]] = {}
    for j, p in enumerate(b_pts):
        if p is not None:
            grid.setdefault((math.floor(p[0] / cell), math.floor(p[1] / cell)), []).append(j)
    examined = 0
    for p in a_pts:
        if p is not None:
            cx, cy = math.floor(p[0] / cell), math.floor(p[1] / cell)
            examined += sum(len(grid.get((gx, gy), ())) for gx in (cx - 1, cx, cx + 1) for gy in (cy - 1, cy, cy + 1))
    if examined > MAX_EXAMINED_PAIRS:
        raise ValueError(f"{examined:,} distance comparisons would be needed to find the target rows within {cap_m:g} m of "
                         "the recorder records; check the entered shot interval")
    hypot, rows = math.hypot, []
    for p in a_pts:
        found = []
        if p is not None:
            cx, cy = math.floor(p[0] / cell), math.floor(p[1] / cell)
            for gx in (cx - 1, cx, cx + 1):
                for gy in (cy - 1, cy, cy + 1):
                    for j in grid.get((gx, gy), ()):
                        q = b_pts[j]
                        d = hypot(p[0] - q[0], p[1] - q[1])
                        units = round(d * UNIT) if d < cap_m else cap_units
                        if units < cap_units:
                            found.append((units, j, d))
            found.sort()
            del found[per_row:]
        rows.append(found)
    return rows


def _fit(a: Point, b: Point, cap_m: float) -> float:
    """Saturating distance in metres: ``cap`` when either position is unknown or the distance reaches it."""
    if a is None or b is None:
        return cap_m
    return min(math.hypot(a[0] - b[0], a[1] - b[1]), cap_m)


def _shift(start: int, step: int, owner: dict[int, int], a_pts, b_pts, cap_m: float):
    """Price moving the records on consecutive used target rows from ``start`` by ``step`` (+1 or -1) until a row is free.

    Returns (records moved, added distance in metres, the free row) or None when no free row lies that way."""
    n = len(b_pts)
    moved, added, t = 0, 0.0, start
    while 0 <= t < n and t in owner and moved <= MAX_SHIFT_SCAN:
        nxt = t + step
        if not 0 <= nxt < n:
            return None
        r = owner[t]
        added += _fit(a_pts[r], b_pts[nxt], cap_m) - _fit(a_pts[r], b_pts[t], cap_m)
        moved += 1
        t = nxt
    return (moved, added, t) if 0 <= t < n and t not in owner else None


def _price_unplaced(a_pts, b_pts, cap_m: float, targets, candidates) -> dict[int, Unplaced]:
    """For every unassigned reference row: its nearest target row and the cost of making room for it.

    Making room means moving the records between it and the nearest unused target row, each by one row, to rows that fit
    them worse.  That is exactly what insisting that every record keeps a row would do, so its price is shown rather than
    paid silently.  Only a record that is alone between its assigned neighbours is priced."""
    m = len(targets)
    owner = {j: i for i, j in enumerate(targets) if j is not None}
    unplaced: dict[int, Unplaced] = {}
    before, i = None, 0                        # before: the nearest assigned record above position i
    while i < m:
        if targets[i] is not None:
            before, i = i, i + 1
            continue
        end = i                                # records i .. end-1 are unassigned
        while end < m and targets[end] is None:
            end += 1
        after = end if end < m else None
        for k in range(i, end):
            nearest = candidates[k][0] if candidates[k] else None
            info = Unplaced(nearest[1] if nearest else None, nearest[2] if nearest else None)
            if end - i == 1:
                priced = []
                if after is not None:
                    priced.append(("AFTER", _shift(targets[after], +1, owner, a_pts, b_pts, cap_m)))
                if before is not None:
                    priced.append(("BEFORE", _shift(targets[before], -1, owner, a_pts, b_pts, cap_m)))
                priced = [(side, option) for side, option in priced if option]
                if priced:
                    side, (moved, added, free) = min(priced, key=lambda item: item[1][1])
                    info = Unplaced(info.nearest_target, info.nearest_distance_m, moved, added, free, side)
            unplaced[k] = info
        i = end
    return unplaced


def _primary(composite: int, scale: int) -> int:
    """The spatial part of a composite weight (``gain * scale - sum of target indices``), rounded up."""
    return -((-composite) // scale)


def align_points(a_pts: Sequence[Point], b_pts: Sequence[Point], cap_m: float,
                 ambiguity_margin_m: float = AMBIGUITY_MARGIN_M, per_row: Optional[int] = None) -> PointAlignment:
    """Place reference points ``a_pts`` on distinct, order-preserving target points ``b_pts`` (see the module docstring)."""
    m, n = len(a_pts), len(b_pts)
    cap_units = round(cap_m * UNIT)
    margin_units = round(ambiguity_margin_m * UNIT)
    if per_row is None:
        per_row = max(16, min(MAX_CANDIDATES_PER_ROW, MAX_CANDIDATE_PAIRS // max(m, 1)))
    candidates = _candidate_pairs(a_pts, b_pts, cap_m, cap_units, per_row)

    # Pair table.  The weight is the gain scaled so that, among alignments of equal total gain, the one whose rows
    # lie earliest in the target sequence is larger (unused rows are skipped as late as possible).
    scale = m * n + 1
    pair_row, pair_target, pair_weight, row_pairs = [], [], [], []
    for i, found in enumerate(candidates):
        ids = []
        for units, j, _ in sorted(found, key=lambda item: item[1]):
            ids.append(len(pair_row))
            pair_row.append(i)
            pair_target.append(j)
            pair_weight.append((cap_units - units) * scale - j)
        row_pairs.append(ids)
    count = len(pair_row)

    # Best chain ending at each pair (forward) and starting at each pair (backward).  A row's pairs all query before any
    # of them is stored, so a chain never uses two pairs of one reference row.
    forward, before = [0] * count, [-1] * count
    tree = _MaxTree(n)
    for ids in row_pairs:
        for pid in ids:
            best, origin = tree.best_before(pair_target[pid])
            forward[pid], before[pid] = pair_weight[pid] + best, origin
        for pid in ids:
            tree.update(pair_target[pid], forward[pid], pid)
    backward = [0] * count
    tree = _MaxTree(n)
    for ids in reversed(row_pairs):
        for pid in ids:
            backward[pid] = pair_weight[pid] + tree.best_before(n - 1 - pair_target[pid])[0]
        for pid in ids:
            tree.update(n - 1 - pair_target[pid], backward[pid], pid)

    chain: list[int] = []
    optimum = 0
    if count:
        last = max(range(count), key=lambda pid: (forward[pid], -pid))
        optimum = forward[last]
        while last != -1:
            chain.append(last)
            last = before[last]
        chain.reverse()
    best_primary = _primary(optimum, scale)

    targets: list[Optional[int]] = [None] * m
    basis: list[Optional[str]] = [None] * m
    alternatives: list[tuple[int, ...]] = [()] * m
    for pid in chain:
        i = pair_row[pid]
        targets[i], basis[i] = pair_target[pid], SPATIAL
        rivals = []
        for other in row_pairs[i]:
            if other != pid:
                regret = best_primary - _primary(forward[other] + backward[other] - pair_weight[other], scale)
                if regret <= margin_units:
                    rivals.append((regret, pair_target[other]))
        rivals.sort()
        alternatives[i] = tuple(j for _, j in rivals[:MAX_ALTERNATIVES])

    # Sequence fallback: records without spatial support take the free rows between their chained neighbours.
    anchors = [(-1, -1)] + [(pair_row[pid], pair_target[pid]) for pid in chain] + [(m, n)]
    for (row_a, target_a), (row_b, target_b) in zip(anchors, anchors[1:]):
        pending, free = range(row_a + 1, row_b), range(target_a + 1, target_b)
        spare = len(free) - len(pending)
        for k in range(min(len(pending), len(free))):
            targets[pending[k]], basis[pending[k]] = free[k], SEQUENCE
            if spare > 0:           # more free rows than records: where the record sits among them is undetermined
                alternatives[pending[k]] = tuple(free[k + s] for s in range(1, min(spare, MAX_ALTERNATIVES) + 1))

    distance_m: list[Optional[float]] = [None] * m
    cost = 0
    for i, j in enumerate(targets):
        if j is None:
            cost += cap_units
            continue
        a, b = a_pts[i], b_pts[j]
        if a is not None and b is not None:
            distance_m[i] = math.hypot(a[0] - b[0], a[1] - b[1])
        cost += round(distance_m[i] * UNIT) if distance_m[i] is not None and distance_m[i] < cap_m else cap_units

    unplaced = _price_unplaced(a_pts, b_pts, cap_m, targets, candidates)
    return PointAlignment(targets, distance_m, basis, alternatives, unplaced, cost, count)


# ----------------------------------------------------------------------------------------------------------
# Record level
# ----------------------------------------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Association:
    """One authoritative reference record placed on one target row."""
    reference_row: int                 # SourceRecord.row_index of the reference record
    target_row: int                    # SourceRecord.row_index of the target row
    distance_m: Optional[float]        # full-precision distance; None when a position is unknown
    basis: str                         # SPATIAL: distance ranked the candidates; SEQUENCE: placed by continuity
    ambiguous: bool                    # another placement of (nearly) equal total fit exists
    alternative_target_rows: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class UnplacedReference:
    """A valid reference record that has no target row, with the evidence needed to understand why.

    ``shift_*`` price making room for it: ``shift_records`` other records would each have to move one target row (the
    ones AFTER or BEFORE it, up to the unused target row ``shift_end_row``), adding ``shift_cost_m`` of total distance."""
    reference_row: int
    nearest_target_row: Optional[int]
    nearest_distance_m: Optional[float]
    shift_records: Optional[int] = None
    shift_cost_m: Optional[float] = None
    shift_end_row: Optional[int] = None
    shift_side: Optional[str] = None


@dataclass
class AlignmentResult:
    associations: list[Association] = field(default_factory=list)       # ordered by reference row
    by_reference: dict[int, Association] = field(default_factory=dict)
    by_target: dict[int, Association] = field(default_factory=dict)
    unplaced_reference_rows: list[int] = field(default_factory=list)    # valid reference records without a target row
    unplaced: dict[int, UnplacedReference] = field(default_factory=dict)
    reference_valid: int = 0
    target_rows: int = 0
    complete: bool = True                                                # every valid reference record has a target row
    direction: str = "REFERENCE_TO_TARGET"
    cost_m: float = 0.0                                                  # total saturating distance incl. cap per unassigned


def _point(record: SourceRecord) -> Point:
    return (record.x, record.y) if record.has_position else None


def align_records(reference: Sequence[SourceRecord], target: Sequence[SourceRecord], parameters) -> AlignmentResult:
    """Associate valid reference records with distinct target rows, preserving acquisition order.

    Reference rows that are not VALID (unparseable, or marked "no shot") take no part.  Target rows with an unknown
    position remain candidates: their place in the sequence is still evidence."""
    pool = [r for r in reference if r.classification == VALID]
    result = AlignmentResult(reference_valid=len(pool), target_rows=len(target))
    if not pool or not target:
        result.complete = not pool
        result.unplaced_reference_rows = [r.row_index for r in pool]
        result.unplaced = {r.row_index: UnplacedReference(r.row_index, None, None) for r in pool}
        return result
    outcome = align_points([_point(r) for r in pool], [_point(t) for t in target], parameters.alignment_cap_m)
    for k, record in enumerate(pool):
        j = outcome.targets[k]
        if j is None:
            detail = outcome.unplaced[k]
            result.unplaced_reference_rows.append(record.row_index)
            result.unplaced[record.row_index] = UnplacedReference(
                record.row_index, None if detail.nearest_target is None else target[detail.nearest_target].row_index,
                detail.nearest_distance_m, detail.shift_records, detail.shift_cost_m,
                None if detail.shift_end is None else target[detail.shift_end].row_index, detail.shift_side)
            continue
        result.associations.append(Association(record.row_index, target[j].row_index, outcome.distance_m[k], outcome.basis[k],
                                               bool(outcome.alternatives[k]), tuple(target[x].row_index for x in outcome.alternatives[k])))
    result.complete = not result.unplaced_reference_rows
    result.cost_m = outcome.cost_units / UNIT
    result.by_reference = {a.reference_row: a for a in result.associations}
    result.by_target = {a.target_row: a for a in result.associations}
    return result
