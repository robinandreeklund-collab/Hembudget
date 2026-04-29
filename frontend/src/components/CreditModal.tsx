/**
 * CreditModal — pedagogiskt flöde när elevens ekonomi inte går ihop.
 *
 * Tre vyer:
 *  1. intro — visar shortfall + tre val (privatlån, SMS-lån, avbryt)
 *  2. apply — formulär med belopp + löptid + ändamål
 *  3. result — godkänd/avslag med faktor-uppdelning + accept/decline
 *
 * Alla pedagogiska texter kommer från backend (explanation,
 * pedagogical_summary). Vi visar dem ordagrant — eleven ska förstå
 * VARFÖR scoren blev som den blev.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowRight, CheckCircle, Info, X, XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, formatSEK } from "@/api/client";

interface AffordabilityOut {
  ok: boolean;
  current_balance: number;
  threshold: number;
  shortfall: number;
  explanation: string;
  account_kind: string;
  options: string[];
}

interface ScoreFactor {
  name: string;
  points: number;
  explanation: string;
}

interface ApplyOut {
  application_id: number;
  approved: boolean;
  score: number;
  score_threshold: number;
  factors: ScoreFactor[];
  simulated_lender: string;
  offered_rate?: number | null;
  offered_monthly_payment?: number | null;
  offered_total_cost?: number | null;
  offered_total_interest?: number | null;
  decline_reason?: string | null;
  pedagogical_summary: string;
}

interface AcceptOut {
  loan_id: number;
  transaction_id: number;
  deposited_amount: number;
  monthly_payment: number;
  interest_rate: number;
  months: number;
  pedagogical_note: string;
}

type View = "intro" | "apply" | "result" | "sms_intro" | "sms_apply" | "sms_result";

interface SmsApplyOut {
  application_id: number;
  approved: boolean;
  simulated_lender: string;
  nominal_rate: number;
  effective_rate: number;
  setup_fee: number;
  avi_fee_per_month: number;
  months: number;
  requested_amount: number;
  total_to_pay: number;
  interest_kr: number;
  total_fees: number;
  pedagogical_warning: string;
}

interface SmsAcceptOut {
  loan_id: number;
  transaction_id: number;
  deposited_amount: number;
  total_to_pay: number;
  months: number;
  pedagogical_note: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  shortfall: number;
  affordability: AffordabilityOut;
  /** Konto där lånet sätts in. Default: lönekontot. */
  depositAccountId: number;
}

export function CreditModal({
  open, onClose, shortfall, affordability, depositAccountId,
}: Props) {
  const qc = useQueryClient();
  const [view, setView] = useState<View>("intro");
  const [amount, setAmount] = useState<string>(
    String(Math.max(5000, Math.ceil((shortfall + 5000) / 1000) * 1000))
  );
  const [months, setMonths] = useState<number>(24);
  const [purpose, setPurpose] = useState<string>("Oförutsedda utgifter");
  const [applyResult, setApplyResult] = useState<ApplyOut | null>(null);
  const [acceptResult, setAcceptResult] = useState<AcceptOut | null>(null);
  const [smsAmount, setSmsAmount] = useState<string>(
    String(Math.min(30_000, Math.max(1_000, Math.ceil(shortfall / 1000) * 1000)))
  );
  const [smsMonths, setSmsMonths] = useState<number>(1);
  const [smsApplyResult, setSmsApplyResult] = useState<SmsApplyOut | null>(null);
  const [smsAcceptResult, setSmsAcceptResult] = useState<SmsAcceptOut | null>(null);

  useEffect(() => {
    if (!open) {
      // Återställ när modalen stängs
      setView("intro");
      setApplyResult(null);
      setAcceptResult(null);
    }
  }, [open]);

  const applyMut = useMutation({
    mutationFn: (body: {
      requested_amount: string;
      requested_months: number;
      purpose: string;
    }) =>
      api<ApplyOut>("/credit/private/apply", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      setApplyResult(data);
      setView("result");
    },
  });

  const acceptMut = useMutation({
    mutationFn: (body: { application_id: number; deposit_account_id: number }) =>
      api<AcceptOut>("/credit/private/accept", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      setAcceptResult(data);
      qc.invalidateQueries({ queryKey: ["balances"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["loans"] });
    },
  });

  const smsApplyMut = useMutation({
    mutationFn: (body: { requested_amount: string; requested_months: number }) =>
      api<SmsApplyOut>("/credit/sms/apply", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      setSmsApplyResult(data);
      setView("sms_result");
    },
  });

  const smsAcceptMut = useMutation({
    mutationFn: (body: { application_id: number; deposit_account_id: number }) =>
      api<SmsAcceptOut>("/credit/sms/accept", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      setSmsAcceptResult(data);
      qc.invalidateQueries({ queryKey: ["balances"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["loans"] });
    },
  });

  const declineMut = useMutation({
    mutationFn: (body: { application_id: number }) =>
      api("/credit/private/decline", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      onClose();
    },
  });

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="font-semibold flex items-center gap-2">
            {view === "intro" && (
              <>
                <AlertTriangle className="w-5 h-5 text-amber-600" />
                Din ekonomi går inte ihop
              </>
            )}
            {view === "apply" && "Ansök om privatlån"}
            {view === "result" && (applyResult?.approved
              ? <><CheckCircle className="w-5 h-5 text-emerald-600" />Banken godkände</>
              : <><XCircle className="w-5 h-5 text-red-600" />Banken tackade nej</>
            )}
          </h2>
          <button onClick={onClose} aria-label="Stäng">
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        <div className="p-5">
          {view === "intro" && (
            <IntroView
              affordability={affordability}
              shortfall={shortfall}
              onPickPrivate={() => setView("apply")}
              onPickSms={() => setView("sms_intro")}
              onCancel={onClose}
            />
          )}
          {view === "sms_intro" && (
            <SmsIntroView
              shortfall={shortfall}
              onContinue={() => setView("sms_apply")}
              onBack={() => setView("intro")}
            />
          )}
          {view === "sms_apply" && (
            <SmsApplyView
              shortfall={shortfall}
              amount={smsAmount} setAmount={setSmsAmount}
              months={smsMonths} setMonths={setSmsMonths}
              onSubmit={() =>
                smsApplyMut.mutate({
                  requested_amount: String(Number(smsAmount.replace(",", "."))),
                  requested_months: smsMonths,
                })
              }
              loading={smsApplyMut.isPending}
              onBack={() => setView("sms_intro")}
            />
          )}
          {view === "sms_result" && smsApplyResult && !smsAcceptResult && (
            <SmsResultView
              result={smsApplyResult}
              onAccept={() =>
                smsAcceptMut.mutate({
                  application_id: smsApplyResult.application_id,
                  deposit_account_id: depositAccountId,
                })
              }
              onCancel={onClose}
              acceptLoading={smsAcceptMut.isPending}
            />
          )}
          {smsAcceptResult && (
            <SmsAcceptedView result={smsAcceptResult} onClose={onClose} />
          )}

          {view === "apply" && (
            <ApplyView
              shortfall={shortfall}
              amount={amount} setAmount={setAmount}
              months={months} setMonths={setMonths}
              purpose={purpose} setPurpose={setPurpose}
              onSubmit={() =>
                applyMut.mutate({
                  requested_amount: String(Number(amount.replace(",", "."))),
                  requested_months: months,
                  purpose,
                })
              }
              loading={applyMut.isPending}
              error={applyMut.error instanceof Error ? applyMut.error.message : null}
              onBack={() => setView("intro")}
            />
          )}

          {view === "result" && applyResult && !acceptResult && (
            <ResultView
              result={applyResult}
              months={months}
              onAccept={() =>
                acceptMut.mutate({
                  application_id: applyResult.application_id,
                  deposit_account_id: depositAccountId,
                })
              }
              onDecline={() =>
                declineMut.mutate({ application_id: applyResult.application_id })
              }
              onTryAgain={() => setView("apply")}
              acceptLoading={acceptMut.isPending}
            />
          )}

          {acceptResult && (
            <AcceptedView result={acceptResult} onClose={onClose} />
          )}
        </div>
      </div>
    </div>
  );
}

function IntroView({
  affordability, shortfall, onPickPrivate, onPickSms, onCancel,
}: {
  affordability: AffordabilityOut;
  shortfall: number;
  onPickPrivate: () => void;
  onPickSms: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm">
        {affordability.explanation}
      </div>
      <div className="text-sm text-slate-700">
        Du saknar <strong>{formatSEK(shortfall)}</strong> för att klara denna
        utgift. Tre saker kan du göra:
      </div>
      <div className="space-y-2">
        <button
          onClick={onPickPrivate}
          className="w-full bg-emerald-600 text-white px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-emerald-700"
        >
          <ArrowRight className="w-4 h-4" />
          <span className="flex-1 text-left">
            <div className="font-medium">Ansök om privatlån</div>
            <div className="text-xs opacity-90">
              Kreditupplysning · 4–9 % ränta beroende på score
            </div>
          </span>
        </button>
        <button
          onClick={onPickSms}
          className="w-full bg-red-50 border border-red-200 text-red-900 px-4 py-3 rounded-lg flex items-center gap-2 hover:bg-red-100"
        >
          <AlertTriangle className="w-4 h-4" />
          <span className="flex-1 text-left">
            <div className="font-medium">Ta SMS-lån (sista utväg)</div>
            <div className="text-xs opacity-80">
              Snabbt men dyrt · effektiv ränta 80–150 % · undvik om möjligt
            </div>
          </span>
        </button>
        <button
          onClick={onCancel}
          className="w-full bg-white border border-slate-300 text-slate-700 px-4 py-3 rounded-lg hover:bg-slate-50"
        >
          Avbryt köpet/överföringen
        </button>
      </div>
    </div>
  );
}

function ApplyView({
  shortfall, amount, setAmount, months, setMonths, purpose, setPurpose,
  onSubmit, loading, error, onBack,
}: {
  shortfall: number;
  amount: string;
  setAmount: (s: string) => void;
  months: number;
  setMonths: (n: number) => void;
  purpose: string;
  setPurpose: (s: string) => void;
  onSubmit: () => void;
  loading: boolean;
  error: string | null;
  onBack: () => void;
}) {
  const num = Number(amount.replace(",", "."));
  // Live-preview av månadskostnad om eleven gissar 7 % ränta
  const r = 0.07 / 12;
  const n = months;
  const previewMonthly =
    Number.isFinite(num) && num > 0
      ? (num * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1)
      : 0;
  return (
    <div className="space-y-4">
      <div className="text-sm text-slate-600">
        Banken kollar din ekonomi och kommer fram till om du får låna och
        till vilken ränta. Du saknar {formatSEK(shortfall)}.
      </div>
      <div>
        <label className="text-sm font-medium block mb-1">
          Belopp (5 000 – 100 000 kr)
        </label>
        <input
          type="number"
          min={5000}
          max={500000}
          step={1000}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="w-full border rounded px-3 py-2"
        />
      </div>
      <div>
        <label className="text-sm font-medium block mb-1">
          Återbetalningstid: <strong>{months} månader</strong>
        </label>
        <input
          type="range"
          min={12}
          max={84}
          step={12}
          value={months}
          onChange={(e) => setMonths(parseInt(e.target.value))}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-slate-500">
          <span>1 år</span><span>3 år</span><span>5 år</span><span>7 år</span>
        </div>
      </div>
      <div>
        <label className="text-sm font-medium block mb-1">Ändamål</label>
        <select
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
          className="w-full border rounded px-3 py-2"
        >
          <option>Oförutsedda utgifter</option>
          <option>Boende</option>
          <option>Studieskuld</option>
          <option>Annat</option>
        </select>
      </div>
      <div className="bg-slate-50 border rounded p-3 text-sm space-y-1">
        <div className="font-medium">Förhandsvisning vid 7 % ränta</div>
        <div className="flex justify-between">
          <span>Månadskostnad ungefär:</span>
          <strong>{formatSEK(previewMonthly)}</strong>
        </div>
        <div className="flex justify-between">
          <span>Total tillbakabetalning:</span>
          <strong>{formatSEK(previewMonthly * months)}</strong>
        </div>
        <div className="text-xs text-slate-500 mt-1">
          Detta är en uppskattning. Banken sätter den faktiska räntan när
          du ansöker.
        </div>
      </div>
      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
          {error}
        </div>
      )}
      <div className="flex gap-2 justify-end">
        <button onClick={onBack} className="px-4 py-2 rounded border">
          Tillbaka
        </button>
        <button
          onClick={onSubmit}
          disabled={loading}
          className="bg-emerald-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {loading ? "Skickar in…" : "Skicka in ansökan"}
        </button>
      </div>
    </div>
  );
}

function ResultView({
  result, months, onAccept, onDecline, onTryAgain, acceptLoading,
}: {
  result: ApplyOut;
  months: number;
  onAccept: () => void;
  onDecline: () => void;
  onTryAgain: () => void;
  acceptLoading: boolean;
}) {
  return (
    <div className="space-y-4">
      <div
        className={`rounded p-3 text-sm ${
          result.approved
            ? "bg-emerald-50 border border-emerald-200"
            : "bg-red-50 border border-red-200"
        }`}
      >
        <div className="font-medium mb-1">
          Bank: {result.simulated_lender} · Score: {result.score} av 850
        </div>
        <div className="text-xs whitespace-pre-line">
          {result.pedagogical_summary}
        </div>
      </div>

      <div>
        <div className="text-sm font-medium mb-2 flex items-center gap-1">
          <Info className="w-4 h-4" />
          Så räknades din score
        </div>
        <div className="space-y-2">
          {result.factors.map((f, i) => (
            <div
              key={i}
              className="border rounded p-2 text-xs flex gap-3"
            >
              <div
                className={`font-mono font-semibold ${
                  f.points > 0
                    ? "text-emerald-700"
                    : f.points < 0
                      ? "text-red-700"
                      : "text-slate-500"
                }`}
                style={{ minWidth: 56 }}
              >
                {f.points >= 0 ? "+" : ""}{f.points} p
              </div>
              <div className="flex-1">
                <div className="font-medium text-slate-800">{f.name}</div>
                <div className="text-slate-600 mt-0.5">{f.explanation}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {result.approved && result.offered_rate !== null && result.offered_rate !== undefined && (
        <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-sm space-y-1">
          <div className="font-medium">Erbjudande</div>
          <div className="flex justify-between">
            <span>Ränta (nominell):</span>
            <strong>{(result.offered_rate * 100).toFixed(2)} %</strong>
          </div>
          <div className="flex justify-between">
            <span>Månadskostnad:</span>
            <strong>{formatSEK(result.offered_monthly_payment ?? 0)}</strong>
          </div>
          <div className="flex justify-between">
            <span>Totalt över {months} mån:</span>
            <strong>{formatSEK(result.offered_total_cost ?? 0)}</strong>
          </div>
          <div className="flex justify-between text-amber-700">
            <span>Varav ränta:</span>
            <strong>{formatSEK(result.offered_total_interest ?? 0)}</strong>
          </div>
        </div>
      )}

      <div className="flex gap-2 justify-end flex-wrap">
        {result.approved ? (
          <>
            <button onClick={onDecline} className="px-4 py-2 rounded border">
              Tacka nej
            </button>
            <button
              onClick={onAccept}
              disabled={acceptLoading}
              className="bg-emerald-600 text-white px-4 py-2 rounded disabled:opacity-50"
            >
              {acceptLoading ? "Tecknar…" : "Acceptera lånet"}
            </button>
          </>
        ) : (
          <>
            <button onClick={onTryAgain} className="px-4 py-2 rounded border">
              Försök ett annat belopp
            </button>
            <button
              onClick={onDecline}
              className="bg-slate-700 text-white px-4 py-2 rounded"
            >
              Stäng
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function AcceptedView({
  result, onClose,
}: {
  result: AcceptOut;
  onClose: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-sm">
        <div className="font-medium flex items-center gap-2 mb-1">
          <CheckCircle className="w-5 h-5 text-emerald-700" />
          Lånet är tecknat och pengarna är inne
        </div>
        <p className="whitespace-pre-line text-slate-700">
          {result.pedagogical_note}
        </p>
      </div>
      <div className="flex justify-end">
        <button
          onClick={onClose}
          className="bg-emerald-600 text-white px-4 py-2 rounded"
        >
          Klar
        </button>
      </div>
    </div>
  );
}

// ---------- SMS-vyer ----------

function SmsIntroView({
  shortfall, onContinue, onBack,
}: {
  shortfall: number;
  onContinue: () => void;
  onBack: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="bg-red-50 border-2 border-red-300 rounded p-4 text-sm space-y-2">
        <div className="font-bold text-red-900 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5" />
          DETTA ÄR DYR KREDIT — LÄS NOGA
        </div>
        <ul className="space-y-1 text-red-900 list-disc ml-5">
          <li>Effektiv ränta typiskt 80 % – 200 %</li>
          <li>500 kr i uppläggningsavgift</li>
          <li>50 kr per månad i aviavgift</li>
          <li>Risk att hamna i skuldspiral om du inte betalar i tid</li>
        </ul>
      </div>
      <div className="text-sm text-slate-700">
        SMS-lån är ett sätt att lösa akut likviditetsbrist — men det är
        ett dyrt sätt. Du saknar {formatSEK(shortfall)} och vet att ett
        privatlån inte är ett alternativ. SMS-lånet ger dig pengarna
        snabbt, men du får tillbaka mycket mer av dem än du lånade.
      </div>
      <div className="text-xs text-slate-500 italic">
        Pedagogisk markering: I denna simulator är SMS-lån alltid godkända
        så länge du har någon inkomst — det är just det som gör SMS-lån
        farliga i verkligheten också.
      </div>
      <div className="flex gap-2 justify-end">
        <button onClick={onBack} className="px-4 py-2 rounded border">
          Tillbaka
        </button>
        <button
          onClick={onContinue}
          className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
        >
          Jag förstår — fortsätt
        </button>
      </div>
    </div>
  );
}

function SmsApplyView({
  shortfall, amount, setAmount, months, setMonths, onSubmit, loading, onBack,
}: {
  shortfall: number;
  amount: string;
  setAmount: (s: string) => void;
  months: number;
  setMonths: (n: number) => void;
  onSubmit: () => void;
  loading: boolean;
  onBack: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="text-sm text-slate-600">
        Du saknar {formatSEK(shortfall)}. SMS-lån har korta löptider
        (1–3 månader) och hög ränta.
      </div>
      <div>
        <label className="text-sm font-medium block mb-1">
          Belopp (1 000 – 30 000 kr)
        </label>
        <input
          type="number"
          min={1000}
          max={30000}
          step={500}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="w-full border rounded px-3 py-2"
        />
      </div>
      <div>
        <label className="text-sm font-medium block mb-1">
          Återbetalningstid: <strong>{months} månad{months !== 1 ? "er" : ""}</strong>
        </label>
        <div className="flex gap-2">
          {[1, 2, 3].map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMonths(m)}
              className={`flex-1 py-2 rounded border ${
                months === m
                  ? "bg-red-100 border-red-400 text-red-900"
                  : "bg-white border-slate-300 text-slate-700"
              }`}
            >
              {m} mån
            </button>
          ))}
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button onClick={onBack} className="px-4 py-2 rounded border">
          Tillbaka
        </button>
        <button
          onClick={onSubmit}
          disabled={loading}
          className="bg-red-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {loading ? "Skickar in…" : "Ansök om SMS-lån"}
        </button>
      </div>
    </div>
  );
}

function SmsResultView({
  result, onAccept, onCancel, acceptLoading,
}: {
  result: SmsApplyOut;
  onAccept: () => void;
  onCancel: () => void;
  acceptLoading: boolean;
}) {
  return (
    <div className="space-y-4">
      <div className="bg-red-50 border-2 border-red-300 rounded p-3 text-sm space-y-1">
        <div className="font-bold text-red-900">
          Långivare: {result.simulated_lender}
        </div>
        <p className="text-red-900 whitespace-pre-line text-xs">
          {result.pedagogical_warning}
        </p>
      </div>

      <div className="border rounded p-3 text-sm space-y-1">
        <div className="font-medium mb-1">Villkor</div>
        <div className="flex justify-between">
          <span>Lånebelopp:</span>
          <strong>{formatSEK(result.requested_amount)}</strong>
        </div>
        <div className="flex justify-between">
          <span>Nominell årlig ränta:</span>
          <strong>{(result.nominal_rate * 100).toFixed(0)} %</strong>
        </div>
        <div className="flex justify-between">
          <span>Effektiv ränta:</span>
          <strong className="text-red-700">
            {(result.effective_rate * 100).toFixed(0)} %
          </strong>
        </div>
        <div className="flex justify-between">
          <span>Uppläggningsavgift:</span>
          <strong>{formatSEK(result.setup_fee)}</strong>
        </div>
        <div className="flex justify-between">
          <span>Aviavgift × {result.months}:</span>
          <strong>{formatSEK(result.avi_fee_per_month * result.months)}</strong>
        </div>
        <div className="flex justify-between">
          <span>Ränta i kr:</span>
          <strong>{formatSEK(result.interest_kr)}</strong>
        </div>
        <div className="flex justify-between border-t pt-1 mt-1 font-semibold">
          <span>Totalt att betala:</span>
          <strong className="text-red-700">{formatSEK(result.total_to_pay)}</strong>
        </div>
      </div>

      <div className="flex gap-2 justify-end">
        <button
          onClick={onCancel}
          className="px-4 py-2 rounded border bg-emerald-50 border-emerald-300 text-emerald-900"
        >
          Avbryt — jag tar inte detta
        </button>
        <button
          onClick={onAccept}
          disabled={acceptLoading}
          className="bg-red-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {acceptLoading ? "Tecknar…" : "Acceptera SMS-lånet"}
        </button>
      </div>
    </div>
  );
}

function SmsAcceptedView({
  result, onClose,
}: {
  result: SmsAcceptOut;
  onClose: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border-2 border-amber-300 rounded p-3 text-sm">
        <div className="font-medium flex items-center gap-2 mb-2">
          <CheckCircle className="w-5 h-5 text-emerald-700" />
          Pengarna är inne — men nu vidtar konsekvenserna
        </div>
        <p className="whitespace-pre-line text-slate-800">
          {result.pedagogical_note}
        </p>
      </div>
      <div className="bg-slate-50 border rounded p-3 text-xs text-slate-700">
        <strong>För läraren:</strong> denna affär är loggad i ledger:n
        med <code>is_high_cost_credit=True</code> och syns rödmarkerad
        i klassöversikten.
      </div>
      <div className="flex justify-end">
        <button
          onClick={onClose}
          className="bg-slate-700 text-white px-4 py-2 rounded"
        >
          Klar
        </button>
      </div>
    </div>
  );
}
