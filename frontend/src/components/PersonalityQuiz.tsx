/**
 * PersonalityQuiz — 3-frågors onboarding som sätter PersonalityProfile.
 *
 * Pedagogisk princip: det finns inget "rätt" svar. Quizen påverkar
 * bara event-mix (introvert → färre sociala events) och Wellbeing-
 * tröskelvärden — aldrig elevens upplevelse av att "lyckas".
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";

interface PersonalityOut {
  introvert_score: number;
  thrill_seeker_score: number;
  family_oriented_score: number;
  onboarded: boolean;
}

const QUESTIONS = [
  {
    key: "introvert_score" as const,
    question: "Vad ger dig energi?",
    answers: [
      { value: 10, text: "Att hänga med många människor — ju fler desto bättre" },
      { value: 30, text: "Att umgås med några kompisar i taget" },
      { value: 50, text: "Mix av båda — beror på dagen" },
      { value: 70, text: "Mest tid själv eller med en eller två" },
      { value: 90, text: "Ensam tid — fest dränerar mig snabbt" },
    ],
  },
  {
    key: "thrill_seeker_score" as const,
    question: "Hur tänker du om risker?",
    answers: [
      { value: 10, text: "Säkra val — buffert framför nöje" },
      { value: 30, text: "Mest säkert men någon impulskonsumtion" },
      { value: 50, text: "Beror på — jag väger för och emot" },
      { value: 70, text: "Jag chansar gärna när det är värt det" },
      { value: 90, text: "Livet är kort — gör grejer som känns rätt nu" },
    ],
  },
  {
    key: "family_oriented_score" as const,
    question: "Hur viktigt är familjeevenemang?",
    answers: [
      { value: 10, text: "Familj är viktigt men separat från mitt liv" },
      { value: 30, text: "Jag deltar i de flesta men inte alla" },
      { value: 50, text: "Mix — beror på vem och vad" },
      { value: 70, text: "Familj är viktigt — försöker alltid vara med" },
      { value: 90, text: "Familjen kommer först, alltid" },
    ],
  },
];

export function PersonalityQuiz() {
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [scores, setScores] = useState({
    introvert_score: 50,
    thrill_seeker_score: 50,
    family_oriented_score: 50,
  });
  const [done, setDone] = useState(false);

  const personalityQ = useQuery({
    queryKey: ["wellbeing-personality"],
    queryFn: () => api<PersonalityOut>("/wellbeing/personality"),
  });

  const saveMut = useMutation({
    mutationFn: (body: typeof scores) =>
      api<PersonalityOut>("/wellbeing/personality", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["wellbeing-personality"] });
      setDone(true);
    },
  });

  // Visa quiz BARA om eleven inte är onboardad
  if (personalityQ.isLoading) return null;
  if (personalityQ.data?.onboarded) return null;
  if (done) {
    return (
      <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-sm text-emerald-900 mb-4">
        <span className="font-medium">Klart!</span> Din personlighet är sparad.
        Det påverkar vilka typer av events du får — det finns inget rätt eller
        fel.
      </div>
    );
  }

  const q = QUESTIONS[step];
  const isLast = step === QUESTIONS.length - 1;

  function pickAnswer(value: number) {
    const newScores = { ...scores, [q.key]: value };
    setScores(newScores);
    if (isLast) {
      saveMut.mutate(newScores);
    } else {
      setStep(step + 1);
    }
  }

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4 space-y-3">
      <div className="flex items-center gap-2 font-medium">
        <Sparkles className="w-4 h-4 text-amber-600" />
        Lär systemet känna dig (3 frågor)
      </div>
      <div className="text-xs text-slate-600">
        Inget "rätt" svar — det här påverkar bara vilka events du får
        på Dashboard. Du kan ändra senare i inställningar.
      </div>
      <div className="text-xs text-slate-500">
        Fråga {step + 1} / {QUESTIONS.length}
      </div>
      <div className="font-medium text-slate-900">{q.question}</div>
      <div className="space-y-1.5">
        {q.answers.map((a) => (
          <button
            key={a.value}
            onClick={() => pickAnswer(a.value)}
            disabled={saveMut.isPending}
            className="w-full text-left p-2 rounded border bg-white hover:bg-slate-50 hover:border-amber-400 text-sm disabled:opacity-50"
          >
            {a.text}
          </button>
        ))}
      </div>
      <button
        onClick={() => saveMut.mutate(scores)}
        disabled={saveMut.isPending}
        className="text-xs text-slate-500 underline"
      >
        Hoppa över — använd default
      </button>
    </div>
  );
}
