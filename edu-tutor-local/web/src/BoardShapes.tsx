import { useLayoutEffect, useRef, useState } from "react";
import type { Shape } from "./lesson";
import { partialPolyline, shapePoints } from "./boardGeometry";
export default function BoardShapes({
  shapes,
  writing,
  onPen,
}: {
  shapes: Shape[];
  writing: boolean;
  onPen: (point: { x: number; y: number } | null) => void;
}) {
  const root = useRef<SVGSVGElement>(null),
    [size, setSize] = useState({ width: 1, height: 1 });
  useLayoutEffect(() => {
    const element = root.current;
    if (!element) return;
    const measure = () => {
      const bounds = element.getBoundingClientRect();
      setSize({ width: bounds.width, height: bounds.height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const rendered = shapes.map((shape) => ({
    shape,
    ...partialPolyline(
      shapePoints(shape, size.width, size.height),
      shape.draw_progress ?? 1,
      size.width,
      size.height,
    ),
  }));
  const active =
    [...rendered]
      .reverse()
      .find((item) => (item.shape.draw_progress ?? 1) < 1) || rendered.at(-1);
  const x = active?.tip?.x,
    y = active?.tip?.y;
  useLayoutEffect(() => {
    const bounds = root.current?.getBoundingClientRect();
    onPen(
      writing && bounds && x !== undefined && y !== undefined
        ? { x: bounds.left + x, y: bounds.top + y }
        : null,
    );
  }, [x, y, writing, size, onPen]);
  return (
    <svg
      ref={root}
      className="shape-layer"
      aria-label="안전한 숫자 좌표 도형"
      viewBox={`0 0 ${size.width} ${size.height}`}
    >
      {rendered.map(({ shape, points, tip }) => (
        <g
          key={shape.element_id}
          data-board-shape={shape.element_id}
          data-board-element={shape.element_id}
        >
          <polyline
            data-drawn-path={shape.element_id}
            points={points.map((point) => `${point.x},${point.y}`).join(" ")}
            fill="none"
            stroke={
              { chalk: "#e6edd9", accent: "#e6cf84", warning: "#e9aa91" }[
                shape.stroke || "chalk"
              ]
            }
            strokeWidth={shape.stroke_width || 2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {shape.type === "arrow" && tip && shape.draw_progress === 1 && (
            <path
              d={`M${tip.x - 9},${tip.y - 5} L${tip.x},${tip.y} L${tip.x - 9},${tip.y + 5}`}
              transform={`rotate(${(Math.atan2((shape.geometry.y2 - shape.geometry.y1) * size.height, (shape.geometry.x2 - shape.geometry.x1) * size.width) * 180) / Math.PI} ${tip.x} ${tip.y})`}
              fill="none"
              stroke="#e6cf84"
              strokeWidth={shape.stroke_width || 2.5}
            />
          )}
        </g>
      ))}
      {writing && active?.tip && (
        <g
          data-pen-tip="true"
          data-tip-x={active.tip.x}
          data-tip-y={active.tip.y}
          transform={`translate(${active.tip.x} ${active.tip.y})`}
        >
          <circle r="4" fill="#f5e3a9" />
          <path d="M0 0 12 -15" stroke="#e6cf84" strokeWidth="4" />
        </g>
      )}
    </svg>
  );
}
