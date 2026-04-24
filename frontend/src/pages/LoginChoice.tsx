import { Link } from "react-router-dom";
import { ArrowLeft, GraduationCap, Users } from "lucide-react";

export default function LoginChoice() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-brand-50 grid place-items-center p-6">
      <div className="w-full max-w-2xl">
        <Link
          to="/"
          className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1 mb-4"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka till startsidan
        </Link>
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Välkommen!</h1>
          <p className="text-slate-600 mt-2">Är du lärare eller elev?</p>
        </div>

        <Link
          to="/demo"
          className="block bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white rounded-xl p-5 text-center mb-4 shadow-lg hover:shadow-xl transition-all"
        >
          <div className="font-semibold">⚡ Prova demoläge direkt</div>
          <div className="text-sm opacity-90 mt-0.5">
            Logga in utan konto — färdig klass att utforska
          </div>
        </Link>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Link
            to="/login/teacher"
            className="group bg-white border-2 border-slate-200 hover:border-brand-500 rounded-2xl p-8 text-center transition-all hover:shadow-xl"
          >
            <div className="inline-flex w-16 h-16 bg-brand-100 text-brand-600 rounded-full items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <Users className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-semibold text-slate-900 mb-1">
              Lärare / Skola
            </h2>
            <p className="text-sm text-slate-600">
              Logga in med e-post och lösenord för att hantera din klass.
            </p>
          </Link>

          <Link
            to="/login/student"
            className="group bg-white border-2 border-slate-200 hover:border-brand-500 rounded-2xl p-8 text-center transition-all hover:shadow-xl"
          >
            <div className="inline-flex w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <GraduationCap className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-semibold text-slate-900 mb-1">
              Elev
            </h2>
            <p className="text-sm text-slate-600">
              Använd din 6-teckens kod som du fått av din lärare.
            </p>
          </Link>
        </div>
      </div>
    </div>
  );
}
