import type { Shape } from "./lesson";
export type Point = { x: number; y: number };
export function shapePoints(
  shape: Shape,
  width = 1000,
  height = 1000,
): Point[] {
  const g = shape.geometry;
  if (shape.type === "line" || shape.type === "arrow")
    return [
      { x: g.x1, y: g.y1 },
      { x: g.x2, y: g.y2 },
    ];
  if (shape.type === "rect")
    return [
      { x: g.x, y: g.y },
      { x: g.x + g.width, y: g.y },
      { x: g.x + g.width, y: g.y + g.height },
      { x: g.x, y: g.y + g.height },
      { x: g.x, y: g.y },
    ];
  if (shape.type === "ellipse" || shape.type === "circle") {
    const cx = shape.type === "circle" ? g.cx : g.x + g.width / 2,
      cy = shape.type === "circle" ? g.cy : g.y + g.height / 2;
    const rx =
        shape.type === "circle"
          ? (g.radius * Math.min(width, height)) / width
          : g.width / 2,
      ry =
        shape.type === "circle"
          ? (g.radius * Math.min(width, height)) / height
          : g.height / 2;
    return Array.from({ length: 65 }, (_, i) => ({
      x: cx + rx * Math.cos((i * Math.PI) / 32),
      y: cy + ry * Math.sin((i * Math.PI) / 32),
    }));
  }
  // Fixed cubic controls form a continuous brace. Only numeric size and
  // orientation come from lesson data, never a user supplied path string.
  const curves = [
    [
      [1, 0],
      [0.4, 0],
      [0.5, 0.25],
      [0.5, 0.4],
    ],
    [
      [0.5, 0.4],
      [0.5, 0.46],
      [0, 0.46],
      [0, 0.5],
    ],
    [
      [0, 0.5],
      [0, 0.54],
      [0.5, 0.54],
      [0.5, 0.6],
    ],
    [
      [0.5, 0.6],
      [0.5, 0.75],
      [0.4, 1],
      [1, 1],
    ],
  ];
  const points = curves.flatMap((curve, segment) =>
    Array.from({ length: 13 }, (_, i) => {
      const t = i / 12,
        u = 1 - t;
      return {
        x:
          u * u * u * curve[0][0] +
          3 * u * u * t * curve[1][0] +
          3 * u * t * t * curve[2][0] +
          t * t * t * curve[3][0],
        y:
          u * u * u * curve[0][1] +
          3 * u * u * t * curve[1][1] +
          3 * u * t * t * curve[2][1] +
          t * t * t * curve[3][1],
      };
    }).slice(segment ? 1 : 0),
  );
  return points.map((point) => {
    const orientation = shape.orientation || "left";
    if (orientation === "right")
      return { x: g.x + (1 - point.x) * g.width, y: g.y + point.y * g.height };
    if (orientation === "top")
      return { x: g.x + point.y * g.width, y: g.y + point.x * g.height };
    if (orientation === "bottom")
      return { x: g.x + point.y * g.width, y: g.y + (1 - point.x) * g.height };
    return { x: g.x + point.x * g.width, y: g.y + point.y * g.height };
  });
}
export function partialPolyline(
  points: Point[],
  progress: number,
  width: number,
  height: number,
) {
  if (!points.length) return { points: [], tip: null };
  const scaled = points.map((point) => ({
    x: point.x * width,
    y: point.y * height,
  }));
  const lengths = scaled
    .slice(1)
    .map((point, i) =>
      Math.hypot(point.x - scaled[i].x, point.y - scaled[i].y),
    );
  let remaining =
    lengths.reduce((a, b) => a + b, 0) * Math.min(1, Math.max(0, progress));
  const visible = [scaled[0]];
  for (let i = 0; i < lengths.length; i++) {
    if (remaining >= lengths[i]) {
      visible.push(scaled[i + 1]);
      remaining -= lengths[i];
    } else {
      const fraction = lengths[i] ? remaining / lengths[i] : 0;
      visible.push({
        x: scaled[i].x + (scaled[i + 1].x - scaled[i].x) * fraction,
        y: scaled[i].y + (scaled[i + 1].y - scaled[i].y) * fraction,
      });
      break;
    }
  }
  return { points: visible, tip: visible.at(-1)! };
}
