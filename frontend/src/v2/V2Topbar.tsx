/**
 * V2 Topbar · matchar prototypens .topbar (elev.html / larare.html).
 *
 * Element:
 * - Brand "Ekonomilabbet" + meta
 * - Roll-pill (Elev / Lärare)
 * - Crumbs (route → människo-läsbar sökväg)
 * - Spacer
 * - Guide-knapp (öppnar GuideDropdown)
 * - Notif-bell (öppnar NotifDrawer · Fas 2AB)
 * - Användar-avatar (initialer)
 *
 * Footer-status med v1-länk + roll renderas separat via V2DevFooter.
 */
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { GuideDropdown } from "./guides/GuideDropdown";
import { NotifBell } from "./NotifBell";
import { EchoButton } from "./EchoButton";
import { CompanyModeToggle } from "./CompanyMode";
import "./topbar.css";

type Status = { role: string; is_super_admin: boolean };

const ROUTE_TO_CRUMBS: Array<[RegExp, string[]]> = [
  // Elev-vyer
  [/^\/v2\/hub$/, ["Hubben"]],
  [/^\/v2\/banken$/, ["Hubben", "Banken"]],
  [/^\/v2\/arbetsgivaren$/, ["Hubben", "Arbetsgivaren"]],
  [/^\/v2\/skatten$/, ["Hubben", "Skatteverket"]],
  [/^\/v2\/lan$/, ["Hubben", "Lånegivaren"]],
  [/^\/v2\/avanza$/, ["Hubben", "Avanza"]],
  [/^\/v2\/forsakringar$/, ["Hubben", "Försäkringar"]],
  [/^\/v2\/forbrukning$/, ["Hubben", "Förbrukning"]],
  [/^\/v2\/hyresvarden$/, ["Hubben", "Boendemarknaden"]],
  [/^\/v2\/boendemarknad$/, ["Hubben", "Boendemarknaden"]],
  [/^\/v2\/arbetsformedlingen$/, ["Hubben", "Arbetsförmedlingen"]],
  [/^\/v2\/pension$/, ["Hubben", "Pension"]],
  [/^\/v2\/postladan/, ["Hubben", "Postlådan"]],
  [/^\/v2\/bokforing$/, ["Hubben", "Bokföring"]],
  [/^\/v2\/budget$/, ["Hubben", "Budget"]],
  [/^\/v2\/mal$/, ["Hubben", "Mål"]],
  [/^\/v2\/aktier$/, ["Hubben", "Aktier"]],
  [/^\/v2\/lanekalkylator$/, ["Hubben", "Lånekalkylator"]],
  [/^\/v2\/maria$/, ["Hubben", "Maria · lönesamtal"]],
  [/^\/v2\/bankid/, ["Hubben", "BankID"]],
  [/^\/v2\/uppdrag$/, ["Hubben", "Mina uppdrag"]],
  [/^\/v2\/portfolio$/, ["Hubben", "Portfolio"]],
  [/^\/v2\/kompetens\//, ["Hubben", "Portfolio", "Kompetens"]],
  [/^\/v2\/moduler$/, ["Hubben", "Mina moduler"]],
  [/^\/v2\/feedback$/, ["Hubben", "Lärar-feedback"]],
  [/^\/v2\/meddelanden$/, ["Hubben", "Meddelanden"]],
  [/^\/v2\/tx\//, ["Hubben", "Transaktion"]],
  // Lärar-vyer
  [/^\/teacher\/v2$/, ["Klassen 9C"]],
  [/^\/teacher\/v2\/elev\//, ["Klassen 9C", "Elev"]],
  [/^\/teacher\/v2\/historik\//, ["Klassen 9C", "Elev", "Aktivitets-historik"]],
  [/^\/teacher\/v2\/portfolio\//, ["Klassen 9C", "Elev", "Portfolio"]],
  [/^\/teacher\/v2\/kompetens\//, ["Klassen 9C", "Elev", "Kompetens"]],
  [/^\/teacher\/v2\/uppdrag\//, ["Klassen 9C", "Elev", "Uppdrag"]],
  [/^\/teacher\/v2\/feedback\//, ["Klassen 9C", "Elev", "Feedback"]],
  [/^\/teacher\/v2\/messages\//, ["Klassen 9C", "Elev", "Meddelanden"]],
  [/^\/teacher\/v2\/maria(\/|$)/, ["Klassen 9C", "Maria-lista"]],
  [/^\/teacher\/v2\/reflektioner$/, ["Klassen 9C", "Reflektioner"]],
  [/^\/teacher\/v2\/postlador$/, ["Klassen 9C", "Postlådor"]],
  [/^\/teacher\/v2\/pedagogik$/, ["Klassen 9C", "Pedagogik-paket"]],
  [/^\/teacher\/v2\/skapa$/, ["Klassen 9C", "Skapa elev"]],
  [/^\/teacher\/v2\/roster$/, ["Klassen 9C", "v2-roster"]],
];

function getCrumbs(path: string): string[] {
  for (const [pattern, crumbs] of ROUTE_TO_CRUMBS) {
    if (pattern.test(path)) return crumbs;
  }
  return ["v2"];
}

function getInitials(role: string): string {
  // Best-effort — vi har inte alltid namn här.
  if (role === "teacher") return "AL";
  if (role === "demo") return "D";
  return "S";
}

export function V2Topbar({ status }: { status: Status }) {
  const location = useLocation();
  const crumbs = getCrumbs(location.pathname);
  const isTeacher = status.role === "teacher";
  const [mobileOpen, setMobileOpen] = useState(false);

  // Stäng mobil-menyn vid route-byte
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <header
      className={`v2-topbar${mobileOpen ? " v2-topbar-mobile-open" : ""}`}
      data-guide="hub-banner"
    >
      <Link to={isTeacher ? "/teacher/v2" : "/v2/hub"} className="tb-brand">
        Ekonomilabbet
        <span className="tb-brand-meta">v2 · 2026</span>
      </Link>
      <span className={`tb-role ${isTeacher ? "is-teacher" : "is-student"}`}>
        {isTeacher ? "Lärare" : "Elev"}
      </span>
      {status.is_super_admin && (
        <span className="tb-role is-admin">Super-admin</span>
      )}

      <nav className="tb-crumbs" aria-label="Sökväg">
        {crumbs.map((c, i) => (
          <span key={i}>
            {i > 0 && <span className="sep"> / </span>}
            {i === crumbs.length - 1 ? (
              <strong>{c}</strong>
            ) : (
              <span>{c}</span>
            )}
          </span>
        ))}
      </nav>

      <div className="tb-spacer" />

      <button
        type="button"
        className="tb-mobile-toggle"
        onClick={() => setMobileOpen((s) => !s)}
        aria-label="Öppna meny"
        aria-expanded={mobileOpen}
      >
        {mobileOpen ? "✕" : "☰"}
      </button>

      <div className="tb-actions">
        {/* Bug #7 · Företag-toggle (flippar dashboard) — bara för elev */}
        {!isTeacher && <CompanyModeToggle />}
        <GuideDropdown />
        <NotifBell />
        {/* AI-chat alltid synlig i topbar — bug #4. AskAI:s FAB
            visas globalt om läraren har ai_enabled. Quota-badge
            visas i chat-headern. */}
        <EchoButton context="Global AI-chat — fråga om vad som helst" />
        <Link
          to={isTeacher ? "/teacher/v2" : "/v2/hub"}
          className="tb-user"
          aria-label="Hem"
        >
          {getInitials(status.role)}
        </Link>
        <button
          type="button"
          className="tb-logout"
          onClick={handleLogout}
          aria-label="Logga ut"
          title="Logga ut"
          style={{
            background: "transparent",
            border: "1px solid rgba(255,255,255,0.15)",
            color: "rgba(255,255,255,0.7)",
            padding: "6px 10px",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: "0.8rem",
            marginLeft: 8,
          }}
        >
          Logga ut
        </button>
      </div>
    </header>
  );
}

async function handleLogout() {
  try {
    // Använd raw fetch eftersom vi inte vill importera api-klient hit
    await fetch("/logout", {
      method: "POST",
      headers: { Authorization: `Bearer ${localStorage.getItem("hb_token") || ""}` },
    }).catch(() => undefined);
  } finally {
    localStorage.removeItem("hb_token");
    window.location.href = "/";
  }
}

// Bakåtkompatibilitet: V2Banner re-exportar V2Topbar så befintliga
// imports funkar. Footer-info läggs till i layouten via V2DevFooter
// (renderas i App.tsx).
export { V2Topbar as V2Banner };
