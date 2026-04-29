import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";

/** Gemensamt yttre skal för alla auth-sidor (login, signup, glömt
 * lösenord, verify-email, reset-password). Ger paper-bg, centrerat
 * 480px-kort med 1.5px svart border + tillbaka-länk till /.
 *
 * Tillbaka-länken är ett vanligt `<a href>` (inte react-router-Link)
 * så ett klick tvingar en full page-navigation — backend serverar då
 * demo-landing/index.html istället för att React Router renderar den
 * gamla SPA-Landingen inuti SPA:n. */
export function AuthShell({
  title,
  eyebrow,
  intro,
  children,
  back = "/",
  backLabel = "Tillbaka",
}: {
  title: string;
  eyebrow?: string;
  intro?: ReactNode;
  children: ReactNode;
  back?: string;
  backLabel?: string;
}) {
  return (
    <div className="min-h-screen bg-paper text-ink grid place-items-center p-6">
      <div className="w-full max-w-md">
        <a
          href={back}
          className="text-sm text-[#666] hover:text-ink flex items-center gap-1 mb-5 nav-link inline-flex"
        >
          <ArrowLeft className="w-4 h-4" /> {backLabel}
        </a>
        <div className="bg-white border-[1.5px] border-ink p-8">
          {eyebrow && <div className="eyebrow mb-3">{eyebrow}</div>}
          <h1 className="serif text-3xl leading-[1.05] mb-3">{title}</h1>
          {intro && <p className="text-sm text-[#555] leading-relaxed mb-5">{intro}</p>}
          {children}
        </div>
      </div>
    </div>
  );
}

/** Standard-input för auth-formulär — paper-stil, ink-border, ingen
 * extra ring. Använder native focus-visible-stilen (svart ring). */
export function PaperInput(
  props: React.InputHTMLAttributes<HTMLInputElement>,
) {
  return (
    <input
      {...props}
      className={`w-full px-3 py-2.5 border-[1.5px] border-rule bg-white text-ink placeholder:text-[#999] focus:border-ink outline-none transition-colors ${props.className ?? ""}`}
    />
  );
}
