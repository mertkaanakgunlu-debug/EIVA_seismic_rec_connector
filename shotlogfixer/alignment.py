"""Directional, ordered, one-to-one alignment: reference records -> target rows.

Authority model
    Every valid reference record is a real shot, so every one of them must receive a target row whenever a
    one-to-one, order-preserving assignment exists.  Distance is a ranking signal, never an existence test:
    no threshold ever rejects a reference record.

Formulation
    Reference rows R[0..m-1] and target rows T[0..n-1] are ordered acquisition sequences.  A valid assignment
    is a strictly increasing map f: R -> T (one-to-one and monotone), so f(i) = i + d_i with offsets
    0 <= d_0 <= d_1 <= ... <= d_{m-1} <= s = n - m.  Exactly s target rows stay unassigned.

Cost (minimised exactly by dynamic programming over the offsets)
    * spatial: the full-precision distance |R[i] - T[f(i)]|, saturating at ``cap``.  Beyond ``cap`` a coordinate
      stops preferring one candidate over another, so a single anomalous coordinate cannot drag the assignments of
      its neighbours; the sequence then decides.  A target row without a usable position costs ``cap``.
    * sequence continuity: a one-unit (one nanometre) charge for every place where the offset increases, i.e. where
      a run of target rows is skipped.  It never outweighs real spatial evidence; it only prefers the most
      continuous assignment, with skips as late as possible, when the spatial evidence is flat.
    Costs are integers, so ties break deterministically.

Because the offsets form a non-decreasing sequence, the DP has m x (s + 1) states.  When the slack s is very large the
search is restricted to a corridor around a robust spatial trajectory (see ``_corridor_windows``); the result is
still a valid one-to-one monotone assignment.

When there are more reference than target rows the same machinery embeds the shorter (target) sequence into the
reference sequence, producing a partial result in which the unplaced valid reference records are reported as blocked.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
import math
from typing import Optional, Sequence

from config import AMBIGUITY_MARGIN_M
from .models import SourceRecord, VALID

UNIT = 10 ** 9            # integer cost units per metre (nanometre resolution)
SKIP_EVENT_COST = 1       # one unit per skip event: a tie-breaker only
FULL_BAND_MAX_SLACK = 192  # up to this slack every offset is searched exactly
MAX_EXACT_STATES = 6_000_000  # exact DP table budget (cells); larger problems use the corridor
CORRIDOR_HALF_WIDTH = 24
MAX_ALTERNATIVES = 4
_INF = 1 << 100

Point = Optional[tuple[float, float]]


@dataclass
class Embedding:
    """Result of embedding sequence ``a`` into the longer sequence ``b`` (every ``a`` row placed)."""
    targets: list[int]                         # index in b for every a row
    distance_m: list[Optional[float]]          # true (uncapped) distance, None when a position is unknown
    saturated: list[bool]                      # spatial evidence unusable: placed by sequence continuity
    alternatives: list[tuple[int, ...]]        # other b rows whose total cost is within the ambiguity margin
    cost_units: int
    windowed: bool = False


def _cost_function(a_pts, b_pts, cap_m, cap_units):
    hypot = math.hypot

    def cost(i, j):
        a, b = a_pts[i], b_pts[j]
        if a is None or b is None:
            return cap_units
        d = hypot(a[0] - b[0], a[1] - b[1])
        return cap_units if d >= cap_m else round(d * UNIT)
    return cost


def _longest_non_decreasing(values):
    """Indices of one longest non-decreasing subsequence (patience sorting, O(k log k))."""
    tails, previous = [], [-1] * len(values)
    for index, value in enumerate(values):
        low, high = 0, len(tails)
        while low < high:
            mid = (low + high) // 2
            if values[tails[mid]] <= value:
                low = mid + 1
            else:
                high = mid
        if low:
            previous[index] = tails[low - 1]
        if low == len(tails):
            tails.append(index)
        else:
            tails[low] = index
    chain, k = [], tails[-1] if tails else -1
    while k != -1:
        chain.append(k)
        k = previous[k]
    return chain[::-1]


def _corridor_windows(a_pts, b_pts, slack, cap_m, half_width):
    """Per-row offset windows [lo, hi] for very large slack.

    Each ``a`` row votes for the offset of its spatially nearest feasible ``b`` row (within ``cap``).  The longest
    non-decreasing chain of votes is a robust estimate of the true offset trajectory; anomalous coordinates cannot
    join it.  Rows are then searched within ``half_width`` of the surrounding chain offsets.  With no votes the
    window is the full range."""
    m = len(a_pts)
    cell = cap_m
    grid = {}
    for j, p in enumerate(b_pts):
        if p is not None:
            grid.setdefault((math.floor(p[0] / cell), math.floor(p[1] / cell)), []).append(j)
    rows, offsets = [], []
    for i, p in enumerate(a_pts):
        if p is None:
            continue
        cx, cy = math.floor(p[0] / cell), math.floor(p[1] / cell)
        best = None
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                members = grid.get((gx, gy))
                if not members:
                    continue
                for k in range(bisect_left(members, i), bisect_right(members, i + slack)):
                    j = members[k]
                    d = math.hypot(p[0] - b_pts[j][0], p[1] - b_pts[j][1])
                    if d < cap_m and (best is None or d < best[0] or (d == best[0] and j < best[1])):
                        best = (d, j)
        if best is not None:
            rows.append(i)
            offsets.append(best[1] - i)
    chain = _longest_non_decreasing(offsets)
    anchor_rows = [rows[k] for k in chain]
    anchor_offsets = [offsets[k] for k in chain]
    lo, hi = [0] * m, [slack] * m
    if not anchor_rows:
        return lo, hi
    pointer = 0
    for i in range(m):
        while pointer < len(anchor_rows) and anchor_rows[pointer] < i:
            pointer += 1
        previous = anchor_offsets[pointer - 1] if pointer > 0 else 0
        following = anchor_offsets[pointer] if pointer < len(anchor_rows) else slack
        lo[i] = max(0, previous - half_width)
        hi[i] = min(slack, following + half_width)
    return lo, hi


def embed_ordered(a_pts: Sequence[Point], b_pts: Sequence[Point], cap_m: float,
                  ambiguity_margin_m: float = AMBIGUITY_MARGIN_M,
                  full_band_max_slack: int = FULL_BAND_MAX_SLACK) -> Embedding:
    """Place every ``a`` row on a distinct ``b`` row, preserving order, at minimum total cost."""
    m, n = len(a_pts), len(b_pts)
    if m > n:
        raise ValueError("The embedded sequence must not be longer than the target sequence")
    if m == 0:
        return Embedding([], [], [], [], 0)
    slack = n - m
    cap_units = round(cap_m * UNIT)
    margin_units = round(ambiguity_margin_m * UNIT)
    cost = _cost_function(a_pts, b_pts, cap_m, cap_units)
    # Three int tables of m x (slack + 1) cells are held: fall back to the corridor when the exact table would be huge.
    windowed = slack > full_band_max_slack or m * (slack + 1) > MAX_EXACT_STATES
    if windowed:
        lo, hi = _corridor_windows(a_pts, b_pts, slack, cap_m, CORRIDOR_HALF_WIDTH)
    else:
        lo, hi = [0] * m, [slack] * m

    # ---- forward pass: F[i][d - lo[i]] = best cost of rows 0..i with row i at offset d ----
    costs = [[cost(i, i + d) for d in range(lo[i], hi[i] + 1)] for i in range(m)]
    forward = [[c + (SKIP_EVENT_COST if d > 0 else 0) for c, d in zip(costs[0], range(lo[0], hi[0] + 1))]]
    for i in range(1, m):
        previous, plo, phi = forward[i - 1], lo[i - 1], hi[i - 1]
        prefix, best = [], _INF
        for value in previous:
            if value < best:
                best = value
            prefix.append(best)
        current = []
        for c, d in zip(costs[i], range(lo[i], hi[i] + 1)):
            stay = previous[d - plo] if plo <= d <= phi else _INF
            if d - 1 >= plo:
                skip = prefix[min(d - 1, phi) - plo] + SKIP_EVENT_COST
            else:
                skip = _INF
            current.append(c + (stay if stay <= skip else skip))
        forward.append(current)

    last_lo = lo[m - 1]
    final = [value + (SKIP_EVENT_COST if last_lo + k < slack else 0) for k, value in enumerate(forward[m - 1])]
    optimum = min(final)
    offsets = [0] * m
    offsets[m - 1] = last_lo + final.index(optimum)          # smallest offset on ties: trailing rows skipped
    for i in range(m - 1, 0, -1):
        d, plo, phi = offsets[i], lo[i - 1], hi[i - 1]
        previous = forward[i - 1]
        best_cost, best_d = None, plo
        for dp in range(plo, min(d, phi) + 1):               # smallest predecessor offset on ties: skip as late as possible
            c = previous[dp - plo] + (0 if dp == d else SKIP_EVENT_COST)
            if best_cost is None or c < best_cost:
                best_cost, best_d = c, dp
        offsets[i - 1] = best_d

    # ---- backward pass: min-marginals expose genuinely competing placements ----
    backward = [None] * m
    backward[m - 1] = [SKIP_EVENT_COST if last_lo + k < slack else 0 for k in range(hi[m - 1] - last_lo + 1)]
    for i in range(m - 2, -1, -1):
        nlo, nhi, following = lo[i + 1], hi[i + 1], backward[i + 1]
        entering = [c + b for c, b in zip(costs[i + 1], following)]
        suffix = [_INF] * (len(entering) + 1)
        for k in range(len(entering) - 1, -1, -1):
            suffix[k] = entering[k] if entering[k] < suffix[k + 1] else suffix[k + 1]
        current = []
        for d in range(lo[i], hi[i] + 1):
            stay = entering[d - nlo] if nlo <= d <= nhi else _INF
            k = max(d + 1, nlo) - nlo
            skip = suffix[k] + SKIP_EVENT_COST if k < len(entering) else _INF
            current.append(stay if stay <= skip else skip)
        backward[i] = current

    targets, distances, saturated, alternatives = [], [], [], []
    for i in range(m):
        j = i + offsets[i]
        targets.append(j)
        a, b = a_pts[i], b_pts[j]
        usable = a is not None and b is not None
        distance = math.hypot(a[0] - b[0], a[1] - b[1]) if usable else None
        distances.append(distance)
        saturated.append(distance is None or distance >= cap_m)
        rivals = []
        for k, d in enumerate(range(lo[i], hi[i] + 1)):
            if d == offsets[i]:
                continue
            regret = forward[i][k] + backward[i][k] - optimum
            if regret <= margin_units:
                rivals.append((regret, i + d))
        rivals.sort()
        alternatives.append(tuple(j2 for _, j2 in rivals[:MAX_ALTERNATIVES]))
    return Embedding(targets, distances, saturated, alternatives, optimum, windowed)


# ----------------------------------------------------------------------------------------------------------
# Record level
# ----------------------------------------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Association:
    """One authoritative reference record placed on one target row."""
    reference_row: int                 # SourceRecord.row_index of the reference record
    target_row: int                    # SourceRecord.row_index of the target row
    distance_m: Optional[float]        # full-precision distance; None when a position is unknown
    basis: str                         # SPATIAL: distance informed the choice; SEQUENCE: placed by continuity
    ambiguous: bool                    # a competing one-to-one placement of nearly equal total cost exists
    alternative_target_rows: tuple[int, ...] = ()


@dataclass
class AlignmentResult:
    associations: list[Association] = field(default_factory=list)       # ordered by reference row
    by_reference: dict[int, Association] = field(default_factory=dict)
    by_target: dict[int, Association] = field(default_factory=dict)
    unplaced_reference_rows: list[int] = field(default_factory=list)    # valid reference records without a target row
    reference_valid: int = 0
    target_rows: int = 0
    complete: bool = True
    direction: str = "REFERENCE_TO_TARGET"
    cost_m: float = 0.0
    windowed: bool = False


def _point(record: SourceRecord) -> Point:
    return (record.x, record.y) if record.has_position else None


def align_records(reference: Sequence[SourceRecord], target: Sequence[SourceRecord], parameters) -> AlignmentResult:
    """Associate every valid reference record with a distinct target row, preserving acquisition order.

    Reference rows that are not VALID (unparseable, or marked "no shot") take no part.  Target rows with an unknown
    position remain candidates: their place in the sequence is still evidence."""
    pool = [r for r in reference if r.classification == VALID]
    result = AlignmentResult(reference_valid=len(pool), target_rows=len(target))
    if not pool or not target:
        result.complete = not pool
        result.unplaced_reference_rows = [r.row_index for r in pool]
        return result
    ref_pts = [_point(r) for r in pool]
    tgt_pts = [_point(t) for t in target]
    cap = parameters.alignment_cap_m
    if len(pool) <= len(target):
        emb = embed_ordered(ref_pts, tgt_pts, cap)
        for k, r in enumerate(pool):
            association = Association(r.row_index, target[emb.targets[k]].row_index, emb.distance_m[k],
                                      "SEQUENCE" if emb.saturated[k] else "SPATIAL", bool(emb.alternatives[k]),
                                      tuple(target[j].row_index for j in emb.alternatives[k]))
            result.associations.append(association)
        result.cost_m = emb.cost_units / UNIT
        result.windowed = emb.windowed
    else:
        # More valid reference records than target rows: a complete assignment is impossible.  Place every target
        # row on a distinct reference record (partial, display only); the remaining records are reported as blocked.
        emb = embed_ordered(tgt_pts, ref_pts, cap)
        placed = set()
        for k, t in enumerate(target):
            r = pool[emb.targets[k]]
            placed.add(emb.targets[k])
            result.associations.append(Association(r.row_index, t.row_index, emb.distance_m[k],
                                                   "SEQUENCE" if emb.saturated[k] else "SPATIAL", False, ()))
        result.associations.sort(key=lambda a: a.reference_row)
        result.unplaced_reference_rows = [r.row_index for k, r in enumerate(pool) if k not in placed]
        result.complete = False
        result.direction = "TARGET_TO_REFERENCE"
        result.cost_m = emb.cost_units / UNIT
        result.windowed = emb.windowed
    result.by_reference = {a.reference_row: a for a in result.associations}
    result.by_target = {a.target_row: a for a in result.associations}
    return result
