import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: 'primary' | 'secondary';
};

export default function ActionButton({
  children,
  variant = 'secondary',
  className = '',
  ...props
}: ActionButtonProps) {
  const baseClassName = 'rounded-full px-3 py-1.5 text-sm transition';
  const variantClassName =
    variant === 'primary'
      ? 'border border-emerald-400/40 bg-emerald-500/15 text-emerald-200 hover:border-emerald-300 hover:text-emerald-100'
      : 'border border-white/10 bg-slate-800/70 text-slate-300 hover:border-emerald-400/40 hover:text-emerald-200';

  return (
    <button
      className={`${baseClassName} ${variantClassName} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
