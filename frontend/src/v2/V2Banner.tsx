/**
 * V2-banner · synlig på alla v2-sidor.
 *
 * Migrations-indikator + dev-växlare för att enkelt hoppa mellan
 * v1 och v2 under utveckling. Knappen "Tvinga v1" sätter en
 * localStorage-flagga som inaktiverar alla v2-auto-redirects, så
 * läraren kan testa v1-flödet (skapa elever, toggle v2 etc.).
 */
import { Link, useNavigate } from "react-router-dom";

const FORCE_V1_KEY = "v2_force_v1";

export function V2Banner({ status }: { status: { role: string; is_super_admin: boolean } }) {
  const navigate = useNavigate();
  const isTeacher = status.role === "teacher";
  const v1Home = isTeacher ? "/teacher" : "/dashboard";

  function forceV1() {
    window.localStorage.setItem(FORCE_V1_KEY, "1");
    navigate(v1Home);
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        background: "linear-gradient(90deg, rgba(220,76,43,0.12), rgba(251,191,36,0.10))",
        borderBottom: "1px solid rgba(251,191,36,0.35)",
        padding: "8px 18px",
        fontFamily: "JetBrains Mono, ui-monospace, monospace",
        fontSize: 11,
        letterSpacing: 1.2,
        textTransform: "uppercase",
        color: "#0f172a",
        display: "flex",
        alignItems: "center",
        gap: 16,
        flexWrap: "wrap",
      }}
    >
      <span style={{ fontWeight: 700 }}>● V2 · Ny dashboard (under utveckling)</span>
      {status.is_super_admin && (
        <span style={{ background: "#0f172a", color: "#fbbf24", padding: "2px 8px", borderRadius: 100, fontWeight: 700 }}>
          SUPER-ADMIN
        </span>
      )}
      <span style={{ color: "#64748b" }}>· {status.role}</span>
      <span style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={forceV1}
          style={{
            background: "#dc4c2b",
            color: "#fff",
            border: 0,
            padding: "5px 10px",
            borderRadius: 4,
            fontFamily: "inherit",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: 1.2,
            textTransform: "uppercase",
            cursor: "pointer",
          }}
        >
          ← Tvinga v1 (dev)
        </button>
        <Link
          to={v1Home}
          style={{ color: "#dc4c2b", textDecoration: "none", fontWeight: 700 }}
        >
          {isTeacher ? "Lärar-dashboard (v1)" : "Gamla gränssnittet (v1)"}
        </Link>
        <Link to="/v2/hub" style={{ color: "#0f172a", textDecoration: "none", fontWeight: 700 }}>
          v2/hub
        </Link>
        <Link to="/v2/onboarding" style={{ color: "#0f172a", textDecoration: "none" }}>
          v2/onboarding
        </Link>
      </span>
    </div>
  );
}
