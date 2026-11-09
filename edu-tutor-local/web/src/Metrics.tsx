type RecordValue = {
  step?: number;
  loss?: number;
  learning_rate?: number;
  grad_norm?: number;
  elapsed_seconds?: number;
  samples_per_second?: number;
  peak_vram_gib?: number;
  [key: string]: unknown;
};
function Plot({
  records,
  metric,
  label,
}: {
  records: RecordValue[];
  metric: "loss" | "learning_rate" | "samples_per_second" | "peak_vram_gib";
  label: string;
}) {
  const points = records.filter(
    (row) => Number.isFinite(row.step) && Number.isFinite(row[metric]),
  );
  if (!points.length)
    return (
      <div className="metric-empty">
        <strong>{label}</strong>
        <span>아직 기록 없음</span>
      </div>
    );
  const xs = points.map((p) => p.step!),
    ys = points.map((p) => p[metric]!),
    minX = Math.min(...xs),
    maxX = Math.max(...xs),
    minY = Math.min(...ys),
    maxY = Math.max(...ys);
  const x = (value: number) => 48 + ((value - minX) / (maxX - minX || 1)) * 340,
    y = (value: number) => 143 - ((value - minY) / (maxY - minY || 1)) * 110;
  const tickLabel = (value: number) =>
    value !== 0 && (Math.abs(value) < 0.001 || Math.abs(value) >= 100000)
      ? value.toExponential(1)
      : value.toPrecision(3);
  return (
    <figure className="metric-plot">
      <figcaption>
        {label}
        <span>실제 {points.length}개 기록</span>
      </figcaption>
      <svg
        viewBox="0 0 420 178"
        role="img"
        aria-label={`${label}, optimizer step ${minX}부터 ${maxX}까지. 값 ${minY}부터 ${maxY}.`}
      >
        <line x1="48" y1="143" x2="395" y2="143" stroke="#d1dbc6" />
        <line x1="48" y1="28" x2="48" y2="143" stroke="#d1dbc6" />
        {points.length > 1 && (
          <polyline
            points={points
              .map((p) => `${x(p.step!)},${y(p[metric]!)}`)
              .join(" ")}
            stroke="#76985a"
            fill="none"
            strokeWidth="2"
          />
        )}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={x(p.step!)}
            cy={y(p[metric]!)}
            r="3"
            fill="#76985a"
          >
            <title>
              step {p.step}: {p[metric]}
            </title>
          </circle>
        ))}
        <text x="43" y="31" textAnchor="end">
          {tickLabel(maxY)}
        </text>
        <text x="43" y="147" textAnchor="end">
          {tickLabel(minY)}
        </text>
        <text x="48" y="162">
          {minX}
        </text>
        <text x="388" y="162" textAnchor="end">
          {maxX}
        </text>
        <text x="218" y="174" textAnchor="middle">
          optimizer step
        </text>
      </svg>
    </figure>
  );
}
export default function Metrics({ records }: { records?: RecordValue[] }) {
  if (!records?.length)
    return (
      <p className="fine-print">
        아직 기록된 학습 지표가 없습니다. 측정한 값이 생기면 표시합니다.
      </p>
    );
  const measured = records.map((record) => ({
    ...record,
    peak_vram_gib:
      typeof record.peak_vram_bytes === "number"
        ? record.peak_vram_bytes / 1024 ** 3
        : undefined,
  }));
  return (
    <div className="real-metrics">
      <div className="metric-grid">
        <Plot records={records} metric="loss" label="학습 loss (정답률 아님)" />
        <Plot
          records={records}
          metric="learning_rate"
          label="학습률 (learning rate)"
        />
        <Plot
          records={measured}
          metric="samples_per_second"
          label="실측 누적 처리량 (sample/s)"
        />
        <Plot
          records={measured}
          metric="peak_vram_gib"
          label="학습 프로세스 최대 CUDA 할당량 (GiB)"
        />
      </div>
      <details>
        <summary>측정값 표 · 기록된 값만 표시</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>step</th>
                <th>loss</th>
                <th>learning rate</th>
                <th>grad norm</th>
                <th>경과 초</th>
                <th>sample/s</th>
                <th>최대 CUDA 할당 GiB</th>
              </tr>
            </thead>
            <tbody>
              {measured.map((row, i) => (
                <tr key={i}>
                  <td>{row.step ?? "—"}</td>
                  <td>{row.loss ?? "—"}</td>
                  <td>{row.learning_rate ?? "—"}</td>
                  <td>{row.grad_norm ?? "—"}</td>
                  <td>{row.elapsed_seconds ?? "—"}</td>
                  <td>{row.samples_per_second ?? "—"}</td>
                  <td>{row.peak_vram_gib?.toFixed(2) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
