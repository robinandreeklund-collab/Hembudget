import type { ReactNode } from "react";
import "./editorial-light.css";

/** Light editorial-skal för långform-content (Docs, Villkor, FAQ).
 *  Cream-bg, serif-rubriker, top-nav (Hem + sekundär CTA), sticky
 *  brand topp-mitten, eyebrow + headline + intro stack.
 *
 *  Page-content går via children — använd .edl-section, .edl-prose,
 *  .edl-h2, .edl-h3, .edl-faq-item, .edl-callout etc. för typografi.
 *  Hem-länken är `<a href>` (inte react-router-Link) så ett klick
 *  triggar en full page-navigation till backend → demo-landing. */
export function EditorialLightShell({
  topNavRight,
  homeLabel = "Hem",
  homeHref = "/",
  eyebrow,
  title,
  intro,
  children,
  credits = "Vol. 01 · Ekonomilabbet 2026",
  withAsideSidebar = false,
  aside,
}: {
  topNavRight?: ReactNode;
  homeLabel?: string;
  homeHref?: string;
  eyebrow?: ReactNode;
  title: ReactNode;
  intro?: ReactNode;
  children: ReactNode;
  credits?: string;
  withAsideSidebar?: boolean;
  aside?: ReactNode;
}) {
  return (
    <div className="edl-root">
      <a href={homeHref} className="edl-home-link" aria-label="Tillbaka till startsidan">
        <span className="edl-home-arrow" aria-hidden="true">←</span>
        {homeLabel}
      </a>

      {topNavRight && <nav className="edl-top-nav" aria-label="Konto">{topNavRight}</nav>}

      <header className="edl-brand" aria-hidden="true">
        <div className="edl-brand-name">Ekonomilabbet</div>
        <div className="edl-brand-tagline">Konsekvensdriven ekonomi och lärande</div>
      </header>

      <div className="edl-shell">
        <div className="edl-head">
          {eyebrow && <div className="edl-eyebrow">{eyebrow}</div>}
          <h1 className="edl-headline">{title}</h1>
          {intro && <p className="edl-lead">{intro}</p>}
        </div>

        {withAsideSidebar ? (
          <div className="edl-with-aside">
            <aside className="edl-aside">{aside}</aside>
            <main>{children}</main>
          </div>
        ) : (
          <main>{children}</main>
        )}

        <div className="edl-foot">
          <span className="edl-foot-vol">{credits}</span>
          <span>3 karaktärer · 12 kompetenser · 4 djupdyk</span>
        </div>
      </div>
    </div>
  );
}
