export function StatusBadge({ value }: { value: string | null | undefined }) {
  const normalized = (value ?? "unknown").toLowerCase();
  const tone =
    normalized.includes("failed") || normalized.includes("discrepancy")
      ? "danger"
      : normalized.includes("sent") || normalized.includes("completed") || normalized.includes("active")
        ? "success"
        : normalized.includes("pending")
          ? "warning"
          : "neutral";

  const labels: Record<string, string> = {
    active: "Активна",
    completed: "Завершена",
    pending: "Очікує",
    sent: "Надіслано",
    failed: "Помилка",
    unknown: "Невідомо",
    control_discrepancy: "Розбіжність контролю",
    primary_negative_delta: "Негативна дельта",
  };

  return <span className={`status-badge status-${tone}`}>{labels[normalized] ?? value ?? "Невідомо"}</span>;
}
