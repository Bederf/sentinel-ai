"""Geometry utilities for coordinate transformations and calculations.

Provides functions for working with DXF coordinates, bounding boxes,
and building-relative coordinate systems. Used by DXF parser to normalize
CAD coordinates to standard building geometry.
"""

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BoundingBox:
    """2D bounding box for DXF entities."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        """Width of bounding box."""
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        """Height of bounding box."""
        return self.max_y - self.min_y

    @property
    def center(self) -> tuple[float, float]:
        """Center point of bounding box."""
        return ((self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2)

    @property
    def area(self) -> float:
        """Area of bounding box."""
        return self.width * self.height


def calculate_bounding_box(entities: list) -> BoundingBox:
    """
    Calculate bounding box from DXF entities.

    Extracts min/max X/Y coordinates from all entity positions
    and returns a BoundingBox covering all entities.

    Args:
        entities: List of DXF entities with dxf.insert or similar coordinates

    Returns:
        BoundingBox covering all entities

    Raises:
        ValueError: If entities list is empty or no coordinates found
    """
    if not entities:
        raise ValueError("Cannot calculate bounding box from empty entities list")

    x_coords = []
    y_coords = []

    for entity in entities:
        try:
            # Try INSERT block entities (most common)
            if hasattr(entity, "dxf") and hasattr(entity.dxf, "insert"):
                x, y, _ = entity.dxf.insert
                x_coords.append(x)
                y_coords.append(y)

            # Try LINE entities (start and end points)
            elif hasattr(entity, "dxf") and hasattr(entity.dxf, "start"):
                x_coords.append(entity.dxf.start[0])
                y_coords.append(entity.dxf.start[1])
                x_coords.append(entity.dxf.end[0])
                y_coords.append(entity.dxf.end[1])

            # Try CIRCLE entities (center point)
            elif hasattr(entity, "dxf") and hasattr(entity.dxf, "center"):
                x_coords.append(entity.dxf.center[0])
                y_coords.append(entity.dxf.center[1])

            # Try TEXT/MTEXT entities
            elif hasattr(entity, "dxf") and hasattr(entity.dxf, "insert"):
                x_coords.append(entity.dxf.insert[0])
                y_coords.append(entity.dxf.insert[1])
        except (AttributeError, IndexError, TypeError):
            continue

    if not x_coords or not y_coords:
        raise ValueError("No coordinates found in entities")

    return BoundingBox(
        min_x=float(np.min(x_coords)),
        min_y=float(np.min(y_coords)),
        max_x=float(np.max(x_coords)),
        max_y=float(np.max(y_coords)),
    )


def normalize_coordinates(
    x: float,
    y: float,
    bbox: BoundingBox,
    target_width: float = 150.0,
    target_depth: float = 120.0,
) -> tuple[float, float]:
    """
    Normalize DXF coordinates to building-relative meters.

    DXF files use arbitrary units (often millimeters or inches).
    This function converts them to building-relative meters for consistency.

    **Transformation:**
    1. Translate: Move DXF origin to bbox minimum
    2. Scale: Scale to target building dimensions
    3. Result: (0, 0) = bottom-left, (target_width, target_depth) = top-right

    Args:
        x, y: DXF coordinates (in original units)
        bbox: Bounding box of entire floor plan
        target_width: Expected building width in meters (default: 150m)
        target_depth: Expected building depth in meters (default: 120m)

    Returns:
        (x_meters, y_meters) normalized to building coordinate space
    """
    if bbox.width == 0 or bbox.height == 0:
        logger.warning("Zero-size bounding box detected, returning raw coordinates")
        return (x, y)

    # Translate to bbox origin
    x_relative = x - bbox.min_x
    y_relative = y - bbox.min_y

    # Scale to target dimensions
    x_normalized = (x_relative / bbox.width) * target_width
    y_normalized = (y_relative / bbox.height) * target_depth

    return (float(x_normalized), float(y_normalized))


def infer_floor_from_z_coordinate(z: float, floor_height: float = 3.5) -> str:
    """
    Infer floor code from Z-coordinate in 3D DXF drawing.

    Maps Z-height to standard building floor codes:
    - z < -floor_height/2: Basements (B1, B2, B3, ...)
    - z between -floor_height/2 and floor_height/2: Ground floor (G)
    - z > floor_height/2: Levels (L1, L2, L3, ...)

    Args:
        z: Z-height in DXF (meters or feet depending on DXF units)
        floor_height: Typical floor-to-floor height (default: 3.5m)

    Returns:
        Floor code string: B1, B2, G, L1, L2, etc.

    Example:
        >>> infer_floor_from_z_coordinate(-3.5)
        'B1'
        >>> infer_floor_from_z_coordinate(0)
        'G'
        >>> infer_floor_from_z_coordinate(3.5)
        'L1'
        >>> infer_floor_from_z_coordinate(7.0)
        'L2'
    """
    threshold = floor_height / 2

    if z < -threshold:
        # Basement level
        basement_num = int(abs(z) / floor_height)
        if basement_num == 0:
            basement_num = 1
        return f"B{basement_num}"
    elif z <= threshold:
        # Ground floor (within tolerance)
        return "G"
    else:
        # Above ground level
        level_num = int(z / floor_height)
        return f"L{level_num}"


def euclidean_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """
    Calculate Euclidean distance between two 2D points.

    Args:
        p1: First point (x, y)
        p2: Second point (x, y)

    Returns:
        Distance in same units as input coordinates

    Example:
        >>> euclidean_distance((0, 0), (3, 4))
        5.0
        >>> euclidean_distance((1, 1), (4, 5))
        5.0
    """
    return float(np.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2))


def cluster_points(
    points: list[tuple[float, float]], distance_threshold: float = 5.0
) -> list[list[tuple[float, float]]]:
    """
    Cluster nearby points using simple distance-based grouping.

    Groups points that are within distance_threshold of each other.
    Used for zone inference from equipment positions.

    Args:
        points: List of (x, y) coordinate tuples
        distance_threshold: Maximum distance to consider points as same cluster

    Returns:
        List of clusters, where each cluster is a list of points

    Example:
        >>> points = [(0, 0), (1, 1), (50, 50), (51, 51)]
        >>> clusters = cluster_points(points, 3.0)
        >>> len(clusters)  # Should be 2 clusters
        2
    """
    if not points:
        return []

    clusters = []
    used = set()

    for i, point in enumerate(points):
        if i in used:
            continue

        cluster = [point]
        used.add(i)

        for j, other_point in enumerate(points):
            if j not in used:
                if euclidean_distance(point, other_point) <= distance_threshold:
                    cluster.append(other_point)
                    used.add(j)

        clusters.append(cluster)

    return clusters


def get_cluster_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """
    Calculate centroid (center) of a cluster of points.

    Args:
        points: List of (x, y) coordinate tuples

    Returns:
        (x_avg, y_avg) centroid of all points

    Raises:
        ValueError: If points list is empty
    """
    if not points:
        raise ValueError("Cannot calculate centroid of empty points list")

    x_avg = np.mean([p[0] for p in points])
    y_avg = np.mean([p[1] for p in points])

    return (float(x_avg), float(y_avg))


def angle_from_points(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """
    Calculate angle in degrees from point p1 to point p2.

    Angle is measured from east (0°) counter-clockwise.
    - 0° = East
    - 90° = North
    - 180° = West
    - 270° = South

    Args:
        p1: Starting point (x, y)
        p2: Ending point (x, y)

    Returns:
        Angle in degrees (0-360)
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    angle_rad = np.arctan2(dy, dx)
    angle_deg = np.degrees(angle_rad)

    # Normalize to 0-360
    if angle_deg < 0:
        angle_deg += 360

    return float(angle_deg)


def point_in_bounding_box(point: tuple[float, float], bbox: BoundingBox) -> bool:
    """
    Check if a point is inside a bounding box.

    Args:
        point: (x, y) coordinate to check
        bbox: BoundingBox to check against

    Returns:
        True if point is inside or on edge of bbox

    Example:
        >>> bbox = BoundingBox(0, 0, 100, 80)
        >>> point_in_bounding_box((50, 40), bbox)
        True
        >>> point_in_bounding_box((150, 40), bbox)
        False
    """
    x, y = point
    return bbox.min_x <= x <= bbox.max_x and bbox.min_y <= y <= bbox.max_y


def scale_coordinates(x: float, y: float, scale_factor: float) -> tuple[float, float]:
    """
    Scale coordinates by a factor.

    Useful for unit conversion (e.g., millimeters to meters).

    Args:
        x, y: Original coordinates
        scale_factor: Factor to multiply by (e.g., 0.001 for mm to m)

    Returns:
        (x_scaled, y_scaled)

    Example:
        >>> scale_coordinates(5000, 4000, 0.001)  # Convert mm to m
        (5.0, 4.0)
    """
    return (float(x * scale_factor), float(y * scale_factor))


def translate_coordinates(x: float, y: float, dx: float, dy: float) -> tuple[float, float]:
    """
    Translate (shift) coordinates by an offset.

    Args:
        x, y: Original coordinates
        dx, dy: Offset to add

    Returns:
        (x_translated, y_translated)

    Example:
        >>> translate_coordinates(50, 40, 10, -5)
        (60, 35)
    """
    return (float(x + dx), float(y + dy))


def rotate_coordinates(
    x: float, y: float, angle_degrees: float, origin: tuple[float, float] = (0, 0)
) -> tuple[float, float]:
    """
    Rotate coordinates around an origin point.

    Args:
        x, y: Original coordinates
        angle_degrees: Rotation angle in degrees (counter-clockwise)
        origin: Point to rotate around (default: origin 0,0)

    Returns:
        (x_rotated, y_rotated)
    """
    # Translate to origin
    x_rel = x - origin[0]
    y_rel = y - origin[1]

    # Rotate
    angle_rad = np.radians(angle_degrees)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)

    x_rot = x_rel * cos_a - y_rel * sin_a
    y_rot = x_rel * sin_a + y_rel * cos_a

    # Translate back
    x_final = x_rot + origin[0]
    y_final = y_rot + origin[1]

    return (float(x_final), float(y_final))
