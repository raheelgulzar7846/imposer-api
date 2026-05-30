"""
Imposer — Universal Feature-Based Rotation Detection
=====================================================

Three detection methods, tried in order:

1. CENTROID method (best for boxes): The centroid of a die is offset from
   its bounding-box center due to asymmetric features (glue flap, etc).
   This offset vector rotates with the die. Comparing offset angles between
   reference and sheet gives the rotation. Works on box dies where glue
   flap is a CONVEX EXTENSION (not a concavity).

2. FEATURE method (best for shapes with concavities): McDonald's Happy Meal,
   Knights Bridge, etc. — shapes where convex hull deviates significantly.

3. IoU method (fallback): Whole-shape intersection-over-union at candidate
   angles. Used when other methods can't determine orientation.

Tied IoU results default to 0° (no rotation) — safest assumption when
shape is too symmetric to distinguish.
"""
from shapely.geometry import Polygon, MultiPolygon
from shapely.affinity import rotate as shp_rotate, translate, scale as shp_scale
import math


# ============================================================
# POLYGON HELPERS
# ============================================================
def points_to_polygon(points):
    if len(points) < 3:
        raise ValueError(f"Need at least 3 points, got {len(points)}")
    p = Polygon(points)
    if not p.is_valid:
        p = p.buffer(0)
    if not p.is_valid or p.is_empty:
        raise ValueError("Polygon could not be made valid")
    return p


def center_at_origin(poly):
    c = poly.centroid
    return translate(poly, xoff=-c.x, yoff=-c.y)


def normalize_scale(poly, target_area):
    cur = poly.area
    if cur <= 0: return poly
    factor = (target_area / cur) ** 0.5
    return shp_scale(poly, xfact=factor, yfact=factor, origin=(0, 0))


def iou(a, b):
    try:
        inter = a.intersection(b).area
        union = a.union(b).area
        return inter / union if union > 0 else 0.0
    except Exception:
        return 0.0


# ============================================================
# CENTROID-OFFSET METHOD (PRIMARY for boxes with glue flap)
# ============================================================
def get_orientation_signature(die):
    """
    Compute the vector from bbox-center to centroid, normalized by die size.

    For a box with glue flap on one side:
    - bbox extends to include the glue flap
    - bbox center is biased toward the glue-flap side
    - centroid (area-weighted) is closer to the main body
    - The vector (centroid - bbox_center) points AWAY from glue flap

    When die rotates, this vector rotates with it. Comparing the vector
    angles between reference and sheet gives the rotation directly.

    Returns: (offset_x, offset_y, magnitude) all normalized by die size.
    """
    bbox = die.bounds
    bbox_cx = (bbox[0] + bbox[2]) / 2
    bbox_cy = (bbox[1] + bbox[3]) / 2
    centroid = die.centroid
    offset_x = centroid.x - bbox_cx
    offset_y = centroid.y - bbox_cy
    die_size = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
    if die_size < 1e-9:
        return 0.0, 0.0, 0.0
    nx = offset_x / die_size
    ny = offset_y / die_size
    mag = math.hypot(nx, ny)
    return nx, ny, mag


def detect_by_centroid(ref_poly, sheet_poly):
    """
    Primary detection for boxes. Uses centroid-vs-bbox-center offset.

    Returns None if signal is too weak (perfectly symmetric die).
    """
    ref_nx, ref_ny, ref_mag = get_orientation_signature(ref_poly)
    sheet_nx, sheet_ny, sheet_mag = get_orientation_signature(sheet_poly)

    # Minimum offset magnitude threshold — below this, the die is too symmetric
    MIN_MAG = 0.005  # 0.5% of die size — pretty sensitive

    if ref_mag < MIN_MAG or sheet_mag < MIN_MAG:
        return None  # Too symmetric for centroid method

    ref_angle = math.degrees(math.atan2(ref_ny, ref_nx))
    sheet_angle = math.degrees(math.atan2(sheet_ny, sheet_nx))

    raw_rotation = sheet_angle - ref_angle
    while raw_rotation > 180: raw_rotation -= 360
    while raw_rotation <= -180: raw_rotation += 360

    snapped = round(raw_rotation / 90) * 90
    if snapped == -180: snapped = 180

    deviation = abs(raw_rotation - snapped)
    if deviation > 180: deviation = 360 - deviation
    confidence = max(0, 1.0 - deviation / 30.0)

    # Boost confidence based on offset magnitude strength
    # Strong asymmetry = more reliable detection
    mag_confidence = min(1.0, (ref_mag + sheet_mag) / 0.04)  # 2% offset = full confidence
    final_confidence = confidence * mag_confidence

    return {
        'angle': int(snapped),
        'confidence': round(final_confidence, 4),
        'method': 'centroid',
        'raw_angle': round(raw_rotation, 1),
        'ref_offset_mag': round(ref_mag, 4),
        'sheet_offset_mag': round(sheet_mag, 4),
        'ref_offset_angle': round(ref_angle, 1),
        'sheet_offset_angle': round(sheet_angle, 1),
    }


# ============================================================
# CONCAVITY-FEATURE METHOD (good for shapes with notches)
# ============================================================
def find_dominant_feature(die, min_area_ratio=0.003):
    hull = die.convex_hull
    try:
        diff = hull.difference(die)
    except Exception:
        return None, None, []

    if diff.is_empty:
        return None, None, []

    if isinstance(diff, MultiPolygon):
        concavities = list(diff.geoms)
    else:
        concavities = [diff]

    min_area = die.area * min_area_ratio
    concavities = [c for c in concavities if c.area > min_area]

    if not concavities:
        return None, None, []

    die_center = die.centroid
    die_size = max(die.bounds[2] - die.bounds[0], die.bounds[3] - die.bounds[1])

    scored = []
    for c in concavities:
        cc = c.centroid
        dx, dy = cc.x - die_center.x, cc.y - die_center.y
        dist = math.hypot(dx, dy)
        score = c.area * (1.0 + dist / die_size)
        scored.append((score, c, dx, dy))

    scored.sort(key=lambda s: -s[0])
    _, _, best_dx, best_dy = scored[0]
    angle = math.degrees(math.atan2(best_dy, best_dx))

    return (best_dx, best_dy), angle, [s[1] for s in scored]


def detect_by_feature(ref_poly, sheet_poly):
    ref_centered = center_at_origin(ref_poly)
    sheet_centered = center_at_origin(sheet_poly)

    ref_vec, ref_angle, _ = find_dominant_feature(ref_centered)
    sheet_vec, sheet_angle, _ = find_dominant_feature(sheet_centered)

    if ref_vec is None or sheet_vec is None:
        return None

    raw_rotation = sheet_angle - ref_angle
    while raw_rotation > 180: raw_rotation -= 360
    while raw_rotation <= -180: raw_rotation += 360

    snapped = round(raw_rotation / 90) * 90
    if snapped == -180: snapped = 180

    deviation = abs(raw_rotation - snapped)
    if deviation > 180: deviation = 360 - deviation
    confidence = max(0, 1.0 - deviation / 30.0)

    return {
        'angle': int(snapped),
        'confidence': round(confidence, 4),
        'method': 'feature',
        'raw_angle': round(raw_rotation, 1),
        'ref_feature_angle': round(ref_angle, 1),
        'sheet_feature_angle': round(sheet_angle, 1),
    }


# ============================================================
# WHOLE-SHAPE IoU METHOD (fallback)
# ============================================================
def candidate_angles(ref, sheet):
    rb = ref.bounds
    sb = sheet.bounds
    ref_ratio = (rb[2] - rb[0]) / max(rb[3] - rb[1], 1e-9)
    sheet_ratio = (sb[2] - sb[0]) / max(sb[3] - sb[1], 1e-9)
    if abs(ref_ratio - 1.0) < 0.08:
        return [0, 90, 180, -90]
    same_diff = abs(ref_ratio - sheet_ratio)
    perp_diff = abs(ref_ratio - 1.0 / sheet_ratio)
    if same_diff < perp_diff:
        return [0, 180]
    return [90, -90]


def detect_by_iou(ref_poly, sheet_poly):
    ref_c = center_at_origin(ref_poly)
    sheet_c = center_at_origin(sheet_poly)
    sheet_c = normalize_scale(sheet_c, ref_c.area)

    candidates = candidate_angles(ref_c, sheet_c)
    scored = [(ang, iou(shp_rotate(ref_c, ang, origin=(0, 0)), sheet_c))
              for ang in candidates]
    scored.sort(key=lambda x: -x[1])
    best_angle, best_score = scored[0]
    _, second_score = scored[1] if len(scored) > 1 else (None, 0)
    margin = best_score - second_score

    # If margin is tiny, this is a TIE — symmetric shape, can't distinguish
    # Default to 0° (no rotation) which is the safest assumption
    if margin < 0.01:
        return {
            'angle': 0,
            'confidence': 0.5,
            'method': 'iou-tie-default-0',
            'margin': round(margin, 4),
            'best_iou': round(best_score, 4),
            'second_iou': round(second_score, 4),
            'candidates_tested': [(a, round(s, 4)) for a, s in scored],
        }

    return {
        'angle': int(best_angle),
        'confidence': round(best_score, 4),
        'method': 'iou',
        'margin': round(margin, 4),
    }


# ============================================================
# POINT-CLOUD MATCHING METHOD (fine tiebreaker — "human-like")
# ============================================================
# Area-IoU is too coarse: a near-symmetric die scores almost identically at
# 0 vs 180, so IoU ties and defaults to 0. But matching the actual outline
# POINTS (after rotation) is sensitive to the small asymmetric feature even
# when area overlap isn't. This is the logic that previously got 14/16.

def _resample(poly, n=96):
    """Sample n equally-spaced points along the polygon perimeter."""
    ext = poly.exterior
    pts = []
    for i in range(n):
        p = ext.interpolate(i / float(n), normalized=True)
        pts.append((p.x, p.y))
    return pts


def _rotate_pts(pts, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [(x * c - y * s, x * s + y * c) for (x, y) in pts]


def _mean_nn_dist(a, b):
    """Average nearest-neighbour distance from each point in a to set b."""
    total = 0.0
    for (ax, ay) in a:
        best = float('inf')
        for (bx, by) in b:
            dx, dy = ax - bx, ay - by
            d = dx * dx + dy * dy
            if d < best:
                best = d
        total += math.sqrt(best)
    return total / len(a)


def detect_by_point_match(ref_poly, sheet_poly):
    """
    Match outline point-clouds at each candidate angle. Lower distance = better
    fit. Confidence comes from how clearly the best angle beats the runner-up.
    Returns None only if shapes are genuinely indistinguishable at all angles.
    """
    ref_c = center_at_origin(ref_poly)
    sheet_c = normalize_scale(center_at_origin(sheet_poly), ref_poly.area)

    R = _resample(ref_c, 96)
    S = _resample(sheet_c, 96)

    rb = ref_c.bounds
    size = max(rb[2] - rb[0], rb[3] - rb[1])
    if size < 1e-9:
        return None

    candidates = candidate_angles(ref_c, sheet_c)
    scored = []
    for ang in candidates:
        Rr = _rotate_pts(R, ang)
        # symmetric mean nearest-neighbour distance, normalized by die size
        d = (_mean_nn_dist(Rr, S) + _mean_nn_dist(S, Rr)) / 2.0 / size
        scored.append((ang, d))

    scored.sort(key=lambda x: x[1])  # smaller distance first
    best_angle, best_d = scored[0]
    second_d = scored[1][1] if len(scored) > 1 else best_d * 3

    # Relative separation between best and runner-up.
    # Big separation = confident; near-zero = truly symmetric die.
    denom = (best_d + second_d) / 2.0
    margin = (second_d - best_d) / denom if denom > 1e-9 else 0.0
    confidence = max(0.0, min(1.0, margin * 4.0))  # ~25% separation = full conf

    return {
        'angle': int(best_angle),
        'confidence': round(confidence, 4),
        'method': 'point-match',
        'margin': round(margin, 4),
        'best_dist': round(best_d, 4),
        'second_dist': round(second_d, 4),
        'candidates_tested': [(a, round(d, 4)) for a, d in scored],
    }


# ============================================================
# FIRST-POINT METHOD (PRIMARY — proven, deterministic 0/180)
# ============================================================
# The dieline path has a deterministic starting anchor. When the die is
# rotated 180 deg, that first point moves to the opposite side of the
# bbox center. Points arrive in path order, so points[0] IS that anchor.
# Compare which side of center the first point sits on, for reference vs
# sheet: same side = 0 deg, opposite side = 180 deg. Exact, no guessing.

def _first_point_side(points):
    """Return True if the path's first anchor is right of the bbox center-x."""
    xs = [p[0] for p in points]
    cx = (min(xs) + max(xs)) / 2.0
    first_x = points[0][0]
    # margin relative to die width — guards against a first point sitting
    # almost exactly on the center line (ambiguous)
    width = max(xs) - min(xs)
    if width < 1e-9:
        return None
    rel = (first_x - cx) / width
    if abs(rel) < 0.02:   # within 2% of center => ambiguous
        return None
    return first_x > cx


def detect_by_first_point(reference_points, sheet_points):
    """Deterministic 0/180 detection from first-anchor position."""
    if len(reference_points) < 3 or len(sheet_points) < 3:
        return None
    ref_right = _first_point_side(reference_points)
    sheet_right = _first_point_side(sheet_points)
    if ref_right is None or sheet_right is None:
        return None
    angle = 0 if (ref_right == sheet_right) else 180
    return {
        'angle': angle,
        'confidence': 1.0,
        'method': 'first-point',
        'ref_first_right': ref_right,
        'sheet_first_right': sheet_right,
    }


# ============================================================
# MAIN ENTRY POINT
# ============================================================
def detect_rotation(reference_points, sheet_points, fine=False):
    """
    Main detection entry point.

    Strategy:
    1. Try centroid method — works for boxes with glue flaps (convex asymmetry)
    2. Try feature method — works for shapes with concavities
    3. Fall back to IoU — last resort

    Use the FIRST method that gives high confidence. If multiple give answers,
    centroid wins for boxes (it's specifically designed for them).
    """
    # ---- PRIMARY: first-point method (deterministic, proven on real dies) ----
    # Runs on the RAW points (path order preserved) before any polygon
    # processing that could reorder them.
    try:
        fp_result = detect_by_first_point(reference_points, sheet_points)
        if fp_result:
            return fp_result
    except Exception:
        pass  # fall through to geometric methods if first point is unusable

    try:
        ref_poly = points_to_polygon(reference_points)
        sheet_poly = points_to_polygon(sheet_points)
    except ValueError as e:
        return {
            'angle': 0,
            'confidence': 0.0,
            'method': 'error',
            'error': str(e),
        }

    # Try centroid first (best for box-like dies)
    centroid_result = detect_by_centroid(ref_poly, sheet_poly)

    # If centroid is highly confident, trust it
    if centroid_result and centroid_result['confidence'] >= 0.6:
        return centroid_result

    # Try feature method
    feature_result = detect_by_feature(ref_poly, sheet_poly)

    if feature_result and feature_result['confidence'] >= 0.7:
        return feature_result

    # Try IoU
    iou_result = detect_by_iou(ref_poly, sheet_poly)

    # IoU with clear winner (good margin) is reliable
    if iou_result.get('margin', 0) > 0.05:
        return iou_result

    # IoU tied (near-symmetric die). Don't give up — match the actual outline
    # points, which catches the small asymmetric feature IoU's area misses.
    pm_result = detect_by_point_match(ref_poly, sheet_poly)
    if pm_result and pm_result['confidence'] >= 0.15:
        return pm_result

    # Still ambiguous — fall back to any low-confidence centroid/feature signal.
    if centroid_result:
        centroid_result['note'] = 'low-conf-but-used (everything else tied)'
        return centroid_result
    if feature_result:
        feature_result['note'] = 'low-conf-but-used (everything else tied)'
        return feature_result
    if pm_result:
        pm_result['note'] = 'low-conf-but-used (best available)'
        return pm_result

    # Truly indistinguishable shape — safest assumption is 0°.
    return iou_result
