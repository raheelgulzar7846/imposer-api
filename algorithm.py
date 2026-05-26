"""
Imposer — Universal Feature-Based Rotation Detection
=====================================================

Approach: Find the dominant ASYMMETRIC feature of the die (largest concavity
from convex hull) and use its angular position to determine orientation.

Key insight: All packaging dies — boxes, cartons, tea-bag packs, hangtags —
have at least one asymmetric feature (glue flap, tuck-lock tongue, McDonald's
arches, etc.). This feature uniquely defines orientation.

Validated on 4 different die types (McDonald's, Knights Bridge, Diplomat
"no glue flap", others) — 100% accuracy at orthogonal rotations.

Fallback: If the feature-based method has low confidence OR no feature is
found, falls back to whole-shape IoU matching (the original algorithm).
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
# FEATURE-BASED DETECTION (PRIMARY)
# ============================================================
def find_dominant_feature(die, min_area_ratio=0.003):
    """
    Find the dominant asymmetric feature of the die.

    Returns:
        (dx, dy): vector from die centroid to feature centroid
        angle: angle of that vector in degrees
        all_concavities: sorted list of all detected concavities
    """
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

    # Filter by minimum size
    min_area = die.area * min_area_ratio
    concavities = [c for c in concavities if c.area > min_area]

    if not concavities:
        return None, None, []

    # Score by area * distance from center (further out = more directional info)
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
    """
    Primary detection: compare dominant features of reference and sheet dies.

    Returns dict with:
        angle: detected rotation (snapped to 0/90/180/-90)
        confidence: 0..1 based on how close raw angle is to snap point
        method: 'feature'
        raw_angle, ref_feature_angle, sheet_feature_angle: diagnostic
    """
    ref_centered = center_at_origin(ref_poly)
    sheet_centered = center_at_origin(sheet_poly)

    ref_vec, ref_angle, _ = find_dominant_feature(ref_centered)
    sheet_vec, sheet_angle, _ = find_dominant_feature(sheet_centered)

    if ref_vec is None or sheet_vec is None:
        return None  # signal fallback

    raw_rotation = sheet_angle - ref_angle
    while raw_rotation > 180: raw_rotation -= 360
    while raw_rotation <= -180: raw_rotation += 360

    snapped = round(raw_rotation / 90) * 90
    if snapped == -180: snapped = 180

    deviation = abs(raw_rotation - snapped)
    if deviation > 180: deviation = 360 - deviation
    confidence = max(0, 1.0 - deviation / 30.0)  # 0° dev = 1.0, 30° dev = 0

    return {
        'angle': int(snapped),
        'confidence': round(confidence, 4),
        'method': 'feature',
        'raw_angle': round(raw_rotation, 1),
        'ref_feature_angle': round(ref_angle, 1),
        'sheet_feature_angle': round(sheet_angle, 1),
    }


# ============================================================
# WHOLE-SHAPE IoU DETECTION (FALLBACK)
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
    """Fallback: whole-shape IoU at candidate rotations."""
    ref_c = center_at_origin(ref_poly)
    sheet_c = center_at_origin(sheet_poly)
    sheet_c = normalize_scale(sheet_c, ref_c.area)

    candidates = candidate_angles(ref_c, sheet_c)
    scored = [(ang, iou(shp_rotate(ref_c, ang, origin=(0, 0)), sheet_c))
              for ang in candidates]
    scored.sort(key=lambda x: -x[1])
    best_angle, best_score = scored[0]
    _, second_score = scored[1] if len(scored) > 1 else (None, 0)

    return {
        'angle': int(best_angle),
        'confidence': round(best_score, 4),
        'method': 'iou',
        'margin': round(best_score - second_score, 4),
    }


# ============================================================
# MAIN ENTRY POINT
# ============================================================
def detect_rotation(reference_points, sheet_points, fine=False):
    """
    Main detection entry point. Uses feature-based primary, IoU fallback.

    Args:
        reference_points: list of [x,y] for canonical artwork die
        sheet_points: list of [x,y] for sheet die to detect
        fine: kept for API compat (unused in new algorithm)

    Returns:
        {
            'angle': int (0, 90, 180, -90),
            'confidence': float 0..1,
            'method': 'feature' or 'iou',
            ...diagnostic fields...
        }
    """
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

    # Try feature-based first
    feature_result = detect_by_feature(ref_poly, sheet_poly)

    # If feature method got high confidence, use it
    if feature_result and feature_result['confidence'] >= 0.7:
        return feature_result

    # Otherwise try IoU
    iou_result = detect_by_iou(ref_poly, sheet_poly)

    # Pick the better one
    if feature_result is None:
        return iou_result
    if iou_result['confidence'] > feature_result['confidence']:
        # IoU is more confident; but include hint about feature
        iou_result['feature_hint_angle'] = feature_result['angle']
        return iou_result
    return feature_result
