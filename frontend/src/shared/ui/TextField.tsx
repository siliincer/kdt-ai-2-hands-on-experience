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
      {label ? <span className="text-sm text-slate-400">{label}</span> : null}
      <input
        className={`w-full rounded-2xl border border-white/10 bg-slate-800/70 px-3 py-2 text-sm text-white outline-none transition focus:border-emerald-400/60 ${className}`}
        {...props}
      />
    </label>
  );
}
