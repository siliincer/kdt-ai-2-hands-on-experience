import { useNavigate } from 'react-router';

import { ALL_TX_ITEM } from '@/features/mockData/mockData';

import type { TransactionsData } from '@/shared/types/ui';

import { TransactionsCard } from './TransactionCard';

// 라우트(디버그) 잔존용 어댑터: 목데이터를 TransactionsData 형태로. E단계에서 라우트째 제거.
const MOCK_TRANSACTIONS: TransactionsData = {
  months: ['2025-06', '2025-05', '2025-04', '2025-03', '2025-02'],
  items: ALL_TX_ITEM,
};

export default function TransactionsFeature() {
  const navigate = useNavigate();

  return (
    // 고정된 다크 스킨을 시스템 테마 스펙인 bg-card 및 border-border로 전환
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground">거래 내역</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            최근 거래 기록과 지출 흐름을 자세히 확인해보세요.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="rounded-2xl border border-border px-4 py-2 text-sm text-foreground transition hover:bg-muted/50"
        >
          홈으로
        </button>
      </div>
      <TransactionsCard data={MOCK_TRANSACTIONS} />
    </div>
  );
}
