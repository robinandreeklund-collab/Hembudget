/**
 * NoStudentSelected — visas när en lärare öppnar en sida som kräver
 * elev-context (t.ex. /arbetsgivare eller /bank) utan att ha valt
 * vilken elev hen tittar på. Istället för en rå HTTP 400 från
 * backend visar vi ett vänligt "Välj elev"-meddelande och en länk
 * tillbaka till elevlistan.
 */
import { Link } from "react-router-dom";
import { Users } from "lucide-react";
import { Card } from "@/components/Card";

export function NoStudentSelected({ pageName }: { pageName: string }) {
  return (
    <div className="p-3 md:p-6">
      <Card>
        <div className="flex items-start gap-4">
          <div className="rounded-full bg-amber-100 p-3 text-amber-700 flex-shrink-0">
            <Users className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="serif text-xl mb-1">Välj en elev först</h2>
            <p className="text-sm text-slate-700 mb-4">
              {pageName} visar elevens egen vy. Som lärare behöver du först
              öppna en specifik elev från elevlistan — då följer{" "}
              <em>{pageName}</em> med eleven du tittar på.
            </p>
            <div className="flex flex-wrap gap-2">
              <Link
                to="/teacher"
                className="inline-flex items-center gap-2 rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
              >
                Till elevlistan
              </Link>
              <Link
                to="/dashboard"
                className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Till lärar-dashboard
              </Link>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
