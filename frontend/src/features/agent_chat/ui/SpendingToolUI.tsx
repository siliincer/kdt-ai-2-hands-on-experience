import { useThreadRuntime } from '@assistant-ui/react';

import { SpendingCard } from '@/features/spending/SpendingCard';
import { useCustomTanstackQuery } from '@/shared/hooks/useCustomTanstackQuery';

import { UI_SPENDING_URL } from '../constants/constants';

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import type { SpendingData } from '@/shared/types/ui';

function CardSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-7 w-40 rounded bg-muted" />
      <div className="h-40 rounded-2xl bg-muted" />
    </div>
  );
}

/**
 * component:spending 시그널 → 소비 분석 카드.
 * SSE 는 렌더 시그널만(ADR-002), 데이터는 여기서 tanstack query 로 조회.
 */
export const SpendingToolUI: ToolCallMessagePartComponent = () => {
  const thread = useThreadRuntime();
  const token = sessionStorage.getItem('rf_access_token') ?? '';

  const { data, isPending, isError } = useCustomTanstackQuery<SpendingData>({
    queryKey: ['ui', 'spending'],
    url: UI_SPENDING_URL,
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
          소비 분석을 불러오지 못했어요.
        </p>
      ) : (
        <SpendingCard data={data} onPrompt={(text) => thread.append(text)} />
      )}
    </div>
  );
};
