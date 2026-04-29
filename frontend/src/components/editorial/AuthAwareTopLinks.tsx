import { Link } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

/** Top-nav-länkar som anpassar sig efter inloggningsstatus.
 *  Utloggad: Logga in + Skapa konto.
 *  Inloggad: Dashboard + Logga ut.
 *
 *  Designad för att användas både i `EditorialAuthShell` (mörkt skal,
 *  klassen "ed-top-link") och `EditorialLightShell` (ljust skal,
 *  klassen "edl-top-link"). Skicka in rätt prefix via `variant`. */
export function AuthAwareTopLinks({
  variant = "dark",
}: {
  variant?: "dark" | "light";
}) {
  const { isAuthenticated, logout } = useAuth();
  const cls = variant === "light" ? "edl-top-link" : "ed-top-link";
  const primary = variant === "light"
    ? "edl-top-link is-primary"
    : "ed-top-link is-primary";

  if (isAuthenticated) {
    return (
      <>
        <Link to="/dashboard" className={cls}>
          Dashboard
        </Link>
        <a
          href="/"
          className={primary}
          onClick={(e) => {
            e.preventDefault();
            logout?.();
            window.location.href = "/";
          }}
        >
          Logga ut
        </a>
      </>
    );
  }

  return (
    <>
      <Link to="/login" className={cls}>
        Logga in
      </Link>
      <Link to="/signup/teacher" className={primary}>
        Skapa konto
      </Link>
    </>
  );
}
