import type { ReactNode } from 'react';

interface PageShellProps {
  children: ReactNode;
  title: string;
  description?: string;
}

export default function PageShell({
  children,
  title,
  description,
}: PageShellProps) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-8 px-4 py-8 md:px-6">
      <header className="flex flex-col gap-3 rounded-4xl border border-white/10 bg-slate-950/70 p-6 shadow-2xl shadow-slate-950/10 backdrop-blur-xl">
        <div>
          <p className="text-sm uppercase tracking-[0.3em] text-emerald-300/80">
            RealFinance
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-white md:text-4xl">
            {title}
          </h1>
        </div>
        {description ? (
          <p className="max-w-3xl text-sm text-slate-400">{description}</p>
        ) : null}
      </header>
      <main className="grid gap-6 md:grid-cols-[1.5fr_0.9fr]">{children}</main>
    </div>
  );
}
