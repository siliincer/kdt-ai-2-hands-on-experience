import { Check } from 'lucide-react';

import { won } from '../utils/format';

import { HITL_CARD } from './uiStyles';

import type { TransferResultArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

function AccountLine({
  label,
  bank,
  masked,
}: {
  label: string;
  bank?: string | null;
  masked?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm text-foreground">
        {[bank, masked].filter(Boolean).join(' ')}
      </span>
    </div>
  );
}

/**
 * transfer_result 결과 렌더러 (계약 4.5).
 * ADR C3: 데이터는 SSE inline payload(args)로 온다(별도 fetch 없음).
 * 실행 순간의 transaction_id·completed_at 스냅샷을 표시한다.
 */
export const TransferResultUI: ToolCallMessagePartComponent = ({ args }) => {
  const a = (args ?? {}) as TransferResultArgs;

  return (
    <div className={HITL_CARD}>
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-chart-2/15 text-chart-2">
          <Check className="h-4 w-4" />
        </span>
        <p className="text-sm font-semibold text-foreground">송금 완료</p>
      </div>

      <p className="mb-3 text-2xl font-bold text-foreground">{won(a.amount)}</p>

      <div className="space-y-2 rounded-2xl border border-border p-3">
        <AccountLine
          label="보내는 계좌"
          bank={a.from_account?.bank_name}
          masked={a.from_account?.masked_account_number}
        />
        <AccountLine
          label="받는 분"
          bank={a.recipient?.name ?? a.recipient?.bank_name}
          masked={a.recipient?.masked_account_number}
        />
      </div>

      {a.transaction_id ? (
        <p className="mt-2 text-right text-[10px] text-muted-foreground">
          거래번호 {a.transaction_id}
        </p>
      ) : null}
    </div>
  );
};
