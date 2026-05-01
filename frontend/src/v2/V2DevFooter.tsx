/**
 * V2 Dev Footer · minimal status-rad i botten av sidan.
 *
 * Speglar prototypens design (bara "Ekonomilabbet · v2 · 2026")
 * + diskret länk för dev-läge så lärare kan tvinga v1 om de
 * vill. Visas på alla v2-sidor.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "./topbar.css";

const FORCE_V1_KEY = "v2_force_v1";

type Props = {
  role?: string;
  isSuperAdmin?: boolean;
};

export function V2DevFooter({ role = "student", isSuperAdmin = false }: Props) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const isTeacher = role === "teacher";
  const v1Home = isTeacher ? "/teacher" : "/dashboard";

  function forceV1() {
    window.localStorage.setItem(FORCE_V1_KEY, "1");
    navigate(v1Home);
  }

  return (
    <footer className="v2-dev-footer">
      <span className="v2-dev-footer-brand">
        Ekonomilabbet <span>v2 · {new Date().getFullYear()}</span>
      </span>
      <span className="v2-dev-footer-meta">
        {isTeacher ? "Lärar-läge" : role === "demo" ? "Demo" : "Elev-läge"}
        {isSuperAdmin ? " · Super-admin" : ""}
      </span>
      <button
        type="button"
        className="v2-dev-footer-toggle"
        onClick={() => setOpen((s) => !s)}
        aria-expanded={open}
      >
        {open ? "× Dev" : "Dev ▾"}
      </button>
      {open && (
        <div className="v2-dev-footer-pop" role="menu">
          <div className="v2-dev-footer-pop-eye">Utvecklings-läge</div>
          <Link
            to={v1Home}
            className="v2-dev-footer-pop-item"
            onClick={() => setOpen(false)}
          >
            Öppna v1 (gamla gränssnittet)
          </Link>
          <button
            type="button"
            className="v2-dev-footer-pop-item is-danger"
            onClick={forceV1}
          >
            ← Tvinga v1 (sparas i localStorage)
          </button>
          <div className="v2-dev-footer-pop-meta">
            Roll: <strong>{role}</strong>
            {isSuperAdmin ? " · super-admin" : ""}
          </div>
        </div>
      )}
    </footer>
  );
}
