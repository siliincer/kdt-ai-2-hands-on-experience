import { useState } from 'react';

import { Check, X } from 'lucide-react';

import { AutoTransferFormCard } from '@/features/autotransfer/AutoTrnasferFormCard';

import { useApprove } from '../model/approveContext';

import type { ToolCallMessagePartComponent } from '@assistant-ui/react';
import type { AutoTransferConfirmValues } from '@/features/autotransfer/types/interface';

interface ConfirmArgs {
  account?: string;
  amount?: string;
  day?: string;
  approvalId?: string;
}

/**
 * need_approval(confirm_autotransfer) 툴 파트 렌더러 (HITL).
 * 프리필된 AutoTransferFormCard 를 수정 가능한 상태로 띄우고,
 * 등록/취소 시 useApprove → POST /agent/approve 로 에이전트를 재개한다.
 * (transfer 와 동일 패턴. component='autotransfer' 로 후속 턴을 분기시킨다.)
 */
export const ConfirmAutoTransferToolUI: ToolCallMessagePartComponent = ({
  args,
}) => {
  const approve = useApprove();
  const confirmArgs = (args ?? {}) as ConfirmArgs;
  const [outcome, setOutcome] = useState<'approve' | 'reject' | null>(null);

  const respond = (
    decision: 'approve' | 'reject',
    values?: AutoTransferConfirmValues,
  ) => {
    if (!confirmArgs.approvalId || outcome) return;
    setOutcome(decision);
    void approve(
      confirmArgs.approvalId,
      decision,
      values as unknown as Record<string, unknown>,
      'autotransfer',
    );
  };

  if (outcome === 'reject') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <X className="h-3.5 w-3.5" />
        자동이체 등록을 취소했어요.
      </div>
    );
  }

  if (outcome === 'approve') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        자동이체 등록을 요청했어요.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <AutoTransferFormCard
        prefill={{
          account: confirmArgs.account,
          amount: confirmArgs.amount,
          day: confirmArgs.day,
        }}
        submitLabel="자동이체 등록 →"
        onConfirm={(values) => respond('approve', values)}
        onCancel={() => respond('reject')}
      />
    </div>
  );
};
