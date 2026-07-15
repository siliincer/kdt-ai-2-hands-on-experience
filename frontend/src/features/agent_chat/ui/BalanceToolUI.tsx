import { useThreadRuntime } from '@assistant-ui/react';

import { BalanceCard } from '@/features/balance/BalanceCard';
import { useCustomTanstackQuery } from '@/shared/hooks/useCustomTanstackQuery';

import { UI_BALANCE_URL } from '../constants/constants';

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import type { BalanceData } from '@/shared/types/ui';

function BalanceSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-7 w-40 rounded bg-muted" />
      <div className="h-16 rounded-2xl bg-muted" />
      <div className="h-16 rounded-2xl bg-muted" />
    </div>
  );
}

/**
 * component:balance 시그널 → 자산 현황 카드.
 * SSE 는 "무엇을 그릴지"만 알렸고(ADR-002), 데이터는 여기서 tanstack query 로
 * UI Data API 를 조회한다(캐시·로딩·에러 선언적 처리).
 */
export const BalanceToolUI: ToolCallMessagePartComponent = () => {
  const thread = useThreadRuntime();
  const token = sessionStorage.getItem('rf_access_token') ?? '';

  const { data, isPending, isError } = useCustomTanstackQuery<BalanceData>({
    queryKey: ['ui', 'balance'],
    url: UI_BALANCE_URL,
    fetchOptions: { headers: { Authorization: `Bearer ${token}` } },
    throwOnError: false,
    retry: false,
  });

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      {isPending ? (
        <BalanceSkeleton />
      ) : isError || !data ? (
        <p className="text-sm text-muted-foreground">
          자산 현황을 불러오지 못했어요.
        </p>
      ) : (
        <BalanceCard data={data} onPrompt={(text) => thread.append(text)} />
      )}
    </div>
  );
};
