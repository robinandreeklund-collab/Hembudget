import { useEffect, useState } from "react";
import { api, clearToken, getToken, setToken } from "@/api/client";

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [initialized, setInitialized] = useState<boolean | null>(null);
  const [demoMode, setDemoMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [backendError, setBackendError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const s = await api<{ initialized: boolean; demo_mode?: boolean }>(
          "/status",
        );
        setInitialized(s.initialized);
        if (s.demo_mode) {
          setDemoMode(true);
          if (!getToken()) {
            setToken("demo");
            setTokenState("demo");
          }
        }
      } catch (e) {
        setInitialized(null);
        setBackendError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function login(password: string) {
    const res = await api<{ token: string }>("/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    setToken(res.token);
    setTokenState(res.token);
    return res.token;
  }

  async function initialize(password: string) {
    const res = await api<{ token: string }>("/init", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    setToken(res.token);
    setTokenState(res.token);
    setInitialized(true);
    return res.token;
  }

  function logout() {
    api("/logout", { method: "POST" }).catch(() => undefined);
    clearToken();
    setTokenState(null);
  }

  return {
    token,
    isAuthenticated: Boolean(token) || demoMode,
    initialized,
    demoMode,
    loading,
    backendError,
    login,
    initialize,
    logout,
  };
}
