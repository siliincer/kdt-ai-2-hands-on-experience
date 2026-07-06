import type { ReactNode } from 'react';

type SectionCardProps = {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
};

export default function SectionCard({
  title,
  description,
  action,
  children,
}: SectionCardProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-800/70 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">{title}</p>
          {description ? (
            <p className="mt-1 text-xs text-slate-400">{description}</p>
          ) : null}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}
