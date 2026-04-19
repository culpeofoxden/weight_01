import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, registerUnauthorizedHandler } from "../lib/api";
import { clearStoredToken, getStoredToken, setStoredToken } from "../lib/storage";
import type { LoginRequest, UserResponse, UserRole } from "../types/api";

interface AuthContextValue {
  user: UserResponse | null;
  token: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  hasRole: (role: UserRole) => boolean;
  login: (payload: LoginRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    clearStoredToken();
    setToken(null);
    setUser(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    registerUnauthorizedHandler(logout);
    return () => registerUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);

    api
      .me(token)
      .then((nextUser) => {
        if (active) {
          setUser(nextUser);
          setLoading(false);
        }
      })
      .catch((error) => {
        if (!active) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          logout();
          return;
        }
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [token, logout]);

  const login = useCallback(async (payload: LoginRequest) => {
    const response = await api.login(payload);
    setStoredToken(response.access_token);
    setToken(response.access_token);
    const nextUser = await api.me(response.access_token);
    setUser(nextUser);
    setLoading(false);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      loading,
      isAuthenticated: Boolean(token && user),
      hasRole: (role) => Boolean(user?.roles.includes(role)),
      login,
      logout,
    }),
    [user, token, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
