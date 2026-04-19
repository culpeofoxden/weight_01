import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../types/api";

export function ProtectedRoute({
  children,
  requireRole,
}: {
  children: JSX.Element;
  requireRole?: UserRole;
}) {
  const location = useLocation();
  const { isAuthenticated, loading, hasRole } = useAuth();

  if (loading) {
    return <div className="screen-state">Loading secure workspace...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (requireRole && !hasRole(requireRole)) {
    return <Navigate to="/" replace />;
  }

  return children;
}
