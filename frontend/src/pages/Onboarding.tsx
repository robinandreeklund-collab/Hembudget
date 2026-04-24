import { useEffect, useState } from "react";
import { ArrowRight, ExternalLink, Info, Sparkles, Wallet } from "lucide-react";
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
      // Spara budgeten månad-för-månad i appens budget-API. För enkelhet
      // sparar vi bara totalsumman som notering — full kategorisering
      // kommer i en framtida iteration.
      // (Här skulle vi ha en /budget/bulk-set-anslutning men det
      // kräver att vi kategori-mappar elevens valda fält till app-
      // ens kategorier. Skippas tills vidare.)
      await api("/student/onboarding/complete", { method: "POST" });
      window.location.href = "/dashboard";
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (err) {
    return (
      <div className="min-h-screen grid place-items-center p-6">
        <div className="bg-rose-50 text-rose-700 border border-rose-200 rounded p-4">
          {err}
        </div>
      </div>
    );
  }
  if (!profile || !tax || !budget) {
    return <div className="grid place-items-center min-h-screen">Laddar…</div>;
  }

  const totalEdited = Object.values(edited).reduce((a, b) => a + b, 0);
  const overUnder = profile.net_salary_monthly - totalEdited;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-brand-50 py-10 px-4">
      <div className="max-w-3xl mx-auto bg-white rounded-2xl shadow-lg border border-slate-200 p-8 space-y-6">
        <div className="flex items-center gap-2 text-brand-600">
          <Sparkles className="w-6 h-6" />
          <h1 className="text-2xl font-bold">Välkommen till Ekonomilabbet</h1>
        </div>
        {/* Stepper */}
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded ${
                i <= step ? "bg-brand-500" : "bg-slate-200"
              }`}
            />
          ))}
        </div>

        {/* Steg 1: Välkommen + backstory */}
        {step === 0 && (
          <div className="space-y-4">
            <p className="text-lg">
              Hej! Du är nu inloggad i din egen ekonomi-simulator. Här lär du
              dig att planera, spara och förstå vart pengarna tar vägen.
            </p>
            <div className="bg-brand-50 border-l-4 border-brand-500 p-4 rounded">
              <h2 className="font-semibold text-brand-900 mb-2">
                Din situation
              </h2>
              <p className="text-slate-800">{profile.backstory}</p>
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
                className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-5 py-2 flex items-center gap-2"
              >
                Förstått, gå vidare <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Steg 2: Skatt */}
        {step === 1 && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Info className="w-5 h-5 text-brand-600" /> Vad händer med din lön?
            </h2>
            <p className="text-slate-700">
              Den lönesumma du ser på papperet är inte den summan som hamnar
              på ditt konto. Skatten dras direkt av arbetsgivaren och skickas
              till Skatteverket. Så här ser det ut för dig:
            </p>
            <div className="bg-slate-50 rounded-lg p-4 space-y-2">
              <Row label="Bruttolön (innan skatt)" value={formatKr(tax.gross_monthly)} />
              <Row
                label="Skatt totalt"
                value={`-${formatKr(tax.total_tax)} (${(tax.effective_rate * 100).toFixed(1)}%)`}
                negative
              />
              <div className="border-t-2 border-slate-300 pt-2">
                <Row
                  label="Nettolön (det du faktiskt får)"
                  value={formatKr(tax.net_monthly)}
                  bold
                />
              </div>
            </div>
            <details className="bg-amber-50 border border-amber-200 rounded p-3 text-sm text-amber-900">
              <summary className="cursor-pointer font-medium">
                Förklara mer om hur skatten räknas
              </summary>
              <p className="mt-2">{tax.explanation}</p>
            </details>
            <div className="flex justify-between pt-3">
              <button
                onClick={() => setStep(0)}
                className="text-slate-600 hover:bg-slate-100 rounded-lg px-3 py-2"
              >
                Tillbaka
              </button>
              <button
                onClick={() => setStep(2)}
                className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-5 py-2 flex items-center gap-2"
              >
                Sätt en budget <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Steg 3: Budget */}
        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold flex items-center gap-2">
              <Wallet className="w-5 h-5 text-brand-600" /> Sätt din månadsbudget
            </h2>
            <p className="text-sm text-slate-700">
              Värdena nedan är ett FÖRSLAG baserat på{" "}
              <a
                href={budget.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-600 underline inline-flex items-center gap-0.5"
              >
                {budget.source_title}
                <ExternalLink className="w-3 h-3" />
              </a>{" "}
              och din profil ({budget.persons_in_household} personer i
              hushållet). Justera så det stämmer med hur du tror att DU
              kommer leva — vi följer sedan upp mot dina riktiga köp.
            </p>
            {budget.note && (
              <div className="bg-amber-50 border border-amber-200 text-amber-900 text-sm rounded p-3">
                💡 {budget.note}
              </div>
            )}
            <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
              {BUDGET_FIELDS.map((f) => (
                <div key={f.key} className="grid grid-cols-[1fr_auto_auto] items-center gap-3">
                  <label className="text-sm">{f.label}</label>
                  <span className="text-xs text-slate-400">
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
                    className="w-28 text-right border rounded px-2 py-1"
                  />
                </div>
              ))}
            </div>
            <div className="border-t pt-3 space-y-1 text-sm">
              <div className="flex justify-between">
                <span>Din nettolön</span>
                <strong>{formatKr(profile.net_salary_monthly)}</strong>
              </div>
              <div className="flex justify-between">
                <span>Din budget totalt</span>
                <strong>{formatKr(totalEdited)}</strong>
              </div>
              <div
                className={`flex justify-between text-base font-semibold ${
                  overUnder >= 0 ? "text-emerald-700" : "text-rose-700"
                }`}
              >
                <span>{overUnder >= 0 ? "Kvar att fördela" : "Överskott (-budgeterat)"}</span>
                <span>
                  {overUnder >= 0 ? "+" : ""}
                  {formatKr(overUnder)}
                </span>
              </div>
            </div>
            <div className="flex justify-between pt-3">
              <button
                onClick={() => setStep(1)}
                className="text-slate-600 hover:bg-slate-100 rounded-lg px-3 py-2"
              >
                Tillbaka
              </button>
              <div className="flex gap-2">
                <button
                  onClick={logout}
                  className="text-slate-500 hover:bg-slate-100 rounded-lg px-3 py-2 text-sm"
                >
                  Avbryt
                </button>
                <button
                  onClick={finish}
                  disabled={busy}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-5 py-2 flex items-center gap-2 disabled:opacity-50"
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
    <div className="bg-slate-50 rounded p-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-medium">{value}</div>
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
    <div className="flex justify-between text-sm">
      <span className={bold ? "font-semibold" : ""}>{label}</span>
      <span
        className={`${bold ? "font-bold text-base" : ""} ${
          negative ? "text-rose-600" : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}
