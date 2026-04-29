/**
 * /bank — Ekonomilabbets bank (idé 3 i dev_v1.md).
 *
 * Tre lägen:
 *  1. PIN-onboarding (om has_pin=false): eleven sätter 4-siffrig PIN
 *  2. Inloggning: QR + polla session tills bekräftad
 *  3. Inloggad: dashboard (kontoutdrag, kommande betalningar, lån)
 *
 * EkonomilabbetID är vår simulering av en BankID-liknande lösning.
 * Eleven förstår skillnaden mellan något-du-har (telefon/QR) och
 * något-du-vet (PIN). Den här simuleringen tränar mönstret utan
 * riktig BankID-integration.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building,
  CheckCircle2,
  Loader2,
  Lock,
  ShieldCheck,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { Card } from "@/components/Card";


interface BankMeOut {
  has_pin: boolean;
  student_id: number;
}


interface InitSessionOut {
  token: string;
  qr_url: string;
  expires_at: string;
  purpose: string;
}


interface SessionStatusOut {
  token: string;
  purpose: string;
  confirmed: boolean;
  expired: boolean;
  confirmed_at: string | null;
}


export default function Bank() {
  const [searchParams] = useSearchParams();
  // Mobil-flödet (sign-confirm-vyn) tar över när token finns i URL:en
  const signToken = searchParams.get("token");
  // Sign-vy bara aktiv när URL:en innehåller ?token=...
  const isSignView = searchParams.get("sign") === "1" || !!signToken;

  // Sign-vy renderas FÖRST — innan vi rör några auth-skyddade endpoints.
  // Telefonen som scannar QR är typiskt INTE inloggad, så vi måste
  // hoppa hela /bank/me-fetchen och bara visa PIN-formuläret.
  if (isSignView && signToken) {
    return (
      <BankShell mobile>
        <SignConfirmView token={signToken} />
      </BankShell>
    );
  }

  return <BankAuthenticatedShell />;
}

function BankAuthenticatedShell() {
  const meQ = useQuery({
    queryKey: ["bank-me"],
    queryFn: () => api<BankMeOut>("/bank/me"),
  });

  // Session-state — null tills eleven trycker 'Logga in'
  const [session, setSession] = useState<InitSessionOut | null>(null);
  // Polla session-status så desktop vet när mobilen bekräftat
  const sessionStatusQ = useQuery({
    queryKey: ["bank-session-status", session?.token],
    queryFn: () =>
      api<SessionStatusOut>(`/bank/session/${session!.token}`),
    enabled: !!session,
    refetchInterval: 2000,
  });

  // När session bekräftas → markera "loggat in" lokalt (15 min)
  useEffect(() => {
    if (sessionStatusQ.data?.confirmed) {
      sessionStorage.setItem(
        "bank_logged_in_at",
        String(Date.now()),
      );
    }
  }, [sessionStatusQ.data?.confirmed]);

  if (meQ.isLoading) {
    return (
      <BankShell>
        <Card><div className="text-sm text-slate-600">Laddar…</div></Card>
      </BankShell>
    );
  }

  if (meQ.error) {
    return (
      <BankShell>
        <Card>
          <div className="text-sm text-rose-700">
            Banken är inte tillgänglig: {String(meQ.error)}
          </div>
        </Card>
      </BankShell>
    );
  }

  // 1. PIN-onboarding
  if (meQ.data && !meQ.data.has_pin) {
    return (
      <BankShell>
        <PinOnboarding onDone={() => meQ.refetch()} />
      </BankShell>
    );
  }

  const loggedIn =
    sessionStatusQ.data?.confirmed ||
    isRecentLogin();

  // 2. Inloggning eller 3. Dashboard
  return (
    <BankShell>
      {!loggedIn ? (
        <LoginView
          session={session}
          onInit={(s) => setSession(s)}
          status={sessionStatusQ.data ?? null}
        />
      ) : (
        <BankDashboard />
      )}
    </BankShell>
  );
}


function isRecentLogin(): boolean {
  const ts = sessionStorage.getItem("bank_logged_in_at");
  if (!ts) return false;
  const age = Date.now() - parseInt(ts, 10);
  return age < 15 * 60 * 1000; // 15 min
}


function BankShell({
  children,
  mobile = false,
}: {
  children: React.ReactNode;
  mobile?: boolean;
}) {
  return (
    <div className={mobile ? "min-h-screen bg-slate-50" : "p-3 md:p-6 space-y-4 md:space-y-5"}>
      <div className="bg-slate-900 text-white px-4 py-3 rounded-md flex items-center gap-2">
        <Building className="w-5 h-5" />
        <span className="serif text-xl">Ekonomilabbet Bank</span>
        <span className="ml-auto text-xs text-slate-300">
          {mobile ? "Mobil-bekräftelse" : "EkonomilabbetID-simulering"}
        </span>
      </div>
      <div className={mobile ? "p-4" : ""}>{children}</div>
    </div>
  );
}


function PinOnboarding({ onDone }: { onDone: () => void }) {
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const setMut = useMutation({
    mutationFn: (p: string) =>
      api("/bank/set-pin", {
        method: "POST",
        body: JSON.stringify({ pin: p }),
      }),
    onSuccess: () => onDone(),
  });

  const valid =
    /^\d{4}$/.test(pin) && pin === confirm;

  return (
    <Card title="Sätt din bank-PIN">
      <div className="text-sm text-slate-700 leading-relaxed mb-4">
        Bank-PIN är en 4-siffrig kod du själv väljer. Den används
        för att bekräfta inloggning och signera betalningar.
        <br />
        <strong>Viktigt:</strong> i en riktig bank ger du aldrig din
        PIN till någon. Inte ens till banken via telefon. Skapa en
        kod som <em>inte</em> är 1234, ditt födelsedatum eller "0000".
      </div>
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-slate-600 mb-1">
            Välj 4-siffrig PIN
          </label>
          <input
            type="password"
            inputMode="numeric"
            pattern="\d{4}"
            maxLength={4}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
            className="border rounded px-3 py-2 w-32 text-center tracking-widest text-lg"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-600 mb-1">
            Upprepa PIN
          </label>
          <input
            type="password"
            inputMode="numeric"
            pattern="\d{4}"
            maxLength={4}
            value={confirm}
            onChange={(e) =>
              setConfirm(e.target.value.replace(/\D/g, ""))
            }
            className="border rounded px-3 py-2 w-32 text-center tracking-widest text-lg"
          />
        </div>
        <button
          onClick={() => setMut.mutate(pin)}
          disabled={!valid || setMut.isPending}
          className="bg-brand-600 text-white rounded px-4 py-2 disabled:opacity-50"
        >
          {setMut.isPending ? "Sparar…" : "Spara PIN"}
        </button>
        {setMut.error && (
          <div className="text-sm text-rose-700">
            {String(setMut.error)}
          </div>
        )}
        {pin && confirm && pin !== confirm && (
          <div className="text-xs text-amber-700">
            PIN-koderna matchar inte.
          </div>
        )}
      </div>
    </Card>
  );
}


function LoginView({
  session,
  onInit,
  status,
}: {
  session: InitSessionOut | null;
  onInit: (s: InitSessionOut) => void;
  status: SessionStatusOut | null;
}) {
  const initMut = useMutation({
    mutationFn: () =>
      api<InitSessionOut>("/bank/session/init", {
        method: "POST",
        body: JSON.stringify({ purpose: "login" }),
      }),
    onSuccess: (data) => onInit(data),
  });

  if (!session) {
    return (
      <Card title="Logga in i banken">
        <div className="text-sm text-slate-700 leading-relaxed mb-4">
          Tryck på knappen nedan för att starta en EkonomilabbetID-session.
          En QR-kod visas — skanna den med din mobil och bekräfta
          med din PIN.
        </div>
        <button
          onClick={() => initMut.mutate()}
          disabled={initMut.isPending}
          className="bg-brand-600 text-white rounded px-4 py-2 flex items-center gap-2 disabled:opacity-50"
        >
          <Lock className="w-4 h-4" />
          {initMut.isPending ? "Startar…" : "Starta EkonomilabbetID"}
        </button>
        {initMut.error && (
          <div className="text-sm text-rose-700 mt-2">
            {String(initMut.error)}
          </div>
        )}
      </Card>
    );
  }

  // QR-vy: visar token + en länk eleven kan klicka för att simulera
  // mobil-bekräftelse. I verklig BankID skulle telefonen byta läge
  // automatiskt; här klickar eleven på länken och får upp PIN-formuläret.
  const fullUrl = `${window.location.origin}${session.qr_url}`;

  if (status?.expired) {
    return (
      <Card title="Sessionen har löpt ut">
        <div className="text-sm text-slate-700 mb-3">
          Din EkonomilabbetID-session var öppen i 15 minuter. Du behöver
          starta en ny för att logga in.
        </div>
        <button
          onClick={() => initMut.mutate()}
          className="bg-brand-600 text-white rounded px-4 py-2"
        >
          Starta ny session
        </button>
      </Card>
    );
  }

  return (
    <Card title="Bekräfta på din mobil">
      <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-4">
        <QRPlaceholder url={fullUrl} />
        <div className="space-y-3">
          <div className="text-sm text-slate-700 leading-relaxed">
            <strong>Steg 1:</strong> Öppna din telefon och skanna
            QR-koden — eller (för simulerings-syfte) klicka länken
            nedan i en ny tab/fönster:
          </div>
          <a
            href={session.qr_url}
            target="_blank"
            rel="noreferrer"
            className="block border border-dashed border-slate-300 rounded px-3 py-2 text-xs font-mono text-brand-700 hover:bg-slate-50 break-all"
          >
            {fullUrl}
          </a>
          <div className="text-sm text-slate-700 leading-relaxed">
            <strong>Steg 2:</strong> På telefonen anger du din
            4-siffriga PIN. När du tryckt 'Bekräfta' loggar du in
            automatiskt här på datorn.
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mt-2">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Väntar på bekräftelse…
          </div>
        </div>
      </div>
    </Card>
  );
}


function QRPlaceholder({ url }: { url: string }) {
  // Riktig skannbar QR via qrcode.react. Eleven kan scanna med sin
  // mobil eller klicka länken under för att simulera flödet.
  return (
    <div className="border-4 border-slate-900 rounded p-3 bg-white aspect-square flex flex-col items-center justify-center">
      <QRCodeSVG
        value={url}
        size={140}
        bgColor="#ffffff"
        fgColor="#0f172a"
        level="M"
      />
      <div className="text-[10px] text-slate-500 mt-2 truncate w-full text-center">
        {url.replace(/^https?:\/\//, "")}
      </div>
    </div>
  );
}


function SignConfirmView({ token }: { token: string }) {
  const qc = useQueryClient();
  const [pin, setPin] = useState("");
  const [done, setDone] = useState(false);

  const confirmMut = useMutation({
    mutationFn: (p: string) =>
      api(`/bank/session/${token}/confirm`, {
        method: "POST",
        body: JSON.stringify({ pin: p }),
      }),
    onSuccess: () => {
      setDone(true);
      qc.invalidateQueries({ queryKey: ["bank-session-status", token] });
    },
  });

  if (done) {
    return (
      <Card>
        <div className="flex flex-col items-center text-center py-4">
          <CheckCircle2 className="w-12 h-12 text-emerald-600" />
          <div className="text-base font-semibold mt-2">
            Bekräftat
          </div>
          <div className="text-sm text-slate-600 mt-1">
            Du kan nu stänga den här fliken — din dator har loggat
            in dig automatiskt.
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Bekräfta inloggning">
      <div className="text-sm text-slate-700 leading-relaxed mb-3">
        Mata in din 4-siffriga bank-PIN för att bekräfta att du
        verkligen är du. Detta logger in dig på datorn.
      </div>
      <div className="space-y-3">
        <input
          type="password"
          inputMode="numeric"
          pattern="\d{4}"
          maxLength={4}
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          className="border rounded px-3 py-3 w-full text-center tracking-widest text-2xl"
          placeholder="••••"
          autoFocus
        />
        <button
          onClick={() => confirmMut.mutate(pin)}
          disabled={pin.length !== 4 || confirmMut.isPending}
          className="bg-brand-600 text-white rounded px-4 py-3 w-full disabled:opacity-50"
        >
          {confirmMut.isPending ? "Bekräftar…" : "Bekräfta"}
        </button>
        {confirmMut.error && (
          <div className="text-sm text-rose-700">
            {String(confirmMut.error)}
          </div>
        )}
      </div>
    </Card>
  );
}


type BankTab =
  | "statements"
  | "upcoming"
  | "scheduled"
  | "reminders"
  | "credit";


function BankDashboard() {
  const [tab, setTab] = useState<BankTab>("statements");
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 border-l-4 border-emerald-400 bg-emerald-50/50 rounded-md p-3">
        <ShieldCheck className="w-5 h-5 text-emerald-700 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-slate-700">
          Du är inloggad. Sessionen är giltig i 15 minuter.
        </div>
      </div>
      <div className="flex gap-2 border-b overflow-x-auto">
        {(
          ["statements", "upcoming", "scheduled", "reminders", "credit"] as BankTab[]
        ).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm border-b-2 whitespace-nowrap ${
              tab === t
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {t === "statements" && "Bank-dokument"}
            {t === "upcoming" && "Kommande"}
            {t === "scheduled" && "Schemalagda"}
            {t === "reminders" && "Påminnelser"}
            {t === "credit" && "EkonomiSkalan"}
          </button>
        ))}
      </div>
      {tab === "statements" && <StatementsTab />}
      {tab === "upcoming" && <UpcomingPaymentsTab />}
      {tab === "scheduled" && <ScheduledPaymentsTab />}
      {tab === "reminders" && <RemindersTab />}
      {tab === "credit" && <CreditScoreTab />}
    </div>
  );
}


// ---------- Påminnelser-flik ----------

interface ReminderRow {
  id: number;
  reminder_no: number;
  issued_date: string;
  late_fee: number;
  upcoming_name: string;
  fee_upcoming_id: number | null;
  settled_at: string | null;
}


function RemindersTab() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["bank-reminders"],
    queryFn: () =>
      api<{ reminders: ReminderRow[]; count: number }>("/bank/reminders"),
  });
  const runMut = useMutation({
    mutationFn: () =>
      api<{ triggered: number; checked_overdue: number }>(
        "/bank/reminders/run",
        { method: "POST" },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bank-reminders"] }),
  });

  if (q.isLoading) {
    return <Card><div className="text-sm text-slate-600">Laddar…</div></Card>;
  }
  const rows = q.data?.reminders ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-slate-500">
          Påminnelser triggas automatiskt när fakturor passerar
          förfallodag. Trycker du <strong>Kontrollera</strong> så
          eskaleras eventuella nya nivåer (1 → 2 → 3 → 4 'Kronofogden').
        </div>
        <button
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
          className="text-xs border border-slate-300 rounded px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
        >
          {runMut.isPending ? "Kollar…" : "Kontrollera"}
        </button>
      </div>
      {runMut.data && (
        <div className="text-xs text-slate-700 border-l-2 border-slate-300 pl-2">
          {runMut.data.triggered} ny(a) påminnelse(r) av{" "}
          {runMut.data.checked_overdue} kontrollerade fakturor.
        </div>
      )}
      {rows.length === 0 ? (
        <Card>
          <div className="text-sm text-slate-700">
            Inga påminnelser. Bra jobbat — du har betalat i tid.
          </div>
        </Card>
      ) : (
        <Card title={`Påminnelser (${rows.length})`}>
          <ul className="divide-y divide-slate-200 text-sm">
            {rows.map((r) => (
              <li key={r.id} className="py-2 flex items-center gap-3">
                <ReminderBadge level={r.reminder_no} />
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">
                    {r.upcoming_name}
                  </div>
                  <div className="text-xs text-slate-500">
                    {r.issued_date} · Påminnelseavgift {Math.round(r.late_fee)} kr
                    {r.fee_upcoming_id && (
                      <> · faktura {r.fee_upcoming_id} skapad</>
                    )}
                  </div>
                </div>
                {r.settled_at ? (
                  <span className="text-xs text-emerald-700">Betald</span>
                ) : (
                  <span className="text-xs text-rose-700">Obetald</span>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}


function ReminderBadge({ level }: { level: number }) {
  const tone =
    level >= 4 ? "bg-rose-700 text-white" :
    level >= 3 ? "bg-rose-100 text-rose-800" :
    level >= 2 ? "bg-amber-100 text-amber-800" :
    "bg-amber-50 text-amber-700";
  const label = level >= 4 ? "Inkasso" : `Påminnelse ${level}`;
  return (
    <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${tone}`}>
      {label}
    </span>
  );
}


// ---------- EkonomiSkalan-flik ----------

interface CreditScoreOut {
  score: number;
  grade: string;
  factors: Record<string, unknown>;
  reasons_md: string;
  computed_at: string;
}


function CreditScoreTab() {
  const q = useQuery({
    queryKey: ["bank-credit-score"],
    queryFn: () => api<CreditScoreOut>("/bank/credit-score"),
  });

  if (q.isLoading) {
    return <Card><div className="text-sm text-slate-600">Räknar fram score…</div></Card>;
  }
  if (q.error || !q.data) {
    return (
      <Card>
        <div className="text-sm text-rose-700">
          Kunde inte beräkna kreditbetyg: {String(q.error)}
        </div>
      </Card>
    );
  }
  const cs = q.data;
  const tone =
    cs.score >= 800 ? "border-emerald-400 bg-emerald-50" :
    cs.score >= 720 ? "border-emerald-300 bg-emerald-50/50" :
    cs.score >= 640 ? "border-slate-300 bg-slate-50" :
    cs.score >= 560 ? "border-amber-400 bg-amber-50" :
    "border-rose-400 bg-rose-50";

  return (
    <div className="space-y-3">
      <div className={`border-l-4 rounded-md p-4 ${tone}`}>
        <div className="text-xs uppercase tracking-wide text-slate-500">
          EkonomiSkalan
        </div>
        <div className="flex items-baseline gap-3 mt-1">
          <div className="text-5xl serif font-semibold">{cs.score}</div>
          <div className="text-base text-slate-600">/ 850 · grad {cs.grade}</div>
        </div>
        <div className="text-xs text-slate-500 mt-1">
          Beräknat {cs.computed_at}
        </div>
      </div>
      <Card title="Vad påverkar din score?">
        <div className="text-sm text-slate-800">
          <MarkdownLite text={cs.reasons_md} />
        </div>
      </Card>
      <Card title="Faktor-detaljer (rådata)">
        <pre className="text-xs text-slate-700 overflow-x-auto">
          {JSON.stringify(cs.factors, null, 2)}
        </pre>
      </Card>
    </div>
  );
}


/** Minimal markdown-renderare lokalt (inget beroende på @/components) */
function MarkdownLite({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("## ")) {
          return (
            <h3 key={i} className="text-base font-semibold mt-2">
              {line.slice(3)}
            </h3>
          );
        }
        if (line.startsWith("- ")) {
          // Hantera **bold** inline
          const inner = line.slice(2);
          return (
            <div key={i} className="text-sm flex gap-1.5">
              <span className="text-slate-400">•</span>
              <span dangerouslySetInnerHTML={{
                __html: inner.replace(
                  /\*\*([^*]+)\*\*/g,
                  "<strong>$1</strong>",
                ),
              }} />
            </div>
          );
        }
        return (
          <div
            key={i}
            className="text-sm"
            dangerouslySetInnerHTML={{
              __html: line.replace(
                /\*\*([^*]+)\*\*/g,
                "<strong>$1</strong>",
              ),
            }}
          />
        );
      })}
    </div>
  );
}


// ---------- Kontoutdrag-flik ----------

interface BankArtifact {
  artifact_id: number;
  batch_id: number;
  year_month: string;
  kind: string;
  title: string;
  filename: string;
  exported_to_my_batches: boolean;
  exported_at: string | null;
  imported_at: string | null;
}


function StatementsTab() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["bank-statements"],
    queryFn: () => api<BankArtifact[]>("/bank/statements"),
  });
  const exportMut = useMutation({
    mutationFn: (params: { batchId: number; artifactId: number }) =>
      api(
        `/bank/statements/${params.batchId}/${params.artifactId}/export`,
        { method: "POST" },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bank-statements"] }),
  });

  if (q.isLoading) {
    return <Card><div className="text-sm text-slate-600">Laddar…</div></Card>;
  }
  if (q.error) {
    return (
      <Card>
        <div className="text-sm text-rose-700">
          Kunde inte hämta dokument: {String(q.error)}
        </div>
      </Card>
    );
  }
  const arts = q.data ?? [];
  if (arts.length === 0) {
    return (
      <Card title="Inga dokument än">
        <div className="text-sm text-slate-700 leading-relaxed">
          Banken har inga kontoutdrag, kreditkortsfakturor eller
          lånebesked för dig än. När din lärare genererar månadens
          material syns dom här.
        </div>
      </Card>
    );
  }
  return (
    <Card title={`Dokument från banken (${arts.length})`}>
      <div className="text-xs text-slate-500 mb-3 leading-relaxed">
        Banken genererar tre typer av dokument åt dig: <strong>kontoutdrag</strong>{" "}
        (det som hänt på ditt konto), <strong>kreditkortsfakturor</strong> (det
        du ska betala till kortet) och <strong>lånebesked</strong>. Klicka{" "}
        <strong>Exportera</strong> så hamnar dokumentet i{" "}
        <a href="/my-batches" className="text-brand-700 underline">Dina
        dokument</a> — där bokar du in det i din ekonomi. Importerade
        kreditkortsfakturor dyker sedan upp i fliken <strong>Kommande</strong>{" "}
        för signering.
      </div>
      <ul className="divide-y divide-slate-200">
        {arts.map((a) => (
          <li
            key={a.artifact_id}
            className="py-2 flex items-center gap-3 text-sm"
          >
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate">
                {a.year_month} · {a.title}
              </div>
              <div className="text-xs text-slate-500 truncate">
                {a.filename} · {kindLabel(a.kind)}
              </div>
            </div>
            {a.exported_to_my_batches ? (
              <span className="text-xs text-emerald-700 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {a.imported_at ? "Importerad" : "Exporterad"}
              </span>
            ) : (
              <button
                onClick={() =>
                  exportMut.mutate({
                    batchId: a.batch_id,
                    artifactId: a.artifact_id,
                  })
                }
                disabled={exportMut.isPending}
                className="text-xs bg-brand-600 text-white rounded px-3 py-1 hover:bg-brand-700 disabled:opacity-50"
              >
                Exportera
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-3 text-[11px] text-slate-500">
        Efter export: gå till <a href="/my-batches" className="text-brand-700 underline">Dina dokument</a> för att importera till bokföringen.
      </div>
    </Card>
  );
}


function kindLabel(kind: string): string {
  switch (kind) {
    case "kontoutdrag": return "Kontoutdrag";
    case "kreditkort_faktura": return "Kreditkortsfaktura";
    case "lan_besked": return "Lånebesked";
    default: return kind;
  }
}


// ---------- Kommande betalningar ----------

interface UpcomingPaymentRow {
  upcoming_id: number;
  name: string;
  amount: number;
  expected_date: string;
  debit_account_id: number | null;
  already_signed: boolean;
  scheduled_payment_id: number | null;
  scheduled_status: string | null;
  scheduled_date: string | null;
}


interface AccountOut {
  id: number;
  name: string;
  type: string;
}


function UpcomingPaymentsTab() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["bank-upcoming"],
    queryFn: () => api<UpcomingPaymentRow[]>("/bank/upcoming-payments"),
  });
  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<AccountOut[]>("/accounts"),
  });
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [accountId, setAccountId] = useState<number | null>(null);

  // Default-konto: första checking
  useEffect(() => {
    if (accountId === null && accountsQ.data) {
      const checking = accountsQ.data.find((a) => a.type === "checking");
      if (checking) setAccountId(checking.id);
    }
  }, [accountsQ.data, accountId]);

  const [signing, setSigning] = useState(false);
  const [signError, setSignError] = useState<string | null>(null);

  const initSign = useMutation({
    mutationFn: () =>
      api<InitSessionOut>("/bank/session/init", {
        method: "POST",
        body: JSON.stringify({
          purpose: `sign_payment_batch:${[...selectedIds].join(",")}`,
        }),
      }),
  });

  async function signSelected() {
    // Validera payload INNAN session-init startas — annars hinner
    // användaren bekräfta i mobilen för en signering som ändå kraschar
    // med 422 från backend.
    if (selectedIds.size === 0) {
      setSignError("Välj minst en faktura att signera.");
      return;
    }
    if (accountId === null || accountId <= 0) {
      setSignError(
        "Inget lönekonto valt — kolla att du har ett checking-konto i din bokföring.",
      );
      return;
    }
    setSigning(true);
    setSignError(null);
    try {
      // 1. Init BankID-session — eleven måste bekräfta i annan tab
      const sess = await initSign.mutateAsync();
      // 2. Polla tills bekräftad (60 sek timeout)
      const start = Date.now();
      let confirmed = false;
      while (Date.now() - start < 60_000) {
        await new Promise((r) => setTimeout(r, 2000));
        const status = await api<SessionStatusOut>(
          `/bank/session/${sess.token}`,
        );
        if (status.confirmed) {
          confirmed = true;
          break;
        }
        if (status.expired) {
          throw new Error("EkonomilabbetID-sessionen löpte ut");
        }
      }
      if (!confirmed) {
        // Visa länken direkt så eleven kan öppna manuellt och bekräfta
        const url = `${window.location.origin}${sess.qr_url}`;
        throw new Error(
          `Du behövde bekräfta i mobilen — öppna ${url} i ny tab och försök igen.`,
        );
      }
      // 3. Signera batchen
      await api("/bank/upcoming-payments/sign", {
        method: "POST",
        body: JSON.stringify({
          upcoming_ids: [...selectedIds],
          account_id: accountId,
          bank_session_token: sess.token,
        }),
      });
      setSelectedIds(new Set());
      qc.invalidateQueries({ queryKey: ["bank-upcoming"] });
    } catch (e) {
      setSignError(e instanceof Error ? e.message : String(e));
    } finally {
      setSigning(false);
    }
  }

  if (q.isLoading) {
    return <Card><div className="text-sm text-slate-600">Laddar…</div></Card>;
  }
  const rows = q.data ?? [];
  const unsignedRows = rows.filter((r) => !r.already_signed);

  if (unsignedRows.length === 0 && rows.length === 0) {
    return (
      <Card title="Inga obetalda fakturor">
        <div className="text-sm text-slate-700 leading-relaxed">
          Inga fakturor väntar på signering just nu. Fakturor hamnar här när
          du importerat en <strong>kreditkortsfaktura</strong> eller liknande
          från <a href="/my-batches" className="text-brand-700 underline">Dina
          dokument</a> till din bokföring — då skapas en kommande betalning
          som ska signeras med EkonomilabbetID innan förfallodag.
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {unsignedRows.length > 0 && (
        <Card title={`Att signera (${unsignedRows.length})`}>
          <div className="text-xs text-slate-500 mb-3">
            Markera fakturor du vill betala. När du signerar med
            EkonomilabbetID schemaläggs de — pengarna dras från valt konto
            på förfallodagen om saldot räcker.
          </div>
          <ul className="divide-y divide-slate-200 mb-3">
            {unsignedRows.map((r) => (
              <li
                key={r.upcoming_id}
                className="py-2 flex items-center gap-3 text-sm"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.has(r.upcoming_id)}
                  onChange={(e) => {
                    const next = new Set(selectedIds);
                    if (e.target.checked) next.add(r.upcoming_id);
                    else next.delete(r.upcoming_id);
                    setSelectedIds(next);
                  }}
                />
                <div className="flex-1 min-w-0">
                  <div className="truncate">{r.name}</div>
                  <div className="text-xs text-slate-500">
                    Förfallodag {r.expected_date}
                  </div>
                </div>
                <div className="text-right tabular-nums">
                  {Math.round(r.amount).toLocaleString("sv-SE")} kr
                </div>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={accountId ?? ""}
              onChange={(e) => setAccountId(parseInt(e.target.value, 10))}
              className="border rounded px-2 py-1.5 text-sm"
            >
              <option value="" disabled>Välj konto</option>
              {(accountsQ.data ?? [])
                .filter((a) => a.type === "checking")
                .map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
            </select>
            <button
              onClick={signSelected}
              disabled={
                signing ||
                selectedIds.size === 0 ||
                accountId === null
              }
              className="bg-brand-600 text-white rounded px-4 py-1.5 text-sm flex items-center gap-2 disabled:opacity-50"
            >
              {signing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
              {signing ? "Signerar med EkonomilabbetID…" : `Signera ${selectedIds.size} st`}
            </button>
            {signError && (
              <div className="text-sm text-rose-700 w-full">
                {signError}
              </div>
            )}
          </div>
        </Card>
      )}
      {rows.filter((r) => r.already_signed).length > 0 && (
        <Card title="Schemalagda — väntar på förfallodag">
          <div className="text-xs text-slate-500 mb-3">
            Du har signerat dessa betalningar med EkonomilabbetID. De
            kommer dras automatiskt på respektive förfallodag (om
            saldot räcker). Försvinner från listan när de körts.
          </div>
          <ul className="divide-y divide-slate-200 text-sm">
            {rows.filter((r) => r.already_signed).map((r) => (
              <li
                key={r.upcoming_id}
                className="py-2 flex items-center gap-3"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <div className="flex-1">
                  <div className="font-medium">{r.name}</div>
                  <div className="text-xs text-slate-500">
                    Dras {r.scheduled_date} · status {r.scheduled_status}
                  </div>
                </div>
                <div className="tabular-nums">
                  {Math.round(r.amount).toLocaleString("sv-SE")} kr
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}


// ---------- Schemalagda betalningar ----------

interface ScheduledPaymentRow {
  id: number;
  upcoming_id: number;
  name: string;
  account_id: number;
  amount: number;
  scheduled_date: string;
  status: string;
  executed_at: string | null;
  failure_reason: string | null;
}


function ScheduledPaymentsTab() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["bank-scheduled"],
    queryFn: () =>
      api<{ scheduled_payments: ScheduledPaymentRow[]; count: number }>(
        "/bank/scheduled-payments",
      ),
  });
  const runMut = useMutation({
    mutationFn: () =>
      api<{ executed: number; failed: number; due_count: number }>(
        "/bank/scheduled-payments/run-due",
        { method: "POST" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bank-scheduled"] });
      qc.invalidateQueries({ queryKey: ["bank-upcoming"] });
    },
  });

  if (q.isLoading) {
    return <Card><div className="text-sm text-slate-600">Laddar…</div></Card>;
  }
  const rows = q.data?.scheduled_payments ?? [];
  if (rows.length === 0) {
    return (
      <Card title="Inga schemalagda betalningar">
        <div className="text-sm text-slate-700">
          När du signerar fakturor i fliken <em>Kommande</em> hamnar de
          här i kö tills förfallodagen kommer.
        </div>
      </Card>
    );
  }
  return (
    <Card title={`Schemalagda betalningar (${rows.length})`}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs text-slate-500">
          Banken kör betalningar dagligen. Tryck här om du vill
          köra körningen direkt (för demo).
        </div>
        <button
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
          className="text-xs border border-slate-300 rounded px-2 py-1 hover:bg-slate-50 disabled:opacity-50"
        >
          {runMut.isPending ? "Kör…" : "Kör nu"}
        </button>
      </div>
      {runMut.data && (
        <div className="text-xs text-slate-700 mb-2 border-l-2 border-slate-300 pl-2">
          Kördes: {runMut.data.executed} utförda, {runMut.data.failed} misslyckade,{" "}
          {runMut.data.due_count} totalt på dagen.
        </div>
      )}
      <ul className="divide-y divide-slate-200 text-sm">
        {rows.map((r) => (
          <li key={r.id} className="py-2 flex items-center gap-3">
            <StatusDot status={r.status} />
            <div className="flex-1 min-w-0">
              <div className="truncate font-medium">{r.name}</div>
              <div className="text-xs text-slate-500">
                {r.scheduled_date} · {r.status}
                {r.failure_reason && (
                  <> · <span className="text-rose-700">{r.failure_reason}</span></>
                )}
              </div>
            </div>
            <div className="tabular-nums">
              {Math.round(r.amount).toLocaleString("sv-SE")} kr
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}


function StatusDot({ status }: { status: string }) {
  const tone =
    status === "executed" ? "bg-emerald-500" :
    status === "failed_no_funds" ? "bg-rose-500" :
    status === "scheduled" ? "bg-amber-500" :
    "bg-slate-400";
  return <span className={`inline-block w-2 h-2 rounded-full ${tone}`} />;
}
