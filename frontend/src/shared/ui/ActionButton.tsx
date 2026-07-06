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
      ? 'border border-emerald-400/40 bg-accent/15 text-accent-foreground hover:border-accent hover:text-foreground'
      : 'border border-border bg-card/90 text-foreground hover:border-emerald-400/40 hover:text-foreground';

  return (
    <button
      className={`${baseClassName} ${variantClassName} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
