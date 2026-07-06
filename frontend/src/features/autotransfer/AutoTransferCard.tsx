import { useState } from 'react';
import { Plus } from 'lucide-react';
import { autoTxItems } from '@/features/mockData/mockData';
import { F, M } from '@/shared/constants/font';

export function AutoTransferCard({ onShowForm }: { onShowForm: () => void }) {
  const [toggles, setToggles] = useState(
    autoTxItems.map((item) => item.active),
  );

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">🔄</span>
        <p
          className="text-sm font-semibold text-foreground"
          style={{ fontFamily: F }}
        >
          자동 이체 목록
        </p>
      </div>
      <div className="space-y-3">
        {autoTxItems.map((item, index) => (
          <div
            key={item.name}
            className="flex items-center justify-between rounded-3xl border border-border bg-card px-3 py-3 shadow-xs"
          >
            <div>
              <p
                className="text-xs font-semibold text-foreground"
                style={{ fontFamily: F }}
              >
                {item.name}
              </p>
              <p
                className="text-[10px] text-muted-foreground"
                style={{ fontFamily: F }}
              >
                {item.cycle}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <p
                className="text-xs font-bold text-foreground"
                style={{ fontFamily: M }}
              >
                {item.amount.toLocaleString()}원
              </p>
              <button
                type="button"
                onClick={() =>
                  setToggles((prev) => {
                    const next = [...prev];
                    next[index] = !next[index];
                    return next;
                  })
                }
                className="rounded-full px-3 py-1 text-[10px] font-semibold transition-all"
                style={{
                  background: toggles[index] ? 'var(--accent)' : 'var(--muted)',
                  color: toggles[index]
                    ? 'var(--primary-foreground)'
                    : 'var(--muted-foreground)',
                  fontFamily: F,
                }}
              >
                {toggles[index] ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={onShowForm}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-border bg-transparent py-2.5 text-sm font-semibold text-muted-foreground transition hover:bg-muted/30 hover:text-foreground"
        style={{ fontFamily: F }}
      >
        <Plus size={14} /> 자동 이체 추가
      </button>
    </div>
  );
}
