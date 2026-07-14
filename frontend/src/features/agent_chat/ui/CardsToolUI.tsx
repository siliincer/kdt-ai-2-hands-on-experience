import { useThreadRuntime } from '@assistant-ui/react';

import { CardInfoCard } from '@/features/card/CardInfoCard';
import { useCustomTanstackQuery } from '@/shared/hooks/useCustomTanstackQuery';

import { UI_CARDS_URL } from '../constants/constants';

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import type { CardsData } from '@/shared/types/ui';

function CardSkeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-7 w-28 rounded bg-muted" />
      <div className="h-32 rounded-3xl bg-muted" />
    </div>
  );
}

/**
 * component:cards 시그널 → 카드 관리 카드.
 * SSE 는 렌더 시그널만(ADR-002), 데이터는 여기서 tanstack query 로 조회.
 */
export const CardsToolUI: ToolCallMessagePartComponent = () => {
  const thread = useThreadRuntime();
  const token = sessionStorage.getItem('rf_access_token') ?? '';

  const { data, isPending, isError } = useCustomTanstackQuery<CardsData>({
    queryKey: ['ui', 'cards'],
    url: UI_CARDS_URL,
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
          카드 정보를 불러오지 못했어요.
        </p>
      ) : (
        <CardInfoCard data={data} onPrompt={(text) => thread.append(text)} />
      )}
    </div>
  );
};
