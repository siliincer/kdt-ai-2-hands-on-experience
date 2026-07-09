import { Edit2 } from 'lucide-react';

import { MINT } from '@/shared/constants/color';
import { M, F } from '@/shared/constants/font';

export function ERow({
  label,
  value,
  isEditing,
  onToggle,
  mono = false,
  children,
}: {
  label: string;
  value: string;
  isEditing: boolean;
  onToggle: () => void;
  mono?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="border-b" style={{ borderColor: 'var(--border)' }}>
      <button
        type="button"
        className="w-full flex items-center gap-3 py-2.5 text-left hover:opacity-80"
        onClick={onToggle}
      >
        <span
          className="text-xs shrink-0 w-18"
          style={{ color: 'var(--muted-foreground)', fontFamily: F }}
        >
          {label}
        </span>
        <span
          className="flex-1 text-sm"
          style={{
            color: 'var(--foreground)',
            fontFamily: mono ? M : F,
            borderBottom: `1.5px dashed ${MINT}`,
            paddingBottom: 1,
          }}
        >
          {value || (
            <span style={{ color: 'var(--muted-foreground)' }}>입력</span>
          )}
        </span>
        <Edit2 size={11} color={MINT} />
      </button>
      {isEditing ? <div className="pb-1">{children}</div> : null}
    </div>
  );
}
