/**
 * /bank — Ekonomilabbets bank (idé 3 i dev_v1.md).
 *
 * Tre lägen:
 *  1. PIN-onboarding (om has_pin=false): eleven sätter 4-siffrig PIN
 *  2. Inloggning: QR + polla session tills bekräftad
 *  3. Inloggad: dashboard (kontoutdrag, kommande betalningar, lån)
 *
 * BankID-simulering: vi visar hur flödet funkar i verkligheten.
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

  // Sign-vy (mobilen) — eleven matar PIN för en specifik token
  if (isSignView && signToken) {
    return (
      <BankShell mobile>
        <SignConfirmView token={signToken} />
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
          {mobile ? "Mobil-bekräftelse" : "BankID-simulering"}
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
          Tryck på knappen nedan för att starta en BankID-session.
          En QR-kod visas — skanna den med din mobil och bekräfta
          med din PIN.
        </div>
        <button
          onClick={() => initMut.mutate()}
          disabled={initMut.isPending}
          className="bg-brand-600 text-white rounded px-4 py-2 flex items-center gap-2 disabled:opacity-50"
        >
          <Lock className="w-4 h-4" />
          {initMut.isPending ? "Startar…" : "Starta BankID"}
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
          Din BankID-session var öppen i 15 minuter. Du behöver
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
  // Riktig QR-rendering kräver beroende — i Ekonomilabbet räcker en
  // grafisk placeholder med URL:en under, eftersom QR är pedagogisk
  // metafor inte säkerhetskritisk.
  return (
    <div className="border-4 border-slate-900 rounded p-3 bg-white aspect-square flex flex-col items-center justify-center">
      <div className="text-[8px] text-slate-400 mb-1">QR-kod</div>
      <div className="grid grid-cols-8 gap-0.5">
        {/* Gör en pseudo-pattern från URL:ens hash så samma URL ger
            samma "kod" — pedagogiskt nog för att förstå konceptet */}
        {Array.from({ length: 64 }).map((_, i) => {
          const on = (url.charCodeAt(i % url.length) + i) % 3 === 0;
          return (
            <div
              key={i}
              className={`w-2 h-2 ${on ? "bg-slate-900" : "bg-white"}`}
            />
          );
        })}
      </div>
      <div className="text-[8px] text-slate-400 mt-1 truncate w-full text-center">
        {url.slice(-12)}
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


function BankDashboard() {
  return (
    <Card title="Du är inloggad i banken">
      <div className="flex items-start gap-3 mb-4">
        <ShieldCheck className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-slate-700 leading-relaxed">
          BankID-simuleringen är klar. I de följande commits (PR 6/7)
          får denna vy:
          <ul className="list-disc ml-5 mt-1 space-y-0.5 text-slate-600">
            <li>Kontoutdrag (export → /my-batches → /transactions)</li>
            <li>Kommande betalningar (signering med BankID)</li>
            <li>Sena betalningar + påminnelser</li>
            <li>Kreditbedömning (EkonomiSkalan)</li>
            <li>Låneansökan</li>
          </ul>
        </div>
      </div>
      <div className="text-xs text-slate-500">
        Sessionen är giltig i 15 minuter. Logga ut genom att stänga
        fliken.
      </div>
    </Card>
  );
}
