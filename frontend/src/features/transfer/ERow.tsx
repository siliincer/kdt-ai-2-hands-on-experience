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
    <div className="border-b" style={{ borderColor: 'rgba(15,30,61,0.06)' }}>
      <button
        type="button"
        className="w-full flex items-center gap-3 py-2.5 text-left hover:opacity-80"
        onClick={onToggle}
      >
        <span
          className="text-xs shrink-0 w-18"
          style={{ color: '#94A3B8', fontFamily: F }}
        >
          {label}
        </span>
        <span
          className="flex-1 text-sm"
          style={{
            color: '#F8FAFC',
            fontFamily: mono ? M : F,
            borderBottom: `1.5px dashed ${MINT}`,
            paddingBottom: 1,
          }}
        >
          {value || <span style={{ color: '#B0B8C9' }}>입력</span>}
        </span>
        <Edit2 size={11} color={MINT} />
      </button>
      {isEditing ? <div className="pb-1">{children}</div> : null}
    </div>
  );
}
