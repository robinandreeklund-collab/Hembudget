import { useEffect, useState } from "react";
import { ArrowRight, ExternalLink } from "lucide-react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";

type Profile = {
  student_id: number;
  profession: string;
  employer: string;
  gross_salary_monthly: number;
  net_salary_monthly: number;
  tax_rate_effective: number;
  personality: string;
  age: number;
  city: string;
  family_status: string;
  housing_type: string;
  housing_monthly: number;
  has_mortgage: boolean;
  has_car_loan: boolean;
  has_student_loan: boolean;
  has_credit_card: boolean;
  children_ages: number[];
  partner_age: number | null;
  backstory: string | null;
};

type TaxBreakdown = {
  gross_monthly: number;
  net_monthly: number;
  total_tax: number;
  effective_rate: number;
  explanation: string;
};

type SuggestedBudget = {
  mat: number;
  individuellt_ovrigt: number;
  boende: number;
  el: number;
  bredband_mobil: number;
  medietjanster: number;
  forbrukningsvaror: number;
  hemutrustning: number;
  vatten_avlopp: number;
  hemforsakring: number;
  transport: number;
  lan_amortering_ranta: number;
  sparande: number;
  nojen_marginal: number;
  total: number;
  persons_in_household: number;
  source_url: string;
  source_title: string;
  note: string;
};

const BUDGET_FIELDS: { key: keyof SuggestedBudget; label: string }[] = [
  { key: "mat", label: "Mat (alla i hushållet)" },
  { key: "individuellt_ovrigt", label: "Kläder, hygien, fritid" },
  { key: "boende", label: "Hyra / avgift" },
  { key: "el", label: "El" },
  { key: "bredband_mobil", label: "Bredband + mobil" },
  { key: "medietjanster", label: "Streaming / medier" },
  { key: "forbrukningsvaror", label: "Förbrukningsvaror" },
  { key: "hemutrustning", label: "Hemutrustning" },
  { key: "vatten_avlopp", label: "Vatten & avlopp" },
  { key: "hemforsakring", label: "Hemförsäkring" },
  { key: "transport", label: "Transport (SL/bensin)" },
  { key: "lan_amortering_ranta", label: "Lån (ränta + amortering)" },
  { key: "sparande", label: "Sparande" },
  { key: "nojen_marginal", label: "Nöjen / buffert" },
];

const formatKr = (n: number): string =>
  n.toLocaleString("sv-SE") + " kr";

export default function Onboarding() {
  const { logout } = useAuth();
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [tax, setTax] = useState<TaxBreakdown | null>(null);
  const [budget, setBudget] = useState<SuggestedBudget | null>(null);
  const [edited, setEdited] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Onboarding renderas av App.tsx oavsett URL för elever som inte
  // är klara med onboarding. Om eleven försökte gå till en specifik
  // sida (t.ex. /modules/1 från sin kursplan) sparar vi destinationen
  // i sessionStorage så vi kan ta dem dit efter att de är klara.
  useEffect(() => {
    const path = window.location.pathname;
    if (path && path !== "/" && path !== "/onboarding") {
      sessionStorage.setItem("hembudget_onboarding_redirect", path);
    }
  }, []);
  const intendedDestination =
    sessionStorage.getItem("hembudget_onboarding_redirect");

  useEffect(() => {
    (async () => {
      try {
        const p = await api<Profile>("/student/profile");
        setProfile(p);
        const t = await api<TaxBreakdown>(
          `/school/tax/breakdown?gross_monthly=${p.gross_salary_monthly}`,
        );
        setTax(t);
        const b = await api<SuggestedBudget>("/student/budget/suggested");
        setBudget(b);
        const initial: Record<string, number> = {};
        BUDGET_FIELDS.forEach((f) => {
          initial[f.key] = b[f.key] as number;
        });
        setEdited(initial);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  async function finish() {
    setBusy(true);
    try {
      // Skicka budget-värdena till backend som mappar dem till
      // riktiga Budget-rader i elevens scope-DB:s aktuella månad.
      // Server skapar saknade kategorier och svarar med antal rader sparade.
      const now = new Date();
      const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
      await api("/student/onboarding/complete", {
        method: "POST",
        body: JSON.stringify({
          year_month: ym,
          values: edited,
        }),
      });
      // Om eleven blev hänvisad hit från en specifik sida — gå dit istället.
      const dest = sessionStorage.getItem("hembudget_onboarding_redirect");
      sessionStorage.removeItem("hembudget_onboarding_redirect");
      window.location.href = dest || "/dashboard";
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (err) {
    return (
      <div className="min-h-screen grid place-items-center p-6 bg-paper">
        <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1 max-w-md">
          {err}
        </div>
      </div>
    );
  }
  if (!profile || !tax || !budget) {
    return (
      <div className="grid place-items-center min-h-screen bg-paper">
        <div className="serif-italic text-[#888]">Laddar…</div>
      </div>
    );
  }

  const totalEdited = Object.values(edited).reduce((a, b) => a + b, 0);
  const overUnder = profile.net_salary_monthly - totalEdited;

  return (
    <div className="min-h-screen bg-paper text-ink py-12 px-4">
      <div className="max-w-3xl mx-auto bg-white border-[1.5px] border-ink p-8 md:p-10 space-y-7">
        <div>
          <div className="eyebrow mb-2">Onboarding · Ekonomilabbet</div>
          <h1 className="serif text-3xl md:text-4xl leading-[1.05]">
            Välkommen — låt oss sätta upp din vardag.
          </h1>
          {intendedDestination && intendedDestination !== "/dashboard" && (
            <p className="mt-3 text-sm text-[#666] serif-italic">
              Du försökte gå till{" "}
              <span className="kbd">{intendedDestination}</span> — vi tar
              dig dit så fort du är klar med dessa tre steg.
            </p>
          )}
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-3">
          {[
            { i: 0, label: "Profil" },
            { i: 1, label: "Skatt" },
            { i: 2, label: "Budget" },
          ].map((s) => (
            <div key={s.i} className="flex-1 flex items-center gap-2">
              <span
                className={`feature-chip ${
                  s.i < step ? "special" : s.i === step ? "" : ""
                }`}
                style={{
                  width: 28, height: 28, fontSize: 12,
                  background: s.i <= step ? "#111217" : "#fff",
                  color: s.i <= step ? "#fff" : "#999",
                  borderColor: s.i <= step ? "#111217" : "#e7e3d7",
                }}
              >
                {s.i + 1}
              </span>
              <span
                className={`text-xs uppercase tracking-eyebrow font-semibold ${
                  s.i === step ? "text-ink" : "text-[#999]"
                }`}
              >
                {s.label}
              </span>
            </div>
          ))}
        </div>

        {/* Steg 1: Välkommen + backstory */}
        {step === 0 && (
          <div className="space-y-5">
            <p className="lead">
              Hej! Du är nu inloggad i din egen ekonomi-simulator. Här lär du
              dig att planera, spara och förstå vart pengarna tar vägen.
            </p>
            <div className="border-l-[3px] border-ink pl-5 py-1">
              <div className="eyebrow mb-1">Din situation</div>
              <p className="serif-italic text-lg leading-snug">
                {profile.backstory}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Stat label="Yrke" value={profile.profession} />
              <Stat label="Arbetsgivare" value={profile.employer} />
              <Stat label="Bruttolön" value={formatKr(profile.gross_salary_monthly)} />
              <Stat label="Nettolön" value={formatKr(profile.net_salary_monthly)} />
              <Stat label="Boende" value={`${profile.housing_type} – ${formatKr(profile.housing_monthly)}/mån`} />
              <Stat label="Stad" value={profile.city} />
              {profile.children_ages.length > 0 && (
                <Stat
                  label="Barn"
                  value={`${profile.children_ages.length} st (${profile.children_ages.join(", ")} år)`}
                />
              )}
            </div>
            <div className="flex justify-end pt-3">
              <button
                onClick={() => setStep(1)}
                className="btn-dark rounded-md px-5 py-2.5 flex items-center gap-2"
              >
                Förstått, gå vidare <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Steg 2: Skatt */}
        {step === 1 && (
          <div className="space-y-5">
            <div>
              <div className="eyebrow mb-1">Steg 2 av 3</div>
              <h2 className="serif text-2xl leading-tight">Vad händer med din lön?</h2>
            </div>
            <p className="body-prose text-sm">
              Den lönesumma du ser på papperet är inte den summan som hamnar
              på ditt konto. Skatten dras direkt av arbetsgivaren och skickas
              till Skatteverket. Så här ser det ut för dig:
            </p>
            <div className="bg-paper border-[1.5px] border-rule p-5 space-y-2">
              <Row label="Bruttolön (innan skatt)" value={formatKr(tax.gross_monthly)} />
              <Row
                label="Skatt totalt"
                value={`-${formatKr(tax.total_tax)} (${(tax.effective_rate * 100).toFixed(1)}%)`}
                negative
              />
              <div className="border-t border-ink pt-2 mt-1">
                <Row
                  label="Nettolön (det du faktiskt får)"
                  value={formatKr(tax.net_monthly)}
                  bold
                />
              </div>
            </div>
            <details className="border-l-[3px] border-ink pl-5 py-2">
              <summary className="cursor-pointer eyebrow">
                Förklara mer om hur skatten räknas
              </summary>
              <p className="mt-2 body-prose text-sm">{tax.explanation}</p>
            </details>
            <div className="flex justify-between pt-3">
              <button
                onClick={() => setStep(0)}
                className="text-sm nav-link inline-flex items-center"
              >
                ← Tillbaka
              </button>
              <button
                onClick={() => setStep(2)}
                className="btn-dark rounded-md px-5 py-2.5 flex items-center gap-2"
              >
                Sätt en budget <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Steg 3: Budget */}
        {step === 2 && (
          <div className="space-y-5">
            <div>
              <div className="eyebrow mb-1">Steg 3 av 3</div>
              <h2 className="serif text-2xl leading-tight">Sätt din månadsbudget</h2>
            </div>
            <p className="body-prose text-sm">
              Värdena nedan är ett FÖRSLAG baserat på{" "}
              <a
                href={budget.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="nav-link inline-flex items-center gap-0.5"
              >
                {budget.source_title}
                <ExternalLink className="w-3 h-3" />
              </a>{" "}
              och din profil ({budget.persons_in_household} personer i
              hushållet). Justera så det stämmer med hur du tror att DU
              kommer leva — vi följer sedan upp mot dina riktiga köp.
            </p>
            {budget.note && (
              <div className="border-l-[3px] border-ink pl-5 py-2">
                <div className="eyebrow mb-1">Notera</div>
                <p className="serif-italic text-sm">{budget.note}</p>
              </div>
            )}
            <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
              {BUDGET_FIELDS.map((f) => (
                <div key={f.key} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 py-1 border-b border-rule last:border-0">
                  <label className="text-sm">{f.label}</label>
                  <span className="text-xs text-[#999]">
                    förslag: {formatKr(budget[f.key] as number)}
                  </span>
                  <input
                    type="number"
                    value={edited[f.key] ?? 0}
                    onChange={(e) =>
                      setEdited({
                        ...edited,
                        [f.key]: parseInt(e.target.value || "0", 10),
                      })
                    }
                    className="w-28 text-right border-[1.5px] border-rule focus:border-ink outline-none px-2 py-1 font-mono text-sm"
                  />
                </div>
              ))}
            </div>
            <div className="border-t border-ink pt-4 space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span>Din nettolön</span>
                <span className="mock-num">{formatKr(profile.net_salary_monthly)}</span>
              </div>
              <div className="flex justify-between">
                <span>Din budget totalt</span>
                <span className="mock-num">{formatKr(totalEdited)}</span>
              </div>
              <div
                className={`flex justify-between text-base font-semibold pt-1 border-t border-rule ${
                  overUnder >= 0 ? "text-emerald-700" : "text-rose-700"
                }`}
              >
                <span>{overUnder >= 0 ? "Kvar att fördela" : "Överbudgeterat"}</span>
                <span className="mock-num">
                  {overUnder >= 0 ? "+" : ""}
                  {formatKr(overUnder)}
                </span>
              </div>
            </div>
            <div className="flex justify-between pt-3 flex-wrap gap-2">
              <button
                onClick={() => setStep(1)}
                className="text-sm nav-link inline-flex items-center"
              >
                ← Tillbaka
              </button>
              <div className="flex gap-2 items-center">
                <button
                  onClick={logout}
                  className="text-sm text-[#888] hover:text-ink px-2 py-2"
                >
                  Avbryt
                </button>
                <button
                  onClick={finish}
                  disabled={busy}
                  className="btn-dark rounded-md px-5 py-2.5 flex items-center gap-2 disabled:opacity-50"
                >
                  {busy ? "Sparar…" : "Klar! Starta Ekonomilabbet"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-[1.5px] border-rule bg-white p-3">
      <div className="eyebrow mb-1">{label}</div>
      <div className="font-medium text-ink">{value}</div>
    </div>
  );
}

function Row({
  label,
  value,
  bold,
  negative,
}: {
  label: string;
  value: string;
  bold?: boolean;
  negative?: boolean;
}) {
  return (
    <div className="flex justify-between items-baseline text-sm">
      <span className={bold ? "font-semibold" : "text-[#444]"}>{label}</span>
      <span
        className={`mock-num ${bold ? "text-base" : ""} ${
          negative ? "text-rose-700" : "text-ink"
        }`}
      >
        {value}
      </span>
    </div>
  );
}
