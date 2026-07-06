import type { InputHTMLAttributes } from 'react';

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
};

export default function TextField({
  label,
  className = '',
  ...props
}: TextFieldProps) {
  return (
    <label className="block space-y-2">
      {label ? <span className="text-sm text-slate-600">{label}</span> : null}
      <input
        className={`w-full rounded-2xl border border-border bg-input-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-accent/70 ${className}`}
        {...props}
      />
    </label>
  );
}
