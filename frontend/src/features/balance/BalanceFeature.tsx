import { useState } from 'react';
import { useNavigate } from 'react-router';

import { accounts as mockAccounts } from '@/features/mockData/mockData';

import type { BalanceData } from '@/shared/types/ui';

import { BalanceCard } from './BalanceCard';
import { AccountDetailCard } from './AccountDetailCard';

// 라우트(디버그) 잔존용 어댑터: 목데이터를 BalanceData 형태로. E단계에서 라우트째 제거.
const MOCK_BALANCE: BalanceData = {
  total: mockAccounts.reduce((sum, a) => sum + a.balance, 0),
  accounts: mockAccounts,
};

export default function BalanceFeature() {
  const navigate = useNavigate();
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(
    null,
  );

  return (
    // 고정 어두운 배경(bg-slate-800/70)을 시스템 공통 카드 스펙(bg-card, border-border)으로 변경
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground">잔액 조회</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            전체 자산과 계좌 세부 정보를 확인하고, 바로 이체할 수 있습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSelectedAccountId(null)}
          className="rounded-2xl border border-border px-4 py-2 text-sm text-foreground transition hover:bg-muted/50"
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
          data={MOCK_BALANCE}
          onPrompt={() => navigate('/transfer')}
        />
      )}
    </div>
  );
}
