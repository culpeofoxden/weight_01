import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { StatCard } from "../components/StatCard";
import { useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import { formatSignedGrams } from "../lib/format";
import type { AnalyticsSummaryResponse, AlertResponse } from "../types/api";

export function AnalyticsPage() {
  const { token } = useAuth();
  const [summary, setSummary] = useState<AnalyticsSummaryResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      return;
    }

    setLoading(true);
    setError(null);

    Promise.all([api.getAnalyticsSummary(token), api.getAlerts(token, {})])
      .then(([summaryResponse, alertResponse]) => {
        setSummary(summaryResponse);
        setAlerts(alertResponse);
      })
      .catch((requestError) => {
        if (requestError instanceof ApiError) {
          setError(requestError.message);
        } else {
          setError("Не вдалося завантажити аналітику");
        }
      })
      .finally(() => setLoading(false));
  }, [token]);

  const primaryAlerts = useMemo(
    () => alerts.filter((alert) => alert.alert_type === "primary_negative_delta").length,
    [alerts],
  );
  const discrepancyAlerts = useMemo(
    () => alerts.filter((alert) => alert.alert_type === "control_discrepancy").length,
    [alerts],
  );
  const maxRangeCount = useMemo(
    () => Math.max(...(summary?.common_loss_ranges.map((range) => range.count) ?? [1])),
    [summary],
  );

  if (loading) {
    return <div className="screen-state">Завантаження аналітики...</div>;
  }

  if (error) {
    return <div className="error-banner">{error}</div>;
  }

  if (!summary) {
    return <EmptyState title="Аналітика недоступна" message="Backend не повернув аналітичні дані." />;
  }

  return (
    <div className="page-stack">
      <section className="grid grid-4">
        <StatCard label="Усього відер" value={summary.total_buckets} hint="Опрацьовані primary-сесії" accent="neutral" />
        <StatCard label="Алерти аномалій" value={summary.anomaly_alerts} hint="Кількість алертів негативної дельти" accent="danger" />
        <StatCard
          label="Алерти розбіжностей"
          value={summary.discrepancy_alerts}
          hint="Кількість алертів невідповідності контролю"
          accent="warning"
        />
        <StatCard
          label="Середня розбіжність"
          value={formatSignedGrams(Math.round(summary.average_discrepancy_grams))}
          hint="Середній контроль мінус очікувана вага"
          accent="success"
        />
      </section>

      <section className="grid grid-2">
        <section className="panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Розподіл</p>
              <h3>Типові діапазони втрат</h3>
            </div>
          </div>
          <div className="range-list">
            {summary.common_loss_ranges.map((range) => {
              const width = `${Math.max((range.count / maxRangeCount) * 100, 8)}%`;
              return (
                <div key={range.label} className="range-row">
                  <div className="range-meta">
                    <span>{range.label}</span>
                    <strong>{range.count}</strong>
                  </div>
                  <div className="range-track">
                    <div className="range-bar" style={{ width }} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Структура алертів</p>
              <h3>Склад подій</h3>
            </div>
          </div>
          <div className="mix-grid">
            <div className="mix-card">
              <span className="mix-label">Primary негативна дельта</span>
              <strong>{primaryAlerts}</strong>
            </div>
            <div className="mix-card">
              <span className="mix-label">Контрольна розбіжність</span>
              <strong>{discrepancyAlerts}</strong>
            </div>
            <div className="mix-card">
              <span className="mix-label">Усі записи алертів</span>
              <strong>{alerts.length}</strong>
            </div>
          </div>
        </section>
      </section>
    </div>
  );
}
