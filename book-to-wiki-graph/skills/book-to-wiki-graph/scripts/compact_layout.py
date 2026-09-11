"""Deterministic rectangle packing with constraints from actual Canvas edges.

Only an edge's exit axis constrains its endpoints.  Unrelated boxes are packed
in free space; neither source order nor a target aspect ratio creates a chain.
No optional numerical/graph dependency is needed by the Canvas builder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CARD_GAP = 100
REGION_GAP = 160
GROUP_INSET = 56
GROUP_HEADER = 76
RIGHT_GAP = 140
DOWN_GAP = 110


@dataclass
class Box:
    key: str
    width: int
    height: int
    nodes: list[dict[str, Any]]
    members: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)


def distances(count: int, constraints: list[tuple[int, int, int]]) -> list[int]:
    """Minimal nonnegative solution of x[to] >= x[from] + distance."""
    result = [0] * count
    for iteration in range(count):
        changed = False
        for left, right, distance in constraints:
            required = result[left] + distance
            if result[right] < required:
                result[right] = required
                changed = True
        if not changed:
            return result
    raise ValueError("Canvas directional constraints have a positive cycle; review the cited routes/group ownership")


def pack_boxes(boxes: list[Box], edges: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    if not boxes:
        return [], []
    owner = {key: index for index, box in enumerate(boxes) for key in box.members}
    constraints: list[list[tuple[int, int, int]]] = [[], []]
    routes = []
    for edge in edges:
        left, right = str(edge["fromNode"]), str(edge["toNode"])
        if left not in owner or right not in owner or owner[left] == owner[right]:
            continue
        i, j = owner[left], owner[right]
        a, b = boxes[i].members[left], boxes[j].members[right]
        axis = 0 if edge["fromSide"] == "right" else 1
        gap = RIGHT_GAP if axis == 0 else DOWN_GAP
        constraints[axis].append((i, j, a[axis] + a[axis + 2] + gap - b[axis]))
        routes.append((i, j, a, b))

    # Lay out independent relation components separately.  A single local
    # timeline must not force every unrelated organizer group into the same
    # horizontal strip.  Solve each weak component using its real directional
    # constraints, then pack those solved constellations as a near-square map.
    adjacency = [set() for _ in boxes]
    for left, right, _a, _b in routes:
        adjacency[left].add(right)
        adjacency[right].add(left)
    components: list[list[int]] = []
    unseen = set(range(len(boxes)))
    while unseen:
        start = min(unseen)
        stack = [start]
        component: list[int] = []
        unseen.remove(start)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in sorted(adjacency[current], reverse=True):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    stack.append(neighbour)
        components.append(sorted(component))
    # Preserve a genuinely chapter-spanning constellation as one graph.  The
    # collision solver can use its branch structure to make the result compact.
    # Component packing is for maps dominated by several independent local
    # clusters, not for a main component that already contains most boxes.
    largest_component = max((len(component) for component in components), default=0)
    if routes and len(components) > 1 and largest_component * 5 < len(boxes) * 3:
        solved: list[tuple[list[int], list[int], list[int], int, int]] = []
        component_boxes: list[Box] = []
        for component_index, indices in enumerate(components):
            subset = [boxes[index] for index in indices]
            subset_x, subset_y = pack_boxes(subset, edges)
            min_x, min_y = min(subset_x), min(subset_y)
            subset_x = [value - min_x for value in subset_x]
            subset_y = [value - min_y for value in subset_y]
            width = max(x + box.width for x, box in zip(subset_x, subset))
            height = max(y + box.height for y, box in zip(subset_y, subset))
            solved.append((indices, subset_x, subset_y, width, height))
            component_boxes.append(Box(f"component:{component_index}", width, height, []))
        component_x, component_y = pack_boxes(component_boxes, [])
        result_x, result_y = [0] * len(boxes), [0] * len(boxes)
        for offset_x, offset_y, (indices, subset_x, subset_y, _width, _height) in zip(
            component_x, component_y, solved
        ):
            for index, local_x, local_y in zip(indices, subset_x, subset_y):
                result_x[index] = offset_x + local_x
                result_y[index] = offset_y + local_y
        return result_x, result_y

    # A collection with no cross-box routes is a region, not a hidden
    # dependency chain.  Seed it as a stable near-square grid before any
    # collision work.  Starting every box at (0, 0) makes the old resolver
    # choose the same axis repeatedly and produces a very tall diagonal.
    if not constraints[0] and not constraints[1]:
        candidates = []
        for columns in range(1, len(boxes) + 1):
            rows = (len(boxes) + columns - 1) // columns
            column_widths = [0] * columns
            row_heights = [0] * rows
            for index, box in enumerate(boxes):
                column, row = index % columns, index // columns
                column_widths[column] = max(column_widths[column], box.width)
                row_heights[row] = max(row_heights[row], box.height)
            column_x, row_y = [], []
            cursor = 0
            for width in column_widths:
                column_x.append(cursor)
                cursor += width + REGION_GAP
            total_width = max(1, cursor - REGION_GAP)
            cursor = 0
            for height in row_heights:
                row_y.append(cursor)
                cursor += height + REGION_GAP
            total_height = max(1, cursor - REGION_GAP)
            xs = [column_x[index % columns] for index in range(len(boxes))]
            ys = [row_y[index // columns] for index in range(len(boxes))]
            # Search every stable row-major grid because organizer groups vary
            # greatly in size.  Count-based sqrt grids can still be extremely
            # wide when one row contains several long local timelines.
            score = total_width * total_height + 1.0 * (
                total_width * total_width + total_height * total_height
            )
            candidates.append((score, abs(total_width - total_height), columns, xs, ys))
        return min(candidates, key=lambda value: value[:3])[3:]

    def solve(cs: list[list[tuple[int, int, int]]]) -> tuple[list[int], list[int]]:
        return distances(len(boxes), cs[0]), distances(len(boxes), cs[1])

    def score(xs: list[int], ys: list[int]) -> float:
        width = max(x + box.width for x, box in zip(xs, boxes))
        height = max(y + box.height for y, box in zip(ys, boxes))
        # Compactness is measured from occupied geometry, never padded bounds.
        # Mild shape preference selects among feasible packings; it never
        # stretches a valid one-dimensional dependency chain into a diagonal.
        length = sum(abs(xs[i]+a[0]-xs[j]-b[0]) + abs(ys[i]+a[1]-ys[j]-b[1]) for i,j,a,b in routes)
        return width * height + 0.08 * (width * width + height * height) + 40 * length

    xs, ys = solve(constraints)
    for _ in range(len(boxes) * len(boxes)):
        collision = None
        for i, a in enumerate(boxes):
            for j in range(i + 1, len(boxes)):
                b = boxes[j]
                gap = REGION_GAP if len(a.nodes) > 1 or len(b.nodes) > 1 else CARD_GAP
                if not (xs[i]+a.width+gap <= xs[j] or xs[j]+b.width+gap <= xs[i]
                        or ys[i]+a.height+gap <= ys[j] or ys[j]+b.height+gap <= ys[i]):
                    collision = (i, j, gap)
                    break
            if collision:
                break
        if collision is None:
            return xs, ys
        i, j, gap = collision
        candidates = []
        # Stable tie break keeps source order among otherwise unrelated peers.
        for axis, left, right in [(1,i,j), (0,i,j), (1,j,i), (0,j,i)]:
            cs = [list(constraints[0]), list(constraints[1])]
            size = boxes[left].width if axis == 0 else boxes[left].height
            cs[axis].append((left, right, size + gap))
            try:
                candidate_x, candidate_y = solve(cs)
            except ValueError:
                continue
            candidates.append((score(candidate_x,candidate_y), len(candidates), cs, candidate_x, candidate_y))
        if not candidates:
            raise ValueError(f"Canvas groups cannot be separated without reversing routes: {boxes[i].key}, {boxes[j].key}")
        _, _, constraints, xs, ys = min(candidates, key=lambda value: value[:2])
    raise ValueError("Canvas compact packing did not converge")


def group_box(key: str, label: str, children: list[Box], edges: list[dict[str, Any]], group_id: str) -> Box:
    xs, ys = pack_boxes(children, edges)
    nodes: list[dict[str, Any]] = []
    members = {}
    for box, x, y in zip(children, xs, ys):
        dx, dy = x + GROUP_INSET, y + GROUP_HEADER
        for node in box.nodes:
            nodes.append({**node, "x": node["x"] + dx, "y": node["y"] + dy})
        members.update({node_id: (a+dx,b+dy,w,h) for node_id,(a,b,w,h) in box.members.items()})
    width = max((x+box.width for x,box in zip(xs,children)), default=240) + GROUP_INSET*2
    height = max((y+box.height for y,box in zip(ys,children)), default=80) + GROUP_HEADER+GROUP_INSET
    group = {"id": group_id, "type": "group", "label": label, "x": 0, "y": 0, "width": width, "height": height}
    return Box(key, width, height, [group,*nodes], members)


def leaf_box(card: dict[str, Any]) -> Box:
    item = {**card, "x": 0, "y": 0}
    return Box(str(item["id"]), item["width"], item["height"], [item],
               {str(item["id"]): (0,0,item["width"],item["height"])})
