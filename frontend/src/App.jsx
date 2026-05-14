import { useEffect, useMemo, useState } from "react";

const STATUS_LABELS = {
  no_data: "Нет данных",
  scale_waiting: "Весы в режиме ожидания",
  waiting_tare: "Ждем тару",
  waiting_fill: "Оттарено, ждем заполнение",
  filling: "Наполняется",
  bucket_removed: "Ведро снято"
};

function today() {
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Europe/Kyiv",
    year: "numeric"
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function formatKg(value) {
  return `${Number(value || 0).toFixed(3)} кг`;
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Europe/Kyiv"
  });
}

function formatDuration(start, end) {
  if (!start || !end) return "-";
  const seconds = Math.max(0, Math.round((new Date(end) - new Date(start)) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes} мин ${rest} сек`;
}

function bucketMetricLabel(status) {
  return status === "bucket_removed" ? "Следующее ведро" : "Текущее ведро";
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers
    }
  });

  if (response.status === 401) {
    const error = new Error("Требуется вход");
    error.status = 401;
    throw error;
  }

  if (!response.ok) {
    const error = new Error(`${response.status} ${response.statusText}`);
    error.status = response.status;
    throw error;
  }

  return response;
}

async function getJson(url) {
  const response = await apiFetch(url);
  return response.json();
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await apiFetch("/api/login", {
        method: "POST",
        body: JSON.stringify({ username, password })
      });
      const payload = await response.json().catch(() => ({}));
      onLogin(payload.user || payload);
    } catch (err) {
      setError(err.status === 401 ? "Неверный логин или пароль" : err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-panel" onSubmit={handleSubmit}>
        <h1>Учет ведер</h1>
        <label>
          Логин
          <input
            autoComplete="username"
            autoFocus
            onChange={(event) => setUsername(event.target.value)}
            value={username}
          />
        </label>
        <label>
          Пароль
          <input
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            value={password}
          />
        </label>
        {error ? <div className="notice error">{error}</div> : null}
        <button disabled={loading || !username || !password} type="submit">
          {loading ? "Вход..." : "Войти"}
        </button>
      </form>
    </main>
  );
}

function BucketTable({ buckets, showDownload = false, onDownload }) {
  const colSpan = showDownload ? 6 : 5;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Начало</th>
            <th>Конец</th>
            <th>Вес</th>
            <th>Длительность</th>
            {showDownload ? <th>CSV</th> : null}
          </tr>
        </thead>
        <tbody>
          {buckets.length === 0 ? (
            <tr>
              <td className="empty" colSpan={colSpan}>
                Ведер пока нет
              </td>
            </tr>
          ) : (
            buckets.map((bucket, index) => (
              <tr key={bucket.id}>
                <td>{bucket.displayNumber ?? index + 1}</td>
                <td>{formatDateTime(bucket.start_timestamp)}</td>
                <td>{formatDateTime(bucket.end_timestamp)}</td>
                <td>{formatKg(bucket.max_weight)}</td>
                <td>{formatDuration(bucket.start_timestamp, bucket.end_timestamp)}</td>
                {showDownload ? (
                  <td>
                    <button
                      className="download-button"
                      onClick={() => onDownload(bucket)}
                      title="Скачать CSV"
                      type="button"
                    >
                      <span aria-hidden="true">↓</span>
                      <span className="sr-only">Скачать CSV</span>
                    </button>
                  </td>
                ) : null}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [user, setUser] = useState(null);
  const [tab, setTab] = useState("now");
  const [date, setDate] = useState(today());
  const [status, setStatus] = useState(null);
  const [todayBuckets, setTodayBuckets] = useState([]);
  const [history, setHistory] = useState({ bucket_count: 0, total_weight: 0, buckets: [] });
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      try {
        const payload = await getJson("/api/me");
        if (!cancelled) setUser(payload.user || payload);
      } catch (err) {
        if (!cancelled && err.status !== 401) setError(err.message);
      } finally {
        if (!cancelled) setAuthChecked(true);
      }
    }

    checkAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!user) return undefined;
    let cancelled = false;

    async function loadNow() {
      try {
        const [statusPayload, bucketsPayload] = await Promise.all([
          getJson("/api/status"),
          getJson(`/api/buckets?date=${today()}`)
        ]);
        if (!cancelled) {
          setStatus(statusPayload);
          setTodayBuckets(bucketsPayload.buckets || []);
          setError("");
        }
      } catch (err) {
        if (!cancelled) {
          if (err.status === 401) setUser(null);
          else setError(err.message);
        }
      }
    }

    loadNow();
    const timer = window.setInterval(loadNow, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [user]);

  useEffect(() => {
    if (!user) return undefined;
    let cancelled = false;

    async function loadHistory() {
      try {
        const payload = await getJson(`/api/buckets?date=${date}`);
        if (!cancelled) {
          setHistory(payload);
          setError("");
        }
      } catch (err) {
        if (!cancelled) {
          if (err.status === 401) setUser(null);
          else setError(err.message);
        }
      }
    }

    loadHistory();
    return () => {
      cancelled = true;
    };
  }, [date, user]);

  async function handleLogout() {
    try {
      await apiFetch("/api/logout", { method: "POST" });
    } catch (err) {
      if (err.status !== 401) setError(err.message);
    } finally {
      setUser(null);
      setStatus(null);
      setTodayBuckets([]);
      setHistory({ bucket_count: 0, total_weight: 0, buckets: [] });
    }
  }

  async function handleDownload(bucket) {
    try {
      const response = await apiFetch(`/api/buckets/${bucket.id}/measurements.csv`);
      const blob = await response.blob();
      const href = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = `bucket-${bucket.id}-measurements.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(href);
      setError("");
    } catch (err) {
      if (err.status === 401) setUser(null);
      else if (err.status === 404) {
        setError("Ведро обновилось. История перезагружена, нажмите скачать еще раз.");
        try {
          const payload = await getJson(`/api/buckets?date=${date}`);
          setHistory(payload);
        } catch {
          // Keep the original download error visible.
        }
      } else setError(err.message);
    }
  }

  function handleLogin(nextUser) {
    setUser(nextUser || { username: "user" });
    setError("");
  }

  const latestTime = status?.status === "scale_waiting" ? status?.device_status_timestamp : status?.latest_measurement?.timestamp;
  const numberedTodayBuckets = useMemo(
    () => todayBuckets.map((bucket, index) => ({ ...bucket, displayNumber: index + 1 })),
    [todayBuckets]
  );
  const recentBuckets = useMemo(() => [...numberedTodayBuckets].reverse().slice(0, 10), [numberedTodayBuckets]);
  const numberedHistoryBuckets = useMemo(
    () => (history.buckets || []).map((bucket, index) => ({ ...bucket, displayNumber: index + 1 })),
    [history.buckets]
  );
  const bucketLabel = bucketMetricLabel(status?.status);
  const username = user?.username || user?.name || "";

  if (!authChecked) {
    return (
      <main className="login-page">
        <div className="login-panel">Проверка входа...</div>
      </main>
    );
  }

  if (!user) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <main className="app">
      <header className="topbar">
        <h1>Учет ведер</h1>
        <div className="header-actions">
          <nav className="tabs" aria-label="Разделы">
            <button className={tab === "now" ? "active" : ""} onClick={() => setTab("now")} type="button">
              Сейчас
            </button>
            <button
              className={tab === "history" ? "active" : ""}
              onClick={() => setTab("history")}
              type="button"
            >
              История
            </button>
          </nav>
          {username ? <span className="user-name">{username}</span> : null}
          <button className="logout-button" onClick={handleLogout} type="button">
            Выйти
          </button>
        </div>
      </header>

      {error ? <div className="notice error">Ошибка API: {error}</div> : null}

      {tab === "now" ? (
        <section className="content">
          <div className="metrics">
            <Metric label="Текущий вес" value={formatKg(status?.current_weight)} />
            <Metric label="Ведер сегодня" value={status?.today_bucket_count ?? 0} />
            <Metric label="Вес сегодня" value={formatKg(status?.today_total_weight)} />
            <Metric label={bucketLabel} value={`#${status?.current_bucket ?? 1}`} />
          </div>

          <section className="panel">
            <div className="panel-title">Состояние</div>
            <dl className="status-list">
              <div>
                <dt>Статус</dt>
                <dd>{STATUS_LABELS[status?.status] || status?.status || "Нет данных"}</dd>
              </div>
              <div>
                <dt>Стабильный вес текущего ведра</dt>
                <dd>{formatKg(status?.current_bucket_max_weight)}</dd>
              </div>
              <div>
                <dt>Последнее измерение</dt>
                <dd>{formatDateTime(latestTime)}</dd>
              </div>
            </dl>
          </section>

          <section className="panel">
            <div className="panel-title">Последние ведра</div>
            <BucketTable buckets={recentBuckets} />
          </section>
        </section>
      ) : (
        <section className="content">
          <div className="toolbar">
            <label>
              Дата
              <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
            </label>
          </div>

          <div className="metrics">
            <Metric label="Ведер за дату" value={history.bucket_count || 0} />
            <Metric label="Вес за дату" value={formatKg(history.total_weight)} />
          </div>

          <section className="panel">
            <div className="panel-title">История за {date}</div>
            <BucketTable buckets={numberedHistoryBuckets} onDownload={handleDownload} showDownload />
          </section>
        </section>
      )}
    </main>
  );
}
