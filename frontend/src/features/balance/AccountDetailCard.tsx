import { accounts, ALL_TX } from '@/features/mockData/mockData';
import { NAVY } from '@/shared/constants/color';
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
      <div
        className="mb-3 rounded-3xl p-4 text-white"
        style={{
          background: 'linear-gradient(135deg,#0F1E3D 0%,#1a3a6b 100%)',
        }}
      >
        <p className="text-xs opacity-80" style={{ fontFamily: F }}>
          {account.bank} · {account.alias} ···{account.tail}
        </p>
        <p
          className="mt-3 text-2xl font-bold"
          style={{ fontFamily: "'DM Sans',sans-serif" }}
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
            className="rounded-2xl bg-slate-100 py-2 text-[10px] font-medium text-slate-700 hover:opacity-90"
            style={{ fontFamily: F }}
          >
            {label}
          </button>
        ))}
      </div>
      <p
        className="mb-3 text-xs font-semibold"
        style={{ color: '#6B7A99', fontFamily: F }}
      >
        최근 거래
      </p>
      <div className="space-y-3">
        {recent.map((tx) => (
          <div
            key={tx.id}
            className="flex items-center gap-2 rounded-3xl border border-slate-200 px-3 py-3"
          >
            <span className="text-sm">{tx.emoji}</span>
            <div className="flex-1 min-w-0">
              <p
                className="truncate text-xs font-medium"
                style={{ color: NAVY, fontFamily: F }}
              >
                {tx.name}
              </p>
              <p
                className="text-[10px] text-slate-500"
                style={{ fontFamily: M }}
              >
                {tx.date}
              </p>
            </div>
            <p
              className="text-xs font-bold"
              style={{
                color: tx.type === 'in' ? '#52C41A' : NAVY,
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
