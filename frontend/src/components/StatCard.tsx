import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  hint,
  accent = "neutral",
}: {
  label: string;
  value: ReactNode;
  hint: string;
  accent?: "neutral" | "danger" | "warning" | "success";
}) {
  return (
    <section className={`panel stat-card accent-${accent}`}>
      <p className="stat-label">{label}</p>
      <div className="stat-value">{value}</div>
      <p className="muted">{hint}</p>
    </section>
  );
}
