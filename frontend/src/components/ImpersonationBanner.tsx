import { useEffect, useState } from "react";
import { ArrowLeft, UserCheck } from "lucide-react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";

type Student = {
  id: number;
  display_name: string;
  class_label: string | null;
};

export function ImpersonationBanner() {
  const { asStudent, impersonate } = useAuth();
  const [student, setStudent] = useState<Student | null>(null);

  useEffect(() => {
    if (!asStudent) {
      setStudent(null);
      return;
    }
    api<Student[]>("/teacher/students")
      .then((list) => {
        setStudent(list.find((s) => s.id === asStudent) ?? null);
      })
      .catch(() => setStudent(null));
  }, [asStudent]);

  if (!asStudent) return null;

  return (
    <div className="bg-amber-100 border-b border-amber-300 px-4 py-2 flex items-center gap-3 text-sm">
      <UserCheck className="w-4 h-4 text-amber-700" />
      <span className="text-amber-900">
        Du tittar som lärare på{" "}
        <strong>{student?.display_name ?? `elev #${asStudent}`}</strong>
        {student?.class_label && ` (${student.class_label})`}
      </span>
      <button
        onClick={() => {
          impersonate(null);
          window.location.href = "/teacher";
        }}
        className="ml-auto flex items-center gap-1 text-amber-900 hover:bg-amber-200 rounded px-2 py-1"
      >
        <ArrowLeft className="w-3 h-3" /> Tillbaka till lärarpanel
      </button>
    </div>
  );
}
