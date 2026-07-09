import { accounts, ALL_TX } from '@/features/mockData/mockData';
import { F, M } from '@/shared/constants/font';

export function AccountDetailCard({
  accountId,
  onNavigate,
}: {
  accountId: number;
  onNavigate: (path: string) => void;
}) {
  const account = accounts.find((item) => item.id === accountId);
  if (!account) return null;

  const recent = ALL_TX.filter((tx) => tx.month === '2025-06').slice(0, 4);

  return (
    <div>
      {/* 딥 블루 그라디언트를 테마 기본 프라이머리 색조 그라디언트로 확장 변경 */}
      <div
        className="mb-3 rounded-3xl p-4 text-primary-foreground"
        style={{
          background:
            'linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%)',
        }}
      >
        <p className="text-xs opacity-80" style={{ fontFamily: F }}>
          {account.bank} · {account.alias} ···{account.tail}
        </p>
        <p
          className="mt-3 text-2xl font-bold"
          style={{ fontFamily: "'DM Sans', sans-serif" }}
        >
          {account.balance.toLocaleString()}원
        </p>
      </div>

      <div className="mb-4 grid grid-cols-4 gap-2">
        {['입금', '출금', '이체', '상세'].map((label) => (
          <button
            key={label}
            type="button"
            onClick={
              label === '이체' ? () => onNavigate('/transfer') : undefined
            }
            className="rounded-2xl bg-secondary py-2 text-[10px] font-medium text-secondary-foreground transition hover:bg-muted"
            style={{ fontFamily: F }}
          >
            {label}
          </button>
        ))}
      </div>

      <p
        className="mb-3 text-xs font-semibold text-muted-foreground"
        style={{ fontFamily: F }}
      >
        최근 거래
      </p>

      <div className="space-y-3">
        {recent.map((tx) => (
          <div
            key={tx.id}
            className="flex items-center gap-2 rounded-3xl border border-border bg-card/50 px-3 py-3"
          >
            <span className="text-sm">{tx.emoji}</span>
            <div className="flex-1 min-w-0">
              <p
                className="truncate text-xs font-medium text-foreground"
                style={{ fontFamily: F }}
              >
                {tx.name}
              </p>
              <p
                className="text-[10px] text-muted-foreground"
                style={{ fontFamily: M }}
              >
                {tx.date}
              </p>
            </div>
            <p
              className="text-xs font-bold"
              style={{
                color:
                  tx.type === 'in' ? 'var(--chart-2)' : 'var(--foreground)',
                fontFamily: M,
              }}
            >
              {tx.type === 'in' ? '+' : ''}
              {Math.abs(tx.amount).toLocaleString()}원
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
