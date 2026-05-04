import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/Card";
import { useAuth } from "@/hooks/useAuth";
import { Bot, ChevronDown, ChevronRight, Lock, Send, Wrench } from "lucide-react";

interface ToolCallMeta {
  tool_calls?: Array<{
    id?: string;
    type?: string;
    function?: { name: string; arguments: string };
  }>;
  // tool-role meddelanden sparar vi i format { name, arguments, tool_call_id }
  name?: string;
  arguments?: Record<string, unknown>;
  tool_call_id?: string;
}

interface Msg {
  role: string;
  content: string;
  created_at: string;
  tool_calls?: ToolCallMeta | null;
}

function newSessionId(): string {
  return crypto.randomUUID().slice(0, 12);
}

function formatArgs(args: Record<string, unknown> | undefined): string {
  if (!args || Object.keys(args).length === 0) return "";
  return Object.entries(args)
    .map(([k, v]) => {
      if (typeof v === "string") return `${k}="${v}"`;
      if (v === null || v === undefined) return `${k}=null`;
      if (typeof v === "object") return `${k}=…`;
      return `${k}=${v}`;
    })
    .join(", ");
}

function ToolChips({ calls }: { calls: ToolCallMeta["tool_calls"] }) {
  if (!calls || calls.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 mb-2">
      {calls.map((tc, i) => {
        const name = tc.function?.name ?? "unknown";
        let args: Record<string, unknown> = {};
        try {
          args = tc.function?.arguments ? JSON.parse(tc.function.arguments) : {};
        } catch {
          /* ignore */
        }
        const argStr = formatArgs(args);
        return (
          <span
            key={i}
            className="inline-flex items-center gap-1 bg-indigo-50 text-indigo-700 text-xs font-mono px-2 py-1 rounded border border-indigo-200"
            title={argStr}
          >
            <Wrench className="w-3 h-3" />
            {name}
            {argStr && <span className="text-indigo-500">({argStr})</span>}
          </span>
        );
      })}
    </div>
  );
}

function ToolResultBubble({ msg }: { msg: Msg }) {
  const [open, setOpen] = useState(false);
  const name = msg.tool_calls?.name ?? "tool";
  const args = msg.tool_calls?.arguments;
  const argStr = args ? formatArgs(args) : "";

  // Parsar svaret för en tät sammanfattning
  let summary = "";
  try {
    const parsed = JSON.parse(msg.content);
    if (parsed.error) {
      summary = `fel: ${parsed.error}`;
    } else if (Array.isArray(parsed.transactions)) {
      summary = `${parsed.transactions.length} transaktioner`;
    } else if (Array.isArray(parsed.items)) {
      summary = `${parsed.items.length} poster`;
    } else if (Array.isArray(parsed.accounts)) {
      summary = `${parsed.accounts.length} konton, totalt ${parsed.total_balance?.toLocaleString("sv-SE") ?? "?"} kr`;
    } else if (Array.isArray(parsed.loans)) {
      summary = `${parsed.loans.length} lån`;
    } else if (Array.isArray(parsed.top)) {
      summary = `${parsed.top.length} kategorier`;
    } else if (Array.isArray(parsed.forecast)) {
      summary = `${parsed.forecast.length} månader prognos`;
    } else if (Array.isArray(parsed.anomalies)) {
      summary = `${parsed.anomalies.length} avvikelser`;
    } else if (Array.isArray(parsed.months)) {
      summary = `${parsed.months.length} månader`;
    } else if (parsed.month) {
      summary = `månad ${parsed.month}`;
    } else {
      const keys = Object.keys(parsed);
      summary = keys.length ? `${keys.length} fält` : "(tomt)";
    }
  } catch {
    summary = "(ej JSON)";
  }

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Wrench className="w-3 h-3" />
        <span className="font-mono font-medium text-slate-700">{name}</span>
        {argStr && <span className="font-mono text-slate-600">({argStr})</span>}
        <span className="text-slate-700 ml-auto">→ {summary}</span>
      </button>
      {open && (
        <pre className="px-3 py-2 text-slate-700 font-mono overflow-x-auto max-h-64 overflow-y-auto border-t border-slate-200 whitespace-pre-wrap break-all">
          {(() => {
            try {
              return JSON.stringify(JSON.parse(msg.content), null, 2);
            } catch {
              return msg.content;
            }
          })()}
        </pre>
      )}
    </div>
  );
}

const EXAMPLE_QUESTIONS = [
  "Vad spenderade vi mest på förra månaden?",
  "Jämför mars och april — vilken kategori gick upp mest?",
  "Finns det några avvikelser i min ekonomi just nu?",
  "Vilka fakturor kommer nästa månad?",
  "Hur mycket har jag kvar på bolånet och vad har jag betalat i ränta i år?",
  "Vilka prenumerationer betalar jag?",
  "Vem betalade mest i familjen förra månaden?",
];

export default function Chat() {
  const { schoolMode } = useAuth();
  if (schoolMode) return <SchoolChat />;
  return <DesktopChat />;
}


// ---------- School-mode AI-chatt: extern Claude + rate-limit ----------

interface ChatStatus {
  ai_enabled: boolean;
  available: boolean;
  daily_quota: number;
  used_today: number;
  remaining_today: number;
  role: string;
}

interface ChatMsg {
  role: string;
  content: string;
  created_at: string;
}

const SCHOOL_EXAMPLES = [
  "Vad är en sparkvot och hur räknar jag ut den?",
  "Hur funkar ISK-skatten egentligen?",
  "Vad är skillnaden mellan ränta och avgift på ett lån?",
  "Hur tänker man kring att spara vs betala av lån?",
];


function SchoolChat() {
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const statusQ = useQuery({
    queryKey: ["chat-status"],
    queryFn: () => api<ChatStatus>("/ai/chat/status"),
    refetchInterval: 30_000,
  });

  const messagesQ = useQuery({
    queryKey: ["chat-messages"],
    queryFn: () => api<{ messages: ChatMsg[]; thread_id: number }>(
      "/ai/chat/messages",
    ),
    enabled: !!statusQ.data?.ai_enabled,
  });

  const sendMut = useMutation({
    mutationFn: (content: string) =>
      api<{ answer: string; used_today: number; remaining_today: number }>(
        "/ai/chat/send",
        { method: "POST", body: JSON.stringify({ content }) },
      ),
    onSuccess: () => {
      messagesQ.refetch();
      statusQ.refetch();
    },
  });

  const clearMut = useMutation({
    mutationFn: () =>
      api<{ deleted: number }>("/ai/chat/messages", { method: "DELETE" }),
    onSuccess: () => messagesQ.refetch(),
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messagesQ.data, sendMut.isPending]);

  const status = statusQ.data;
  const msgs = messagesQ.data?.messages ?? [];
  const isTeacher = status?.role === "teacher";

  // Inte aktiverat → visa låsbild (ingen klickbar kontroll).
  if (status && !status.ai_enabled) {
    return (
      <div className="p-4 md:p-6 max-w-3xl mx-auto">
        <h1 className="serif text-3xl leading-tight mb-4 flex items-center gap-2">
          <Bot className="w-7 h-7" /> AI-chatt
        </h1>
        <Card>
          <div className="flex items-start gap-3">
            <Lock className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-slate-800 mb-1">
                Ej aktiverat
              </div>
              <div className="text-sm text-slate-600 leading-relaxed">
                AI-chatten är inte påslagen för{" "}
                {isTeacher ? "ditt lärarkonto" : "din klass"}.
                {isTeacher
                  ? " Be super-admin att aktivera AI-funktioner under /admin/ai."
                  : " Be din lärare att slå på den."}
              </div>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  // Kvot 0 → aktiverat men avstängt för chatten specifikt
  if (status && status.daily_quota === 0) {
    return (
      <div className="p-4 md:p-6 max-w-3xl mx-auto">
        <h1 className="serif text-3xl leading-tight mb-4 flex items-center gap-2">
          <Bot className="w-7 h-7" /> AI-chatt
        </h1>
        <Card>
          <div className="text-sm text-slate-700">
            AI-chatten är inte aktiv just nu — dagskvoten är satt till 0.
            {isTeacher
              ? " Höj värdet under /admin/ai för att slå på."
              : " Be din lärare att höja dagskvoten."}
          </div>
        </Card>
      </div>
    );
  }

  const remaining = status?.remaining_today ?? 0;
  const limit = status?.daily_quota ?? 0;
  const used = status?.used_today ?? 0;
  const sendDisabled = sendMut.isPending || remaining <= 0;

  return (
    <div className="p-4 md:p-6 flex flex-col h-full max-w-3xl mx-auto w-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="serif text-3xl leading-tight flex items-center gap-2">
          <Bot className="w-7 h-7" /> AI-chatt
        </h1>
        <div className="flex items-center gap-3 text-sm">
          {msgs.length > 0 && (
            <button
              onClick={() => {
                if (confirm("Rensa hela chatten? Går inte att ångra.")) {
                  clearMut.mutate();
                }
              }}
              disabled={clearMut.isPending}
              className="px-2.5 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-rose-50 hover:border-rose-300 hover:text-rose-700 text-xs disabled:opacity-50"
            >
              {clearMut.isPending ? "Rensar…" : "Rensa chatt"}
            </button>
          )}
          <div
            className={`text-xs px-2 py-1 rounded ${
              remaining <= 2
                ? "bg-amber-100 text-amber-800"
                : "bg-slate-100 text-slate-700"
            }`}
            title={isTeacher
              ? "Lärare får 3× elevkvoten för testning"
              : "Antal frågor du har kvar idag"}
          >
            {remaining} av {limit} kvar idag
          </div>
        </div>
      </div>

      <Card className="flex-1 flex flex-col min-h-[420px]">
        <div className="flex-1 overflow-y-auto space-y-3 pr-2">
          {msgs.length === 0 && (
            <div className="text-sm text-slate-700">
              <div className="mb-3">
                Fråga om personlig ekonomi — budget, lön, skatt, lån, sparande,
                investeringar. Modellen ser inte din egen data, så för
                personliga siffror titta i Dashboard eller Kontoutdrag.
              </div>
              <div className="space-y-1.5">
                {SCHOOL_EXAMPLES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => !sendDisabled && sendMut.mutate(q)}
                    disabled={sendDisabled}
                    className="block text-left w-full px-3 py-1.5 rounded border border-slate-200 hover:border-brand-400 hover:bg-paper text-slate-700 transition disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => {
            if (m.role === "user") {
              return (
                <div
                  key={i}
                  className="max-w-2xl rounded-lg p-3 text-sm ml-auto bg-brand-600 text-white"
                >
                  <div className="whitespace-pre-wrap">{m.content}</div>
                </div>
              );
            }
            return (
              <div
                key={i}
                className="max-w-2xl rounded-lg p-3 text-sm bg-slate-50 border border-slate-200"
              >
                <div className="whitespace-pre-wrap">{m.content}</div>
              </div>
            );
          })}
          {sendMut.isPending && (
            <div className="text-sm text-slate-600">Claude funderar…</div>
          )}
          {sendMut.error && (
            <div className="text-sm text-rose-700 border-l-2 border-rose-400 pl-2">
              {(sendMut.error as Error).message}
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!input.trim() || sendDisabled) return;
            sendMut.mutate(input);
            setInput("");
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              remaining <= 0
                ? "Dagskvoten är slut — försök igen i morgon"
                : "Skriv en fråga…"
            }
            disabled={sendDisabled}
            className="flex-1 border rounded-lg px-3 py-2 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={sendDisabled || !input.trim()}
            className="bg-brand-600 text-white rounded-lg px-4 flex items-center gap-1.5 disabled:opacity-50"
          >
            <Send className="w-4 h-4" /> Skicka
          </button>
        </form>
      </Card>
      <div className="text-[10px] text-slate-500 mt-2 leading-snug">
        Du har {used} fråga{used === 1 ? "" : "or"} idag av maxgränsen{" "}
        {limit}. {isTeacher
          ? "Som lärare har du 3× elevkvoten."
          : "Be din lärare höja kvoten om du behöver fler."}
      </div>
    </div>
  );
}


// ---------- Desktop-chat: lokal LM Studio (Nemotron) ----------

function DesktopChat() {
  const [sessionId] = useState(() => {
    const s = sessionStorage.getItem("chat_session");
    if (s) return s;
    const id = newSessionId();
    sessionStorage.setItem("chat_session", id);
    return id;
  });
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const statusQ = useQuery({
    queryKey: ["lm-status"],
    queryFn: () => api<{ alive: boolean; base_url: string; model: string }>("/chat/lm-studio-status"),
    refetchInterval: 30000,
  });

  const historyQ = useQuery({
    queryKey: ["chat-history", sessionId],
    queryFn: () => api<{ messages: Msg[] }>(`/chat/history/${sessionId}`),
  });

  const sendMut = useMutation({
    mutationFn: (content: string) =>
      api<{ answer: string }>("/chat/send", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, content }),
      }),
    onSuccess: () => historyQ.refetch(),
  });

  const clearMut = useMutation({
    mutationFn: () =>
      api<{ deleted: number }>(`/chat/history/${sessionId}`, {
        method: "DELETE",
      }),
    onSuccess: () => historyQ.refetch(),
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historyQ.data, sendMut.isPending]);

  const msgs = (historyQ.data?.messages ?? []).filter((m) => m.role !== "system");

  return (
    <div className="p-6 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="serif text-3xl leading-tight">AI-chatt</h1>
        <div className="flex items-center gap-3 text-sm">
          {msgs.length > 0 && (
            <button
              onClick={() => {
                if (confirm("Rensa hela chat-historiken? Går inte att ångra.")) {
                  clearMut.mutate();
                }
              }}
              disabled={clearMut.isPending}
              className="px-2.5 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-rose-50 hover:border-rose-300 hover:text-rose-700 text-xs disabled:opacity-50"
              title="Ta bort alla meddelanden i denna session"
            >
              {clearMut.isPending ? "Rensar…" : "Rensa chatt"}
            </button>
          )}
          <div>
            <span
              className={`inline-block w-2 h-2 rounded-full mr-1.5 ${
                statusQ.data?.alive ? "bg-emerald-500" : "bg-rose-500"
              }`}
            />
            LM Studio: {statusQ.data?.alive ? "aktiv" : "frånkopplad"} · {statusQ.data?.model}
          </div>
        </div>
      </div>

      <Card className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto space-y-3 pr-2">
          {msgs.length === 0 && (
            <div className="text-sm text-slate-700">
              <div className="mb-3">
                Fråga om din ekonomi. Nemotron har tillgång till 21 verktyg
                och kan svara om konton, saldo, lån, fakturor, prenumerationer,
                skatter, regler och trender.
              </div>
              <div className="space-y-1.5">
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => sendMut.mutate(q)}
                    className="block text-left w-full px-3 py-1.5 rounded border border-slate-200 hover:border-brand-400 hover:bg-paper text-slate-700 transition"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => {
            if (m.role === "tool") {
              return (
                <div key={i} className="max-w-3xl">
                  <ToolResultBubble msg={m} />
                </div>
              );
            }
            if (m.role === "user") {
              return (
                <div
                  key={i}
                  className="max-w-3xl rounded-lg p-3 text-sm ml-auto bg-brand-600 text-white"
                >
                  <div className="whitespace-pre-wrap">{m.content}</div>
                </div>
              );
            }
            // assistant
            const calls = m.tool_calls?.tool_calls;
            return (
              <div
                key={i}
                className="max-w-3xl rounded-lg p-3 text-sm bg-slate-50 border border-slate-200"
              >
                {calls && calls.length > 0 && <ToolChips calls={calls} />}
                {m.content && (
                  <div className="whitespace-pre-wrap">{m.content}</div>
                )}
                {!m.content && (!calls || calls.length === 0) && (
                  <div className="text-slate-600 italic">(tomt svar)</div>
                )}
              </div>
            );
          })}
          {sendMut.isPending && (
            <div className="text-sm text-slate-600">Nemotron funderar…</div>
          )}
          <div ref={endRef} />
        </div>

        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!input.trim()) return;
            sendMut.mutate(input);
            setInput("");
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Skriv en fråga…"
            className="flex-1 border rounded-lg px-3 py-2"
          />
          <button
            className="bg-brand-600 text-white rounded-lg px-4 flex items-center gap-1.5 disabled:opacity-50"
            disabled={sendMut.isPending}
          >
            <Send className="w-4 h-4" /> Skicka
          </button>
        </form>
      </Card>
    </div>
  );
}
