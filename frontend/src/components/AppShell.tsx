import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

export function AppShell() {
  const { user, logout, hasRole } = useAuth();

  return (
    <div className="app-shell">
      <aside className="sidebar panel">
        <div>
          <p className="eyebrow">Бурштинові відра</p>
          <h1 className="sidebar-title">Промисловий монітор</h1>
          <p className="muted">Операційний інтерфейс для майстрів лінії та адміністраторів.</p>
        </div>

        <nav className="nav-stack">
          <NavLink to="/" end className={navClass}>
            Панель
          </NavLink>
          <NavLink to="/analytics" className={navClass}>
            Аналітика
          </NavLink>
          {hasRole("admin") && (
            <NavLink to="/settings" className={navClass}>
              Налаштування
            </NavLink>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="user-chip">
            <span className="user-chip-label">{user?.email}</span>
            <span className="user-chip-meta">{user?.roles.join(", ")}</span>
          </div>
          <button type="button" className="ghost-button" onClick={logout}>
            Вийти
          </button>
        </div>
      </aside>

      <main className="content">
        <header className="topbar panel">
          <div>
            <p className="eyebrow">Операційна панель</p>
            <h2 className="topbar-title">Відстеження відер, контроль аномалій і звірка ваги</h2>
          </div>
          <div className="topbar-status">
            <span className="signal-dot" />
            Захищена сесія
          </div>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
