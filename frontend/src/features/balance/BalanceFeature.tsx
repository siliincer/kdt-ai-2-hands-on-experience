import { useState } from 'react';
import { useNavigate } from 'react-router';

import { BalanceCard } from './BalanceCard';
import { AccountDetailCard } from './AccountDetailCard';

export default function BalanceFeature() {
  const navigate = useNavigate();
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(
    null,
  );

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">잔액 조회</h2>
          <p className="mt-1 text-sm text-slate-400">
            전체 자산과 계좌 세부 정보를 확인하고, 바로 이체할 수 있습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSelectedAccountId(selectedAccountId ? null : null)}
          className="rounded-2xl border border-slate-600 px-4 py-2 text-sm text-slate-200 transition hover:bg-slate-900"
        >
          {selectedAccountId ? '뒤로' : '전체'}
        </button>
      </div>
      {selectedAccountId ? (
        <AccountDetailCard
          accountId={selectedAccountId}
          onNavigate={navigate}
        />
      ) : (
        <BalanceCard
          onSelectAccount={setSelectedAccountId}
          onNavigate={navigate}
        />
      )}
    </div>
  );
}
