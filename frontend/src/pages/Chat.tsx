import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/Card";
import { Send } from "lucide-react";

interface Msg { role: string; content: string; created_at: string }

function newSessionId(): string {
  return crypto.randomUUID().slice(0, 12);
}

export default function Chat() {
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

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historyQ.data, sendMut.isPending]);

  const msgs = (historyQ.data?.messages ?? []).filter((m) => m.role !== "system");

  return (
    <div className="p-6 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">AI-chatt</h1>
        <div className="text-sm">
          <span
            className={`inline-block w-2 h-2 rounded-full mr-1.5 ${
              statusQ.data?.alive ? "bg-emerald-500" : "bg-rose-500"
            }`}
          />
          LM Studio: {statusQ.data?.alive ? "aktiv" : "frånkopplad"} · {statusQ.data?.model}
        </div>
      </div>

      <Card className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto space-y-3 pr-2">
          {msgs.length === 0 && (
            <div className="text-sm text-slate-500">
              Fråga om din ekonomi. Exempel:
              <ul className="list-disc ml-5 mt-2 space-y-1 text-slate-600">
                <li>"Vad spenderade vi mest på förra månaden?"</li>
                <li>"Vilka prenumerationer betalar jag?"</li>
                <li>"Om vi köper hus för 5M med 4 % ränta — vad blir månadskostnaden?"</li>
              </ul>
            </div>
          )}
          {msgs.map((m, i) => (
            <div
              key={i}
              className={`max-w-3xl rounded-lg p-3 text-sm ${
                m.role === "user"
                  ? "ml-auto bg-brand-600 text-white"
                  : m.role === "tool"
                  ? "bg-slate-100 text-slate-500 font-mono text-xs"
                  : "bg-slate-50 border border-slate-200"
              }`}
            >
              <div className="whitespace-pre-wrap">{m.content}</div>
            </div>
          ))}
          {sendMut.isPending && (
            <div className="text-sm text-slate-400">Nemotron funderar…</div>
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
          <button className="bg-brand-600 text-white rounded-lg px-4 flex items-center gap-1.5">
            <Send className="w-4 h-4" /> Skicka
          </button>
        </form>
      </Card>
    </div>
  );
}
