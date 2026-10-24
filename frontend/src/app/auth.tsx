import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { api, ApiError, setCsrfToken, setUnauthorizedHandler } from "@/lib/api";
import type { Me, Role } from "@/types/api";

const RANK: Record<Role, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };

interface AuthState {
  me: Me | null;
  loading: boolean;
  can: (minimum: Role) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        const me = await api.get<Me>("/auth/me");
        setCsrfToken(me.csrf_token);
        return me;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });

  useEffect(() => {
    setUnauthorizedHandler(() => { setCsrfToken(null); qc.setQueryData(["me"], null); qc.removeQueries({ predicate: (x) => x.queryKey[0] !== "me" }); });
    return () => setUnauthorizedHandler(null);
  }, [qc]);

  const login = useCallback(async (email: string, password: string) => {
    const me = await api.post<Me>("/auth/login", { email, password });
    setCsrfToken(me.csrf_token);
    qc.setQueryData(["me"], me);
  }, [qc]);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } finally {
      setCsrfToken(null);
      qc.clear();
      qc.setQueryData(["me"], null);
    }
  }, [qc]);

  const me = q.data ?? null;
  const value = useMemo<AuthState>(() => ({ me, loading: q.isLoading, can: (min) => !!me && RANK[me.role] >= RANK[min], login, logout }), [me, q.isLoading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
