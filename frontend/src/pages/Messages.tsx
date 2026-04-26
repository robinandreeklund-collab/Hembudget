import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, MessageCircle, Send } from "lucide-react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";

type Message = {
  id: number;
  student_id: number;
  teacher_id: number;
  sender_role: "student" | "teacher";
  body: string;
  created_at: string;
  read_at: string | null;
};

type Thread = {
  student_id: number;
  display_name: string;
  class_label: string | null;
  last_message_at: string | null;
  last_message_preview: string | null;
  unread_count: number;
};

export default function Messages() {
  const { role } = useAuth();
  const isTeacher = role === "teacher";
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeStudent, setActiveStudent] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMessage, setNewMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  async function loadThreads() {
    if (!isTeacher) return;
    try {
      const ts = await api<Thread[]>("/teacher/messages/threads");
      setThreads(ts);
      if (ts.length > 0 && activeStudent === null) {
        setActiveStudent(ts[0].student_id);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function loadMessages() {
    try {
      const path = isTeacher
        ? `/teacher/messages/threads/${activeStudent}`
        : "/student/messages";
      const ms = await api<Message[]>(path);
      setMessages(ms);
      setTimeout(() => {
        scrollRef.current?.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: "smooth",
        });
      }, 50);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    if (isTeacher) loadThreads();
    else loadMessages();
  }, []);

  useEffect(() => {
    if (isTeacher && activeStudent !== null) loadMessages();
  }, [activeStudent]);

  async function send() {
    const body = newMessage.trim();
    if (!body) return;
    setSending(true);
    try {
      if (isTeacher) {
        if (!activeStudent) return;
        await api(`/teacher/messages/threads/${activeStudent}`, {
          method: "POST",
          body: JSON.stringify({ body }),
        });
      } else {
        await api("/student/messages", {
          method: "POST",
          body: JSON.stringify({ body }),
        });
      }
      setNewMessage("");
      await loadMessages();
      if (isTeacher) await loadThreads();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  const activeThread = threads.find((t) => t.student_id === activeStudent);

  return (
    <div className={`${isTeacher ? "h-[calc(100vh-3rem)] md:h-screen" : "p-6"}`}>
      {!isTeacher && (
        <div className="max-w-3xl mx-auto space-y-4">
          <div className="flex items-center gap-2">
            <MessageCircle className="w-6 h-6 text-brand-600" />
            <h1 className="serif text-3xl leading-tight">Meddela din lärare</h1>
          </div>
          <p className="text-sm text-slate-600">
            Ställ en fråga, be om hjälp eller ge feedback. Din lärare svarar
            här när hen har tittat på det.
          </p>
        </div>
      )}
      <div
        className={
          isTeacher
            ? "grid grid-cols-1 md:grid-cols-[300px_1fr] h-full"
            : "max-w-3xl mx-auto mt-4"
        }
      >
        {isTeacher && (
          <aside className="border-r bg-slate-50 overflow-y-auto">
            <div className="p-3 border-b bg-white sticky top-0">
              <Link
                to="/teacher"
                className="text-sm text-slate-600 hover:text-ink flex items-center gap-1"
              >
                <ArrowLeft className="w-4 h-4" /> Lärarpanel
              </Link>
              <h2 className="font-semibold mt-1">Konversationer</h2>
            </div>
            {threads.length === 0 ? (
              <div className="p-4 text-sm text-slate-500">
                Inga konversationer än.
              </div>
            ) : (
              <ul>
                {threads.map((t) => (
                  <li key={t.student_id}>
                    <button
                      onClick={() => setActiveStudent(t.student_id)}
                      className={`w-full text-left p-3 border-b hover:bg-white ${
                        activeStudent === t.student_id
                          ? "bg-white border-l-4 border-l-brand-500"
                          : ""
                      }`}
                    >
                      <div className="flex justify-between">
                        <span className="font-medium">{t.display_name}</span>
                        {t.unread_count > 0 && (
                          <span className="text-xs bg-rose-500 text-white rounded-full w-5 h-5 flex items-center justify-center">
                            {t.unread_count}
                          </span>
                        )}
                      </div>
                      {t.last_message_preview && (
                        <div className="text-xs text-slate-500 truncate">
                          {t.last_message_preview}
                        </div>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        )}

        <main className="flex flex-col overflow-hidden">
          {isTeacher && activeThread && (
            <div className="border-b px-4 py-2 bg-white">
              <h2 className="font-semibold">
                {activeThread.display_name}
                {activeThread.class_label && (
                  <span className="text-slate-500 text-sm ml-2">
                    {activeThread.class_label}
                  </span>
                )}
              </h2>
            </div>
          )}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
            {err && (
              <div className="text-sm text-rose-700 bg-rose-50 rounded p-2">
                {err}
              </div>
            )}
            {messages.length === 0 ? (
              <div className="text-sm text-slate-500 text-center py-10">
                {isTeacher
                  ? "Inga meddelanden än. Skriv ett till eleven nedan."
                  : "Inga meddelanden. Ställ din första fråga nedan!"}
              </div>
            ) : (
              messages.map((m) => {
                const mine = (isTeacher && m.sender_role === "teacher") ||
                  (!isTeacher && m.sender_role === "student");
                return (
                  <div
                    key={m.id}
                    className={`flex ${mine ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-md rounded-lg p-3 text-sm ${
                        mine
                          ? "bg-brand-600 text-white"
                          : "bg-slate-100 text-slate-900"
                      }`}
                    >
                      <div className="whitespace-pre-wrap">{m.body}</div>
                      <div
                        className={`text-xs mt-1 ${
                          mine ? "text-brand-100" : "text-slate-500"
                        }`}
                      >
                        {new Date(m.created_at).toLocaleString("sv-SE", {
                          hour: "2-digit",
                          minute: "2-digit",
                          day: "2-digit",
                          month: "2-digit",
                        })}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className={`border-t bg-white p-3 flex gap-2 ${
              isTeacher ? "" : "rounded-b-lg"
            }`}
          >
            <input
              type="text"
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              placeholder={
                isTeacher
                  ? "Skriv ett svar…"
                  : "Skriv ett meddelande till läraren…"
              }
              className="flex-1 border rounded px-3 py-2"
              disabled={
                sending || (isTeacher && activeStudent === null)
              }
            />
            <button
              type="submit"
              disabled={
                sending || !newMessage.trim() ||
                (isTeacher && activeStudent === null)
              }
              className="btn-dark rounded-md px-4 py-2 flex items-center gap-1 disabled:opacity-50"
            >
              <Send className="w-4 h-4" /> Skicka
            </button>
          </form>
        </main>
      </div>
    </div>
  );
}
