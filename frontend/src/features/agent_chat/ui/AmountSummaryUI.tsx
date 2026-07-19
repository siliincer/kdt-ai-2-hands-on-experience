import { won } from '../utils/format';

import { HITL_CARD } from './uiStyles';

import type { AmountSummaryArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * amount_summary 결과 렌더러 (계약 4.4).
 * ADR C3: 데이터는 SSE inline payload(args)로 온다. Agent 는 직접 합산하지 않는다.
 */
export const AmountSummaryUI: ToolCallMessagePartComponent = ({ args }) => {
  const a = (args ?? {}) as AmountSummaryArgs;
  const isSpending = a.summary_type === 'spending';
  const label = isSpending ? '지출' : '수입';

  return (
    <div className={HITL_CARD}>
      <div className="mb-1 flex items-center gap-2">
        <span className="text-lg">{isSpending ? '💸' : '💰'}</span>
        <p className="text-sm font-semibold text-foreground">{label} 합계</p>
      </div>
      {a.start_date && a.end_date ? (
        <p className="mb-3 text-xs text-muted-foreground">
          {a.start_date} ~ {a.end_date}
        </p>
      ) : null}

      <p className="text-2xl font-bold text-foreground">
        {won(a.total_amount)}
      </p>
    </div>
  );
};
