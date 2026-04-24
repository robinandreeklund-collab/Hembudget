import { useEffect, useState } from "react";
import {
  api,
  clearRole,
  clearToken,
  getAsStudent,
  getRole,
  getToken,
  setAsStudent,
  setRole,
  setToken,
} from "@/api/client";

type SchoolStatus = {
  school_mode: boolean;
  teacher_count?: number;
  bootstrap_ready?: boolean;
  bootstrap_requires_secret?: boolean;
  turnstile_site_key?: string;
};

export function useAuth() {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [role, setRoleState] = useState<"teacher" | "student" | null>(getRole());
  const [asStudent, setAsStudentState] = useState<number | null>(getAsStudent());
  const [initialized, setInitialized] = useState<boolean | null>(null);
  const [demoMode, setDemoMode] = useState(false);
  const [schoolMode, setSchoolMode] = useState(false);
  const [schoolStatus, setSchoolStatus] = useState<SchoolStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [studentMeta, setStudentMeta] = useState<{
    onboarding_completed: boolean;
    family_id: number | null;
  } | null>(null);

  // Hämta /student/me när token+role finns för att veta onboarding-status
  useEffect(() => {
    if (token && role === "student") {
      api<{ onboarding_completed: boolean; family_id: number | null }>(
        "/student/me",
      )
        .then((m) =>
          setStudentMeta({
            onboarding_completed: m.onboarding_completed,
            family_id: m.family_id,
          }),
        )
        .catch(() => undefined);
    } else {
      setStudentMeta(null);
    }
  }, [token, role]);

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
        try {
          const ss = await api<SchoolStatus>("/school/status");
          setSchoolStatus(ss);
          setSchoolMode(ss.school_mode);
        } catch {
          /* endpoint kan saknas i äldre backend */
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
    // Master-login är desktop-läge — ingen "teacher"/"student"-roll.
    // Rensa ev. kvarliggande role från en tidigare school-session så
    // App.tsx inte tror vi är lärare och routear till /teacher.
    clearRole();
    setRoleState(null);
    setAsStudent(null);
    setAsStudentState(null);
    setToken(res.token);
    setTokenState(res.token);
    return res.token;
  }

  async function initialize(password: string) {
    const res = await api<{ token: string }>("/init", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
    clearRole();
    setRoleState(null);
    setAsStudent(null);
    setAsStudentState(null);
    setToken(res.token);
    setTokenState(res.token);
    setInitialized(true);
    return res.token;
  }

  async function teacherLogin(
    email: string, password: string, turnstileToken?: string,
  ) {
    const res = await api<{ token: string }>("/teacher/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
      turnstileToken,
    });
    setToken(res.token);
    setTokenState(res.token);
    setRole("teacher");
    setRoleState("teacher");
    return res.token;
  }

  async function teacherBootstrap(
    bootstrap_secret: string,
    email: string,
    password: string,
    name: string,
    turnstileToken?: string,
  ) {
    const res = await api<{ token: string }>("/teacher/bootstrap", {
      method: "POST",
      body: JSON.stringify({ bootstrap_secret, email, password, name }),
      turnstileToken,
    });
    setToken(res.token);
    setTokenState(res.token);
    setRole("teacher");
    setRoleState("teacher");
    return res.token;
  }

  async function demoTeacherLogin() {
    const res = await api<{ token: string }>("/demo/teacher", {
      method: "POST",
    });
    setToken(res.token);
    setTokenState(res.token);
    setRole("teacher");
    setRoleState("teacher");
    setAsStudent(null);
    setAsStudentState(null);
    return res.token;
  }

  async function demoStudentLogin(code: string = "DEMO01") {
    const res = await api<{ token: string }>(
      `/demo/student?code=${encodeURIComponent(code)}`,
      { method: "POST" },
    );
    setToken(res.token);
    setTokenState(res.token);
    setRole("student");
    setRoleState("student");
    setAsStudent(null);
    setAsStudentState(null);
    return res.token;
  }

  async function studentLogin(login_code: string, turnstileToken?: string) {
    const res = await api<{ token: string }>("/student/login", {
      method: "POST",
      body: JSON.stringify({ login_code }),
      turnstileToken,
    });
    setToken(res.token);
    setTokenState(res.token);
    setRole("student");
    setRoleState("student");
    setAsStudent(null);
    setAsStudentState(null);
    return res.token;
  }

  function impersonate(studentId: number | null) {
    setAsStudent(studentId);
    setAsStudentState(studentId);
  }

  function logout() {
    api("/logout", { method: "POST" }).catch(() => undefined);
    clearToken();
    clearRole();
    setAsStudent(null);
    setTokenState(null);
    setRoleState(null);
    setAsStudentState(null);
  }

  function refreshStudentMeta() {
    if (token && role === "student") {
      api<{ onboarding_completed: boolean; family_id: number | null }>(
        "/student/me",
      )
        .then((m) =>
          setStudentMeta({
            onboarding_completed: m.onboarding_completed,
            family_id: m.family_id,
          }),
        )
        .catch(() => undefined);
    }
  }

  return {
    token,
    role,
    asStudent,
    isAuthenticated: Boolean(token) || demoMode,
    initialized,
    demoMode,
    schoolMode,
    schoolStatus,
    studentMeta,
    refreshStudentMeta,
    loading,
    backendError,
    login,
    initialize,
    teacherLogin,
    teacherBootstrap,
    studentLogin,
    demoTeacherLogin,
    demoStudentLogin,
    impersonate,
    logout,
  };
}
