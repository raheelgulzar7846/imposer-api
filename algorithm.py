"""
Imposer — Shape Matching Core Algorithm
========================================

Production-tested polygon shape matching for die rotation detection.
Validated in Phase 1 on real Pakistani packaging files (Colgate, Sooper, Qourma).
"""
from shapely.geometry import Polygon
from shapely.affinity import rotate as shp_rotate, translate, scale as shp_scale


def center_at_origin(poly: Polygon) -> Polygon:
    """Translate polygon so centroid is at (0,0)."""
    c = poly.centroid
    return translate(poly, xoff=-c.x, yoff=-c.y)


def normalize_scale(poly: Polygon, target_area: float) -> Polygon:
    """Uniformly scale polygon to match target area."""
    cur_area = poly.area
    if cur_area <= 0:
        return poly
    factor = (target_area / cur_area) ** 0.5
    return shp_scale(poly, xfact=factor, yfact=factor, origin=(0, 0))


def iou(a: Polygon, b: Polygon) -> float:
    """Intersection over Union."""
    try:
        inter = a.intersection(b).area
        union = a.union(b).area
        return inter / union if union > 0 else 0.0
    except Exception:
        return 0.0


def candidate_angles(ref: Polygon, sheet: Polygon, fine: bool = False) -> list:
    """Pick rotation angles to test."""
    if fine:
        return list(range(-180, 180))

    rb = ref.bounds
    sb = sheet.bounds
    ref_ratio = (rb[2] - rb[0]) / max(rb[3] - rb[1], 1e-9)
    sheet_ratio = (sb[2] - sb[0]) / max(sb[3] - sb[1], 1e-9)

    # Near-square reference: aspect filter useless, test all 4
    if abs(ref_ratio - 1.0) < 0.08:
        return [0, 90, 180, -90]

    same_diff = abs(ref_ratio - sheet_ratio)
    perp_diff = abs(ref_ratio - 1.0 / sheet_ratio)
    if same_diff < perp_diff:
        return [0, 180]
    return [90, -90]


def points_to_polygon(points: list) -> Polygon:
    """Convert [[x,y], ...] to Shapely Polygon, with validity repair."""
    if len(points) < 3:
        raise ValueError(f"Need at least 3 points, got {len(points)}")
    p = Polygon(points)
    if not p.is_valid:
        p = p.buffer(0)  # try to fix self-intersections
    if not p.is_valid or p.is_empty:
        raise ValueError("Polygon could not be made valid")
    return p


def detect_rotation(reference_points: list, sheet_points: list, fine: bool = False) -> dict:
    """
    Main entry point.
    reference_points: list of [x, y] — the artwork die at canonical orientation
    sheet_points: list of [x, y] — the same die rotated on a sheet
    fine: try every 1° (slower but handles arbitrary rotations)

    Returns: {
        'angle': detected rotation in degrees,
        'confidence': IoU score 0..1 (1.0 = perfect match),
        'margin': how much best beat second-best,
        'second_best': runner-up angle for transparency,
        'aspect_ratio_used': True if ratio narrowed candidates,
    }
    """
    try:
        ref_poly = points_to_polygon(reference_points)
        sheet_poly = points_to_polygon(sheet_points)
    except ValueError as e:
        return {
            'angle': 0,
            'confidence': 0.0,
            'margin': 0.0,
            'second_best': None,
            'error': str(e),
        }

    ref_c = center_at_origin(ref_poly)
    sheet_c = center_at_origin(sheet_poly)
    sheet_c = normalize_scale(sheet_c, ref_c.area)

    candidates = candidate_angles(ref_c, sheet_c, fine=fine)
    aspect_filtered = (len(candidates) < 4)

    scored = []
    for angle in candidates:
        rotated_ref = shp_rotate(ref_c, angle, origin=(0, 0))
        score = iou(rotated_ref, sheet_c)
        scored.append((angle, score))

    scored.sort(key=lambda x: -x[1])
    best_angle, best_score = scored[0]
    second_angle, second_score = scored[1] if len(scored) > 1 else (None, 0)

    return {
        'angle': best_angle,
        'confidence': round(best_score, 4),
        'margin': round(best_score - second_score, 4),
        'second_best': second_angle,
        'aspect_ratio_used': aspect_filtered,
    }
