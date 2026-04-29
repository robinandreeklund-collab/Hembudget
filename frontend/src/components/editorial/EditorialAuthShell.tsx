import type { ReactNode } from "react";
import "./editorial.css";

/** Editorial yttre skal för auth-sidor — speglar /demo-landing.
 *  Mörk navy bg med ambient gradient-mesh, fast top-nav (Hem +
 *  sekundär CTA), brand-block topp-mitten, eyebrow + headline +
 *  intro stack, content-card eller choice-grid, footer-credits.
 *
 *  Sidor passar in egen content via children — typografi (h1, p,
 *  cards, formulär) löses lokalt via .ed-* klasser eftersom de
 *  redan är scopade i editorial.css.
 *
 *  Hem-länken är ett vanligt `<a href>` (inte react-router-Link) så
 *  klicket gör en full page-navigation — backend serverar då
 *  demo-landing/index.html. Annars hade React Router renderat sin
 *  egna `/`-route (gamla Landing) inuti SPA:n.
 */
export function EditorialAuthShell({
  topNavRight,
  homeLabel = "Hem",
  homeHref = "/",
  children,
  credits = "Vol. 01 · Ekonomilabbet 2026",
}: {
  topNavRight?: ReactNode;
  homeLabel?: string;
  homeHref?: string;
  children: ReactNode;
  credits?: string;
}) {
  return (
    <div className="ed-root">
      <a href={homeHref} className="ed-home-link" aria-label="Tillbaka till startsidan">
        <span className="ed-home-arrow" aria-hidden="true">←</span>
        {homeLabel}
      </a>

      {topNavRight && <nav className="ed-top-nav" aria-label="Konto">{topNavRight}</nav>}

      <header className="ed-brand" aria-hidden="true">
        <div className="ed-brand-name">Ekonomilabbet</div>
        <div className="ed-brand-tagline">Konsekvensdriven ekonomi och lärande</div>
      </header>

      <div className="ed-shell">
        <div className="ed-content">{children}</div>

        <div className="ed-credits">
          <span className="ed-credits-vol">{credits}</span>
          <span>3 karaktärer · 12 kompetenser · 4 djupdyk</span>
        </div>
      </div>
    </div>
  );
}
