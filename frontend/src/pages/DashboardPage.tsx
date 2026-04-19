import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { SparkBars } from "../components/SparkBars";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import { formatDateTime, formatSignedGrams } from "../lib/format";
import type { AlertResponse, BucketSummaryResponse } from "../types/api";

export function DashboardPage() {
  const { token } = useAuth();
  const [draftBucketFilter, setDraftBucketFilter] = useState("");
  const [bucketFilter, setBucketFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [buckets, setBuckets] = useState<BucketSummaryResponse[]>([]);
  const [alerts, setAlerts] = useState<AlertResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setBucketFilter(draftBucketFilter.trim()), 250);
    return () => window.clearTimeout(timeoutId);
  }, [draftBucketFilter]);

  useEffect(() => {
    if (!token) {
      return;
    }

    setLoading(true);
    setError(null);

    Promise.all([
      api.getBuckets(token, { bucket_id: bucketFilter || undefined, status: statusFilter || undefined }),
      api.getAlerts(token, { bucket_id: bucketFilter || undefined }),
    ])
      .then(([bucketRows, alertRows]) => {
        setBuckets(bucketRows);
        setAlerts(alertRows.slice(0, 8));
      })
      .catch((requestError) => {
        if (requestError instanceof ApiError) {
          setError(requestError.message);
        } else {
          setError("Не вдалося завантажити панель");
        }
      })
      .finally(() => setLoading(false));
  }, [token, bucketFilter, statusFilter]);

  const activeBuckets = useMemo(() => buckets.filter((bucket) => bucket.status === "active").length, [buckets]);
  const discrepancyBuckets = useMemo(
    () => buckets.filter((bucket) => (bucket.discrepancy_grams ?? 0) < 0).length,
    [buckets],
  );
  const sparkValues = useMemo(
    () => buckets.slice(0, 18).map((bucket) => bucket.discrepancy_grams ?? 0),
    [buckets],
  );

  return (
    <div className="page-stack">
      <section className="grid grid-4">
        <StatCard label="Відра у вибірці" value={buckets.length} hint="Поточні відфільтровані primary-сесії" accent="neutral" />
        <StatCard label="Активні сесії" value={activeBuckets} hint="Відра, що зараз проходять лінію" accent="success" />
        <StatCard
          label="Негативні розбіжності"
          value={discrepancyBuckets}
          hint="Відра, де контрольна вага нижча за очікувану"
          accent="warning"
        />
        <StatCard label="Останні алерти" value={alerts.length} hint="Останні записи зі стрічки подій" accent="danger" />
      </section>

      <section className="panel filters-panel">
        <div>
          <p className="eyebrow">Фільтри панелі</p>
          <h3>Черга відер</h3>
        </div>
        <div className="filters-row">
          <label className="field compact-field">
            <span>ID відра</span>
            <input
              value={draftBucketFilter}
              onChange={(event) => setDraftBucketFilter(event.target.value)}
              placeholder="Фільтр за ID відра"
            />
          </label>
          <label className="field compact-field">
            <span>Статус</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="">Усі</option>
              <option value="active">Активні</option>
              <option value="completed">Завершені</option>
              <option value="unknown">Невідомі</option>
            </select>
          </label>
        </div>
      </section>

      <section className="grid grid-2">
        <section className="panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Primary Sessions</p>
              <h3>Панель відер</h3>
            </div>
            <SparkBars values={sparkValues} title="Зріз розбіжностей" />
          </div>

          {loading ? (
            <div className="screen-state inset-state">Завантаження відер...</div>
          ) : error ? (
            <div className="error-banner">{error}</div>
          ) : buckets.length === 0 ? (
            <EmptyState title="Відра не знайдено" message="Змініть фільтри або створіть тестові дані у backend." />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Відро</th>
                    <th>Primary-станція</th>
                    <th>Початок</th>
                    <th>Очікувана вага</th>
                    <th>Контроль</th>
                    <th>Розбіжність</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {buckets.map((bucket) => (
                    <tr key={bucket.bucket_id}>
                      <td>
                        <Link className="text-link" to={`/buckets/${bucket.bucket_id}`}>
                          {bucket.bucket_id}
                        </Link>
                      </td>
                      <td>{bucket.primary_station_id ?? "н/д"}</td>
                      <td>{formatDateTime(bucket.primary_started_at_utc)}</td>
                      <td>{bucket.expected_final_weight_grams ?? "н/д"} g</td>
                      <td>{bucket.control_weight_grams ?? "н/д"} g</td>
                      <td className={(bucket.discrepancy_grams ?? 0) < 0 ? "danger-text" : ""}>
                        {formatSignedGrams(bucket.discrepancy_grams)}
                      </td>
                      <td>
                        <StatusBadge value={bucket.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Alert Feed</p>
              <h3>Останні події</h3>
            </div>
          </div>

          {alerts.length === 0 ? (
            <EmptyState title="Немає алертів" message="Для поточного фільтра система ще не згенерувала подій." />
          ) : (
            <div className="alert-list">
              {alerts.map((alert) => (
                <article key={`${alert.bucket_id}-${alert.detected_at_utc}-${alert.alert_type}`} className="alert-card">
                  <div className="alert-head">
                    <div>
                      <p className="alert-type">{alert.alert_type}</p>
                      <Link className="text-link" to={`/buckets/${alert.bucket_id}`}>
                        {alert.bucket_id}
                      </Link>
                    </div>
                    <StatusBadge value={alert.status} />
                  </div>
                  <p className="muted">{alert.message_text}</p>
                  <div className="alert-meta">
                    <span>{alert.station_id}</span>
                    <span>{formatDateTime(alert.detected_at_utc)}</span>
                    <span>{formatSignedGrams(alert.delta_grams)}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>
    </div>
  );
}
