import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuth } from "./context/AuthContext";
import { AdminSettingsPage } from "./pages/AdminSettingsPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { BucketDetailsPage } from "./pages/BucketDetailsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";

function App() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="buckets/:bucketId" element={<BucketDetailsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route
          path="settings"
          element={
            <ProtectedRoute requireRole="admin">
              <AdminSettingsPage />
            </ProtectedRoute>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to={isAuthenticated ? "/" : "/login"} replace />} />
    </Routes>
  );
}

export default App;
