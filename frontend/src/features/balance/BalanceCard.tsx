import { NAVY } from '@/shared/constants/color';
import { F, M } from '@/shared/constants/font';

import { accounts } from '@/features/mockData/mockData';

export function BalanceCard({
  onSelectAccount,
  onNavigate,
}: {
  onSelectAccount: (id: number) => void;
  onNavigate: (path: string) => void;
}) {
  const total = accounts.reduce((sum, item) => sum + item.balance, 0);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg">💳</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          내 자산 현황
        </p>
      </div>
      <p
        className="text-2xl font-bold"
        style={{ color: NAVY, fontFamily: "'DM Sans',sans-serif" }}
      >
        {total.toLocaleString()}원
      </p>
      <p className="mb-4 text-xs text-slate-500" style={{ fontFamily: F }}>
        총 자산
      </p>
      <div className="mb-4 space-y-3 rounded-3xl border border-slate-200 p-3">
        {accounts.map((account) => (
          <button
            key={account.id}
            type="button"
            onClick={() => onSelectAccount(account.id)}
            className="w-full rounded-3xl border border-slate-200 p-3 text-left hover:bg-slate-50"
            style={{ color: NAVY, fontFamily: F }}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-sm font-bold text-white"
                  style={{ background: account.color }}
                >
                  {account.bank[0]}
                </div>
                <div>
                  <p className="text-xs font-medium">{account.bank}</p>
                  <p className="text-[10px] text-slate-500">
                    ···{account.tail}
                  </p>
                </div>
              </div>
              <div>
                <p className="text-sm font-bold" style={{ fontFamily: M }}>
                  {account.balance.toLocaleString()}원
                </p>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onNavigate('/transfer');
                  }}
                  className="mt-2 rounded-full border border-emerald-200 px-3 py-1 text-[10px] font-medium text-emerald-700"
                  style={{ fontFamily: F }}
                >
                  이체
                </button>
              </div>
            </div>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onNavigate('/transactions')}
          className="rounded-full border border-emerald-200 px-3 py-2 text-[10px] font-medium text-emerald-700"
          style={{ fontFamily: F }}
        >
          거래내역 보기
        </button>
        <button
          type="button"
          onClick={() => onNavigate('/bill')}
          className="rounded-full border border-emerald-200 px-3 py-2 text-[10px] font-medium text-emerald-700"
          style={{ fontFamily: F }}
        >
          카드 청구서
        </button>
        <button
          type="button"
          onClick={() => onNavigate('/transfer')}
          className="rounded-full border border-emerald-200 px-3 py-2 text-[10px] font-medium text-emerald-700"
          style={{ fontFamily: F }}
        >
          계좌 이체
        </button>
      </div>
    </div>
  );
}
