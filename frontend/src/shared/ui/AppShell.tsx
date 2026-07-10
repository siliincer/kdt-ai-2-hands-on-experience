import type { ReactNode } from 'react';

type AppShellProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

export default function AppShell({
  title,
  description,
  children,
}: AppShellProps) {
  return (
    <section className="rounded-3xl border border-border bg-card p-6 shadow-xl">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground">{title}</h2>
          {description ? (
            <p className="mt-1 text-sm text-slate-600">{description}</p>
          ) : null}
        </div>
      </div>
      {children}
    </section>
  );
}
