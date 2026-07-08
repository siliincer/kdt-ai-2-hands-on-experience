import { F, M } from '@/shared/constants/font';

import type { BalanceData } from '@/shared/types/ui';

interface BalanceCardProps {
  data: BalanceData;
  /** 카드 내 액션 → 자연어 프롬프트 전송(라우팅 대신 chat 흐름). */
  onPrompt?: (text: string) => void;
}

const QUICK_ACTIONS = [
  { label: '거래내역 보기', prompt: '거래 내역 보여줘' },
  { label: '카드 청구서', prompt: '카드 청구서 보여줘' },
  { label: '계좌 이체', prompt: '송금하고 싶어' },
];

export function BalanceCard({ data, onPrompt }: BalanceCardProps) {
  const total =
    data.total || data.accounts.reduce((sum, item) => sum + item.balance, 0);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg">💳</span>
        <p
          className="text-sm font-semibold text-foreground"
          style={{ fontFamily: F }}
        >
          내 자산 현황
        </p>
      </div>
      <p
        className="text-2xl font-bold text-foreground"
        style={{ fontFamily: "'DM Sans', sans-serif" }}
      >
        {total.toLocaleString()}원
      </p>
      <p
        className="mb-4 text-xs text-muted-foreground"
        style={{ fontFamily: F }}
      >
        총 자산
      </p>

      <div className="mb-4 space-y-3 rounded-3xl border border-border p-3">
        {data.accounts.map((account) => (
          <div
            key={account.id}
            className="w-full rounded-3xl border border-border p-3 text-left"
            style={{ color: 'var(--foreground)', fontFamily: F }}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-sm font-bold text-white shadow-sm"
                  style={{ background: account.color || 'var(--primary)' }}
                >
                  {account.bank[0]}
                </div>
                <div>
                  <p className="text-xs font-medium text-foreground">
                    {account.bank}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    ···{account.tail}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm font-bold" style={{ fontFamily: M }}>
                  {account.balance.toLocaleString()}원
                </p>
                <button
                  type="button"
                  onClick={() => onPrompt?.('송금하고 싶어')}
                  className="mt-2 rounded-full border border-border bg-secondary px-3 py-1 text-[10px] font-medium text-secondary-foreground transition hover:bg-muted"
                  style={{ fontFamily: F }}
                >
                  이체
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        {QUICK_ACTIONS.map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => onPrompt?.(item.prompt)}
            className="rounded-full border border-border bg-transparent px-3 py-2 text-[10px] font-medium text-muted-foreground transition hover:bg-muted/30 hover:text-foreground"
            style={{ fontFamily: F }}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}
