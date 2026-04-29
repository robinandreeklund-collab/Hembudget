/**
 * HouseholdSplitQuiz — pedagogisk 'veil of ignorance'-onboarding.
 *
 * Eleven väljer fördelningsmodell INNAN partnerns lön avslöjas.
 * Det blir ett ärligt etiskt val (Rawls 1971) snarare än ett
 * rationellt självoptimerings-val.
 *
 * Visas BARA om:
 *   family_status != 'ensam' (har partner)
 *   AND cost_split_preference IS NULL (ej beslutat ännu)
 *
 * Efter beslut: visas en reflektionsbanner som jämför vad eleven
 * VALDE med vad andra modeller hade gett — pedagogiskt skifte från
 * matematik till etik.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle, Eye, Heart, Scale, Users,
} from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";

interface CostSplitOut {
  family_status: string;
  needs_decision: boolean;
  cost_split_preference: string | null;
  cost_split_decided_at: string | null;
  partner_profession: string | null;
  partner_gross_salary: number | null;
  student_share_pct: number | null;
}

const OPTIONS = [
  {
    value: "even_50_50",
    icon: Scale,
    label: "50/50 — vi delar lika",
    summary: "Båda betalar exakt halva varje gemensam kostnad.",
    pedagogics:
      "Lättförståeligt och känns rättvist på papper. " +
      "Men: om en av er tjänar mycket mer kommer den med lägre lön " +
      "ha mindre marginal kvar varje månad. Är det rättvist?",
  },
  {
    value: "pro_rata",
    icon: Users,
    label: "Proportionellt — den som tjänar mer betalar mer",
    summary:
      "Var och en betalar samma andel av sin egen lön — så ni har " +
      "ungefär samma marginal kvar.",
    pedagogics:
      "Matematiskt rättvist och vanligast bland sambor i Sverige idag. " +
      "Den med högre inkomst tar en större del av hyran så båda har " +
      "lika mycket kvar att leva på.",
  },
  {
    value: "all_shared",
    icon: Heart,
    label: "Allt delas — gemensam ekonomi",
    summary:
      "Båda löner går in på ett gemensamt konto. Inga 'mina pengar' " +
      "eller 'dina pengar'.",
    pedagogics:
      "Mest engagerat — kräver förtroende. Vissa par mår bra av detta, " +
      "andra känner sig kontrollerade. Inget rätt eller fel — beror " +
      "på relationen.",
  },
];

export function HouseholdSplitQuiz() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [showReflection, setShowReflection] = useState(false);

  const splitQ = useQuery({
    queryKey: ["student-cost-split"],
    queryFn: () => api<CostSplitOut>("/student/cost-split"),
  });

  const saveMut = useMutation({
    mutationFn: (preference: string) =>
      api<CostSplitOut>("/student/cost-split", {
        method: "POST",
        body: JSON.stringify({ preference }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["student-cost-split"] });
      qc.invalidateQueries({ queryKey: ["student-profile"] });
      setShowReflection(true);
    },
  });

  if (splitQ.isLoading) return null;
  const data = splitQ.data;
  if (!data) return null;

  // Visa quiz BARA om eleven har partner OCH inte beslutat ännu
  if (!data.needs_decision && !showReflection) return null;

  if (showReflection && saveMut.data) {
    return <ReflectionBanner result={saveMut.data} onClose={() => setShowReflection(false)} />;
  }

  return (
    <div className="bg-white border-2 border-amber-300 rounded-xl p-5 mb-4 space-y-4 shadow-sm">
      <div className="flex items-center gap-2">
        <Eye className="w-5 h-5 text-amber-600" />
        <h2 className="font-semibold text-lg">
          Innan vi avslöjar din partners ekonomi — en fråga
        </h2>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm space-y-2">
        <p>
          Du har en sambo i din profil. Innan vi visar vad din partner tjänar
          vill vi att du svarar på en fråga om <strong>dig själv</strong>:
        </p>
        <p>
          <strong>
            Hur tycker du att gemensamma kostnader (hyra, el, mat hemma,
            försäkringar) ska fördelas i ett hushåll?
          </strong>
        </p>
        <p className="text-xs italic text-slate-700">
          Du vet inte än om du eller din partner tjänar mer. Svara utifrån
          vad du <em>tycker</em> är rätt — inte vad som gynnar dig själv.
          Det är en fråga om värderingar, inte matematik.
        </p>
      </div>

      <div className="space-y-2">
        {OPTIONS.map((opt) => {
          const Icon = opt.icon;
          const isSelected = selected === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setSelected(opt.value)}
              className={`w-full text-left border-2 rounded-lg p-3 transition-all ${
                isSelected
                  ? "border-amber-500 bg-amber-50"
                  : "border-slate-200 bg-white hover:border-amber-300"
              }`}
            >
              <div className="flex items-start gap-2">
                <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${
                  isSelected ? "text-amber-600" : "text-slate-500"
                }`} />
                <div className="flex-1">
                  <div className="font-medium text-sm">{opt.label}</div>
                  <div className="text-xs text-slate-600 mt-0.5">
                    {opt.summary}
                  </div>
                  {isSelected && (
                    <div className="mt-2 pt-2 border-t border-amber-200 text-xs text-slate-700">
                      <strong>Tänk på:</strong> {opt.pedagogics}
                    </div>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex justify-end">
        <button
          onClick={() => selected && saveMut.mutate(selected)}
          disabled={!selected || saveMut.isPending}
          className="bg-amber-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
        >
          {saveMut.isPending ? "Sparar…" : "Bekräfta valet — visa min partner"}
        </button>
      </div>
    </div>
  );
}

function ReflectionBanner({ result, onClose }: { result: CostSplitOut; onClose: () => void }) {
  if (!result.partner_gross_salary || result.student_share_pct === null) {
    return null;
  }

  // Eleven behöver veta sin egen lön för jämförelse — hämta från profile
  const profileQ = useQuery({
    queryKey: ["student-profile"],
    queryFn: () => api<{ gross_salary_monthly: number }>("/student/profile"),
  });
  const studentSalary = profileQ.data?.gross_salary_monthly ?? 0;

  const pref = result.cost_split_preference;
  const partnerSalary = result.partner_gross_salary;
  const studentSharePct = result.student_share_pct;
  const earnsMore = studentSalary > partnerSalary;
  const earnsLess = studentSalary < partnerSalary;
  const sameLevel = !earnsMore && !earnsLess;

  let reflection = "";
  if (pref === "even_50_50" && earnsMore) {
    reflection =
      "Du valde 50/50 och du tjänar mer. Det är generöst mot din partner — " +
      "du har mindre marginal än du hade haft med proportionell fördelning, " +
      "men ni delar lika ansvar. Pedagogiskt: din partner får mer kvar att leva på.";
  } else if (pref === "even_50_50" && earnsLess) {
    reflection =
      "Du valde 50/50 och din partner tjänar mer. Du betalar lika mycket som din " +
      "partner men har mindre marginal kvar. Värt att fundera: hade du valt " +
      "samma sak om du visste vem som tjänade mer?";
  } else if (pref === "pro_rata" && earnsMore) {
    reflection =
      "Du valde proportionellt och du tjänar mer. Det innebär att DU bär en större " +
      "andel av hushållskostnaderna — pedagogiskt: båda får ungefär samma marginal " +
      "kvar att leva på trots olika löner.";
  } else if (pref === "pro_rata" && earnsLess) {
    reflection =
      "Du valde proportionellt och din partner tjänar mer. Det innebär att din " +
      "partner bär en större andel — du har samma marginal som hen trots " +
      "lägre lön. Det är ett moget val.";
  } else if (pref === "all_shared") {
    reflection =
      "Du valde gemensam ekonomi. Båda löner går till hushållet och beslut " +
      "tas tillsammans. Det kräver förtroende — men ger pedagogiskt den " +
      "tightaste bilden av hushållets totalbudget.";
  } else if (sameLevel) {
    reflection =
      "Ni tjänar ungefär lika mycket — alla tre modeller hade gett ungefär " +
      "samma resultat ekonomiskt. Pedagogiskt: ditt val handlar mer om " +
      "värderingar än om matematik här.";
  }

  return (
    <div className="bg-emerald-50 border-2 border-emerald-300 rounded-xl p-5 mb-4 space-y-3">
      <div className="flex items-center gap-2 font-semibold">
        <CheckCircle className="w-5 h-5 text-emerald-600" />
        Valet är gjort — så här ser det ut
      </div>

      <div className="bg-white border rounded p-3 space-y-1.5 text-sm">
        <div className="flex justify-between">
          <span>Du tjänar (brutto/mån):</span>
          <strong>{studentSalary.toLocaleString("sv-SE")} kr</strong>
        </div>
        <div className="flex justify-between">
          <span>Din partner ({result.partner_profession}) tjänar:</span>
          <strong>{partnerSalary.toLocaleString("sv-SE")} kr</strong>
        </div>
        <div className="flex justify-between border-t pt-1.5 mt-1.5">
          <span>Modellen du valde:</span>
          <strong>
            {pref === "even_50_50" && "50/50 jämnt"}
            {pref === "pro_rata" && "Proportionellt"}
            {pref === "all_shared" && "Gemensam ekonomi"}
          </strong>
        </div>
        <div className="flex justify-between text-emerald-900">
          <span>Du betalar av gemensamma kostnader:</span>
          <strong>{studentSharePct?.toFixed(0)} %</strong>
        </div>
      </div>

      <div className="bg-white border-l-4 border-emerald-400 p-3 text-sm text-slate-700 italic">
        {reflection}
      </div>

      <div className="text-xs text-slate-500">
        Partnerns lön kommer nu in på ditt konto varje månad som "LÖN SAMBO" —
        ekonomin går ihop. Du kan ändra modell senare i inställningar, men ditt
        första ärliga val sparas alltid.
      </div>

      <div className="flex justify-end">
        <button
          onClick={onClose}
          className="bg-emerald-600 text-white px-4 py-2 rounded text-sm"
        >
          Förstått
        </button>
      </div>
    </div>
  );
}
