/**
 * Modul-detalj v2 · /v2/moduler/:moduleId
 *
 * Bug #12 · Wrappar v1 ModuleView (full step-renderare med heartbeat,
 * AI, celebration) inom v2-shell (V2Banner topbar, dark surface,
 * tillbaka-länk till v2-modullistan).
 *
 * Inner-komponenten ModuleViewInner exporteras från v1-filen och
 * återanvänder all befintlig logik utan duplicering.
 */
import { Link } from "react-router-dom";
import { V2Banner } from "./V2Banner";
import { ModuleViewInner } from "../pages/ModuleView";


export function ModuleViewV2() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #0a0e1a 0%, #0f1525 100%)",
      }}
    >
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "20px 28px 4px" }}>
        <Link
          to="/v2/moduler"
          style={{
            color: "rgba(255,255,255,0.6)",
            textDecoration: "none",
            fontSize: "0.9rem",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontFamily: "JetBrains Mono, monospace",
            letterSpacing: 1.1,
            textTransform: "uppercase",
          }}
        >
          ← Mina moduler
        </Link>
      </div>

      {/*
       * v1 step-renderare har egen ljus bakgrund (bg-slate-50). Vi
       * wrappar den i en mörk frame så v2-topbar smälter in. Inom
       * step-vyn bibehålls v1-färger så pedagogisk kod-renderaren,
       * AI-knappen, celebrate-overlay etc fortsätter funka identiskt.
       */}
      <div
        style={{
          background: "linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%)",
          margin: "12px 28px 28px",
          borderRadius: 16,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.08)",
          boxShadow: "0 12px 40px rgba(0, 0, 0, 0.4)",
        }}
      >
        <ModuleViewInner />
      </div>
    </div>
  );
}
