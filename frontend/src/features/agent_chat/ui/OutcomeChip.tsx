import { Check, X } from 'lucide-react';

import type { ReactNode } from 'react';

type ChipVariant = 'success' | 'cancel' | 'neutral';

/**
 * HITL 카드가 제출/취소된 뒤 자리에 남기는 작은 결과 칩.
 * - success: 초록 테두리 + 체크(승인/제출 완료)
 * - cancel: 무채색 + X(취소)
 * - neutral: 무채색 + 아이콘 없음(안내)
 * 여러 입력 UI 에서 반복되던 마크업을 한 곳으로 모은다.
 */
export function OutcomeChip({
  variant,
  children,
}: {
  variant: ChipVariant;
  children: ReactNode;
}) {
  const isSuccess = variant === 'success';
  const tone = isSuccess
    ? 'border-chart-2/40 bg-chart-2/10 text-foreground'
    : 'border-border/60 bg-muted/40 text-muted-foreground';

  return (
    <div
      className={`my-1 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${tone}`}
    >
      {variant === 'success' ? <Check className="h-3.5 w-3.5" /> : null}
      {variant === 'cancel' ? <X className="h-3.5 w-3.5" /> : null}
      {children}
    </div>
  );
}
