/**
 * Standardiserad sid-wrapper för alla undersidor i appen.
 *
 * Tidigare hade varje sida sin egen kombination av padding och max-w-X
 * vilket gjorde att t.ex. /salaries klippte vid 1152 px medan /dashboard
 * skalade fritt. Nu samlar vi mönstret här så alla undersidor följer
 * /dashboards layout: full bredd, samma padding och vertikalt mellanrum.
 */
import { ReactNode } from "react";
import clsx from "clsx";

export function PageContainer({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("p-3 md:p-6 space-y-4 md:space-y-5", className)}>
      {children}
    </div>
  );
}


/**
 * Sidhuvud med titel + valfri undertext + actions till höger.
 * Matchar Dashboard-mönstret exakt så vyer kan skifta utan att
 * användaren märker layoutskillnader.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between flex-wrap gap-3">
      <div>
        <h1 className="serif text-3xl leading-tight">{title}</h1>
        {subtitle && (
          <div className="text-sm text-slate-700 mt-1">{subtitle}</div>
        )}
      </div>
      {actions && (
        <div className="flex items-center gap-2 flex-wrap">{actions}</div>
      )}
    </div>
  );
}
