import { BudgetCard } from '@/features/budget/BudgetCard';
import { useCustomTanstackQuery } from '@/shared/hooks/useCustomTanstackQuery';

import { UI_BUDGET_URL } from '../constants/constants';

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import type { BudgetData } from '@/shared/types/ui';

function CardSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-7 w-32 rounded bg-muted" />
      <div className="h-32 rounded-2xl bg-muted" />
    </div>
  );
}

/**
 * component:budget 시그널 → 예산 현황 카드.
 * SSE 는 렌더 시그널만(ADR-002), 데이터는 여기서 tanstack query 로 조회.
 */
export const BudgetToolUI: ToolCallMessagePartComponent = () => {
  const token = sessionStorage.getItem('rf_access_token') ?? '';

  const { data, isPending, isError } = useCustomTanstackQuery<BudgetData>({
    queryKey: ['ui', 'budget'],
    url: UI_BUDGET_URL,
    fetchOptions: { headers: { Authorization: `Bearer ${token}` } },
    throwOnError: false,
    retry: false,
  });

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      {isPending ? (
        <CardSkeleton />
      ) : isError || !data ? (
        <p className="text-sm text-muted-foreground">
          예산 현황을 불러오지 못했어요.
        </p>
      ) : (
        <BudgetCard data={data} />
      )}
    </div>
  );
};
