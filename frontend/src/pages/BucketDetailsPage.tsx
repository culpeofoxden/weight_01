import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { SparkBars } from "../components/SparkBars";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../context/AuthContext";
import { api, ApiError, getApiBaseUrl, getMockBucketCsv, isMockApiEnabled } from "../lib/api";
import { formatDateTime, formatSignedGrams } from "../lib/format";
import type { BucketDetailResponse } from "../types/api";

export function BucketDetailsPage() {
  const { bucketId = "" } = useParams();
  const { token } = useAuth();
  const [data, setData] = useState<BucketDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!token || !bucketId) {
      return;
    }

    setLoading(true);
    setError(null);

    api
      .getBucket(token, bucketId)
      .then((response) => setData(response))
      .catch((requestError) => {
        if (requestError instanceof ApiError) {
          setError(requestError.message);
        } else {
          setError("Не вдалося завантажити дані відра");
        }
      })
      .finally(() => setLoading(false));
  }, [token, bucketId]);

  const weightValues = useMemo(() => data?.weight_logs.map((row) => row.weight_grams) ?? [], [data]);
  const deltaValues = useMemo(() => data?.weight_logs.map((row) => row.delta_grams) ?? [], [data]);

  async function handleDownload() {
    if (!token || !bucketId) {
      return;
    }

    setDownloading(true);
    try {
      let blob: Blob;

      if (isMockApiEnabled()) {
        blob = new Blob([getMockBucketCsv(bucketId)], { type: "text/csv;charset=utf-8" });
      } else {
        const response = await fetch(`${getApiBaseUrl()}/api/v1/buckets/${bucketId}/raw-logs.csv`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          throw new Error("Download failed");
        }
        blob = await response.blob();
      }
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${bucketId}-raw-logs.csv`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch {
      setError("Не вдалося завантажити сирі логи");
    } finally {
      setDownloading(false);
    }
  }

  if (loading) {
    return <div className="screen-state">Завантаження телеметрії відра...</div>;
  }

  if (error) {
    return <div className="error-banner">{error}</div>;
  }

  if (!data) {
    return <EmptyState title="Відро не знайдено" message="У поточному наборі даних немає запитаного ID відра." />;
  }

  return (
    <div className="page-stack">
      <section className="panel hero-panel">
        <div>
          <p className="eyebrow">Трасування відра</p>
          <h2>{bucketId}</h2>
          <p className="muted">
            Сесія {data.summary.bucket_session_id ?? "н/д"} на станції {data.summary.primary_station_id ?? "н/д"}
          </p>
        </div>
        <div className="hero-actions">
          <StatusBadge value={data.summary.status} />
          <button className="primary-button" type="button" onClick={handleDownload} disabled={downloading}>
            {downloading ? "Підготовка CSV..." : "Завантажити сирі логи"}
          </button>
        </div>
      </section>

      <section className="grid grid-4">
        <StatCard
          label="Очікувана фінальна"
          value={`${data.summary.expected_final_weight_grams ?? "н/д"} g`}
          hint="Очікувана завершальна вага на primary-станції"
          accent="neutral"
        />
        <StatCard
          label="Контрольна вага"
          value={`${data.summary.control_weight_grams ?? "н/д"} g`}
          hint="Останнє вимірювання на контрольній станції"
          accent="success"
        />
        <StatCard
          label="Розбіжність"
          value={formatSignedGrams(data.summary.discrepancy_grams)}
          hint="Контроль мінус очікувана вага"
          accent={(data.summary.discrepancy_grams ?? 0) < 0 ? "danger" : "warning"}
        />
        <StatCard
          label="Виявлені алерти"
          value={data.alerts.length}
          hint="Алерти, пов'язані з цим відром"
          accent={data.alerts.length ? "danger" : "success"}
        />
      </section>

      <section className="grid grid-2">
        <section className="panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Вагова телеметрія</p>
              <h3>Тренд primary-логів</h3>
            </div>
            <SparkBars values={weightValues} title="Тренд ваги" />
          </div>
          <div className="table-wrap tall-table">
            <table className="data-table">
              <thead>
                <tr>
                    <th>Час запису</th>
                    <th>Станція</th>
                    <th>Вага</th>
                    <th>Дельта</th>
                    <th>Причина</th>
                </tr>
              </thead>
              <tbody>
                {data.weight_logs.map((row) => (
                  <tr key={row.event_id}>
                    <td>{formatDateTime(row.recorded_at_utc)}</td>
                    <td>{row.station_id}</td>
                    <td>{row.weight_grams} g</td>
                    <td className={row.delta_grams < 0 ? "danger-text" : ""}>{formatSignedGrams(row.delta_grams)}</td>
                    <td>{row.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Шкала аномалій</p>
              <h3>Контекст негативних змін</h3>
            </div>
            <SparkBars values={deltaValues} title="Тренд дельти" />
          </div>

          {data.anomaly_events.length === 0 ? (
            <EmptyState title="Немає аномалій" message="Для цього відра не зафіксовано кандидатів на аномалію." />
          ) : (
            <div className="timeline-list">
              {data.anomaly_events.map((event) => (
                <article className="timeline-card" key={event.anomaly_event_id}>
                  <div className="timeline-head">
                    <strong>{event.event_type}</strong>
                    <span>{formatDateTime(event.observed_at_utc)}</span>
                  </div>
                  <p className="muted">
                    {event.station_id} | delta {formatSignedGrams(event.delta_grams)} | persistence {event.persistence_seconds}s
                  </p>
                  <p className="muted">
                    {event.weight_before_grams} g to {event.weight_after_grams} g
                  </p>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>

      <section className="grid grid-2">
        <section className="panel">
          <div className="section-head">
            <div>
              <p className="eyebrow">Контрольні записи</p>
              <h3>Ручна перевірка</h3>
            </div>
          </div>
          {data.control_records.length === 0 ? (
            <EmptyState title="Немає контрольних записів" message="Це відро ще не зважували на контрольній станції." />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Час запису</th>
                    <th>Станція</th>
                    <th>Вага</th>
                    <th>Примітка оператора</th>
                  </tr>
                </thead>
                <tbody>
                  {data.control_records.map((row) => (
                    <tr key={row.control_weight_record_id}>
                      <td>{formatDateTime(row.recorded_at_utc)}</td>
                      <td>{row.station_id}</td>
                      <td>{row.control_weight_grams} g</td>
                      <td>{row.operator_note ?? "н/д"}</td>
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
              <p className="eyebrow">Алерти</p>
              <h3>Сповіщення для цього відра</h3>
            </div>
            <Link className="text-link" to="/analytics">
              Переглянути аналітику
            </Link>
          </div>

          {data.alerts.length === 0 ? (
            <EmptyState title="Немає алертів" message="Для цього відра немає пов'язаних записів алертів." />
          ) : (
            <div className="alert-list">
              {data.alerts.map((alert) => (
                <article className="alert-card" key={`${alert.alert_type}-${alert.detected_at_utc}`}>
                  <div className="alert-head">
                    <div>
                      <p className="alert-type">{alert.alert_type}</p>
                      <p className="muted">{formatDateTime(alert.detected_at_utc)}</p>
                    </div>
                    <StatusBadge value={alert.status} />
                  </div>
                  <p>{alert.message_text}</p>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>
    </div>
  );
}
