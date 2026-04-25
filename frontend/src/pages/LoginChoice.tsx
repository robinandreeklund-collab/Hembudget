import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { PaperChip } from "@/components/paper";

export default function LoginChoice() {
  return (
    <div className="min-h-screen bg-paper text-ink grid place-items-center p-6">
      <div className="w-full max-w-2xl">
        <Link
          to="/"
          className="text-sm text-[#666] nav-link inline-flex items-center gap-1 mb-6"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka till startsidan
        </Link>
        <div className="text-center mb-10">
          <div className="eyebrow mb-3">Ekonomilabbet</div>
          <h1 className="serif text-4xl md:text-5xl leading-[1.05]">Välkommen.</h1>
          <p className="lead mt-3">Är du lärare eller elev?</p>
        </div>

        <Link
          to="/demo"
          className="block border-[1.5px] border-ink bg-paper text-ink p-5 mb-6 transition-colors hover:bg-[#fffef5]"
        >
          <div className="flex items-center gap-3">
            <PaperChip color="special">⚡</PaperChip>
            <div>
              <div className="serif text-lg leading-tight">Prova demoläge direkt</div>
              <div className="text-sm text-[#555] mt-0.5">
                Logga in utan konto — färdig klass att utforska.
              </div>
            </div>
          </div>
        </Link>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Link
            to="/login/teacher"
            className="feature-card text-left group block"
          >
            <PaperChip color="special">Lä</PaperChip>
            <h2 className="serif text-2xl mt-4">Lärare / Skola</h2>
            <p className="mt-2 body-prose text-sm">
              Logga in med e-post och lösenord för att hantera din klass.
            </p>
          </Link>

          <Link
            to="/login/student"
            className="feature-card text-left group block"
          >
            <PaperChip color="grund">El</PaperChip>
            <h2 className="serif text-2xl mt-4">Elev</h2>
            <p className="mt-2 body-prose text-sm">
              Använd din 6-teckens kod som du fått av din lärare.
            </p>
          </Link>
        </div>
      </div>
    </div>
  );
}
