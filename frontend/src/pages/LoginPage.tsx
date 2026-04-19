import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const locationState = location.state as { from?: { pathname?: string } } | null;
  const from = locationState?.from?.pathname ?? "/";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await login({ email, password });
      navigate(from, { replace: true });
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        setError(requestError.message);
      } else {
        setError("Не вдалося створити сесію");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-frame">
        <section className="login-copy">
          <p className="eyebrow">Моніторинг бурштинових відер</p>
          <h1>Захищена операторська консоль для виявлення втрат по кожному відру.</h1>
          <p className="muted login-lead">
            Переглядайте сесії відер, аналізуйте сирі вагові логи, перевіряйте аномалії та змінюйте пороги системи з
            єдиного робочого простору.
          </p>
          <div className="login-highlights">
            <div className="panel info-panel">
              <span className="info-kicker">Панель</span>
              <strong>Операційна черга</strong>
              <p>Пріоритезація за відрами для активних і завершених сесій.</p>
            </div>
            <div className="panel info-panel">
              <span className="info-kicker">Аналітика</span>
              <strong>Розподіл втрат</strong>
              <p>Швидкий зріз алертів, розбіжностей і типових діапазонів втрати.</p>
            </div>
          </div>
        </section>

        <section className="panel login-card">
          <p className="eyebrow">Обмежений доступ</p>
          <h2>Вхід</h2>
          <form className="form-stack" onSubmit={handleSubmit}>
            <label className="field">
              <span>Ел. пошта</span>
              <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required />
            </label>
            <label className="field">
              <span>Пароль</span>
              <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required />
            </label>
            {error && <div className="error-banner">{error}</div>}
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "Вхід..." : "Увійти"}
            </button>
          </form>

          <div className="credentials-hint">
            <p className="muted">Тестові облікові записи з backend:</p>
            <p>`admin@example.com / admin123`</p>
            <p>`viewer@example.com / viewer123`</p>
          </div>
        </section>
      </div>
    </div>
  );
}
