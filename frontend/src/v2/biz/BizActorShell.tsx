/**
 * BizActorShell · gemensam layout för alla biz-aktör-vyer.
 *
 * Matchar prototypen vol-7 p-biz-* exakt:
 *   - actor-back · "Tillbaka till biz-hubben"
 *   - actor-head (grid 1fr auto): vänster = pill + actor-name + actor-sub,
 *     höger = actor-meta (mono-text med bold-värden)
 *   - children fyller resten av sidan
 *
 * Sätter automatiskt body[data-mode="business"] för indigo-theming.
 */
import { useEffect, type ReactNode } from "react";
import { Link } from "react-router-dom";
import "./biz.css";


export function BizActorShell({
  pillLabel,
  title,
  subtitle,
  meta,
  backLabel = "Tillbaka till biz-hubben",
  backTo = "/v2/foretag",
  children,
}: {
  pillLabel: string;
  title: ReactNode;
  subtitle?: ReactNode;
  meta?: ReactNode;
  backLabel?: string;
  backTo?: string;
  children: ReactNode;
}) {
  // Sätt mode body-attribut för indigo-theming via biz-CSS.
  useEffect(() => {
    const prev = document.body.getAttribute("data-mode");
    document.body.setAttribute("data-mode", "business");
    return () => {
      document.body.setAttribute("data-mode", prev || "private");
    };
  }, []);

  return (
    <div className="biz-shell">
      <Link to={backTo} className="actor-back">
        {backLabel}
      </Link>

      <header className="actor-head">
        <div>
          <span className="biz-pill">{pillLabel}</span>
          <h1 className="actor-name" style={{ marginTop: 14 }}>
            {title}
          </h1>
          {subtitle && <p className="actor-sub">{subtitle}</p>}
        </div>
        {meta && <div className="actor-meta">{meta}</div>}
      </header>

      {children}
    </div>
  );
}


/** Sektion med eye-rubrik (matchar .section-eye från prototyp). */
export function BizSection({
  eye,
  eyeColor,
  children,
  marginTop,
}: {
  eye: string;
  eyeColor?: string;
  children: ReactNode;
  marginTop?: number | string;
}) {
  return (
    <div style={marginTop !== undefined ? { marginTop } : undefined}>
      <div
        className="section-eye"
        style={eyeColor ? { color: eyeColor } : undefined}
      >
        {eye}
      </div>
      {children}
    </div>
  );
}
