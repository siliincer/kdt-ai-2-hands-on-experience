import { TransactionsCard } from '@/features/transactions/TransactionCard';
import { useCustomTanstackQuery } from '@/shared/hooks/useCustomTanstackQuery';

import { UI_TRANSACTIONS_URL } from '../constants/constants';

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import type { TransactionsData } from '@/shared/types/ui';

function CardSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-7 w-32 rounded bg-muted" />
      <div className="h-10 rounded-xl bg-muted" />
      <div className="h-10 rounded-xl bg-muted" />
      <div className="h-10 rounded-xl bg-muted" />
    </div>
  );
}

/**
 * component:transactions 시그널 → 거래 내역 카드.
 * SSE 는 렌더 시그널만(ADR-002), 데이터는 여기서 tanstack query 로 조회.
 */
export const TransactionsToolUI: ToolCallMessagePartComponent = () => {
  const token = sessionStorage.getItem('rf_access_token') ?? '';

  const { data, isPending, isError } = useCustomTanstackQuery<TransactionsData>(
    {
      queryKey: ['ui', 'transactions'],
      url: UI_TRANSACTIONS_URL,
      fetchOptions: { headers: { Authorization: `Bearer ${token}` } },
      throwOnError: false,
      retry: false,
    },
  );

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      {isPending ? (
        <CardSkeleton />
      ) : isError || !data ? (
        <p className="text-sm text-muted-foreground">
          거래 내역을 불러오지 못했어요.
        </p>
      ) : (
        <TransactionsCard data={data} />
      )}
    </div>
  );
};
