import { FormEvent, useEffect, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { useAuth } from "../context/AuthContext";
import { api, ApiError } from "../lib/api";
import type { GlobalSettingItem } from "../types/api";

export function AdminSettingsPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<GlobalSettingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      return;
    }

    setLoading(true);
    api
      .getSettings(token)
      .then((response) => setItems(response))
      .catch((requestError) => {
        if (requestError instanceof ApiError) {
          setError(requestError.message);
        } else {
          setError("Не вдалося завантажити налаштування");
        }
      })
      .finally(() => setLoading(false));
  }, [token]);

  function updateItem(index: number, key: keyof GlobalSettingItem, value: string) {
    setItems((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, [key]: value } : item)));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.updateSettings(token, { items });
      setItems(response);
      setSuccess("Налаштування успішно збережено");
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        setError(requestError.message);
      } else {
        setError("Не вдалося зберегти налаштування");
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="screen-state">Завантаження адмін-налаштувань...</div>;
  }

  if (!items.length) {
    return <EmptyState title="Налаштування не знайдено" message="Backend не повернув жодного доступного для зміни параметра." />;
  }

  return (
    <div className="page-stack">
      <section className="panel hero-panel">
        <div>
          <p className="eyebrow">Адмін-керування</p>
          <h2>Глобальні налаштування</h2>
          <p className="muted">Пороги та допуски, які використовуються в ingest та alert pipeline.</p>
        </div>
      </section>

      <form className="panel form-stack settings-form" onSubmit={handleSubmit}>
        {error && <div className="error-banner">{error}</div>}
        {success && <div className="success-banner">{success}</div>}

        {items.map((item, index) => (
          <div className="settings-row" key={item.key}>
            <label className="field">
              <span>Ключ</span>
              <input value={item.key} disabled />
            </label>
            <label className="field">
              <span>Значення</span>
              <input value={item.value} onChange={(event) => updateItem(index, "value", event.target.value)} />
            </label>
            <label className="field settings-description">
              <span>Опис</span>
              <input
                value={item.description}
                onChange={(event) => updateItem(index, "description", event.target.value)}
              />
            </label>
          </div>
        ))}

        <div className="settings-actions">
          <button className="primary-button" type="submit" disabled={saving}>
            {saving ? "Збереження..." : "Зберегти налаштування"}
          </button>
        </div>
      </form>
    </div>
  );
}
