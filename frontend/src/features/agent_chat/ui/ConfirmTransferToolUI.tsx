import { useState } from 'react';

import { Check, X } from 'lucide-react';

import { TransferCard } from '@/features/transfer/TransferCard';

import { useApprove } from '../model/approveContext';

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import type { TransferConfirmValues } from '@/features/transfer/types/interface.ts';
interface ConfirmArgs {
  name?: string;
  bank?: string;
  account?: string;
  amount?: string;
  time?: string;
  approvalId?: string;
}

/**
 * need_approval(confirm_transfer) 툴 파트 렌더러 (HITL).
 * 정보가 다 채워진 TransferCard 를 수정 가능한 상태로 띄우고,
 * 송금하기/취소 시 useApprove → POST /agent/approve 로 에이전트를 재개한다.
 *
 * (assistant-ui 0.14 에서 makeAssistantToolUI 는 deprecated 이므로
 *  MessagePrimitive.Parts 의 tools.by_name 오버라이드로 등록한다.)
 */
export const ConfirmTransferToolUI: ToolCallMessagePartComponent = ({
  args,
}) => {
  const approve = useApprove();
  const confirmArgs = (args ?? {}) as ConfirmArgs;
  const [outcome, setOutcome] = useState<'approve' | 'reject' | null>(null);

  const respond = (
    decision: 'approve' | 'reject',
    values?: TransferConfirmValues,
  ) => {
    if (!confirmArgs.approvalId || outcome) return;
    setOutcome(decision);
    void approve(
      confirmArgs.approvalId,
      decision,
      values as unknown as Record<string, unknown>,
    );
  };

  if (outcome === 'reject') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <X className="h-3.5 w-3.5" />
        송금을 취소했어요.
      </div>
    );
  }

  if (outcome === 'approve') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        송금을 요청했어요.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <TransferCard
        prefill={{
          name: confirmArgs.name,
          bank: confirmArgs.bank,
          account: confirmArgs.account,
          amtRaw: confirmArgs.amount,
          scheduled:
            confirmArgs.time && confirmArgs.time !== '지금 바로'
              ? confirmArgs.time
              : undefined,
        }}
        submitLabel="송금하기 →"
        onConfirm={(values) => respond('approve', values)}
        onCancel={() => respond('reject')}
      />
    </div>
  );
};
