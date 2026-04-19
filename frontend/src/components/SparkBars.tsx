import { clamp } from "../lib/format";

export function SparkBars({
  values,
  title,
}: {
  values: number[];
  title: string;
}) {
  if (!values.length) {
    return <div className="empty-inline">No datapoints</div>;
  }

  const max = Math.max(...values.map((value) => Math.abs(value)), 1);

  return (
    <div className="sparkbars" aria-label={title} title={title}>
      {values.map((value, index) => {
        const size = clamp((Math.abs(value) / max) * 100, 8, 100);
        const className = value < 0 ? "sparkbar sparkbar-negative" : "sparkbar sparkbar-positive";
        return <span key={`${title}-${index}`} className={className} style={{ height: `${size}%` }} />;
      })}
    </div>
  );
}
