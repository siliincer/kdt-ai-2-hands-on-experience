import { useState } from 'react';

import { Check, X } from 'lucide-react';

import { ERow } from '@/features/transfer/ERow';

import { useApprove } from '../model/approveContext';

import type { ConfirmModalArgs } from '../types/hitl';
import type { ApprovalDecision } from '../types/interface';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * need_approval(confirm_modal) 툴 파트 렌더러 (HITL, 계약 3.7).
 * Prepare 가 고정한 변경 조건을 표시하고 승인/수정/취소한다.
 * - 승인 → approval_outcome=approved
 * - 수정 → change_requested + change_target(해당 입력 화면으로 되돌아가 재입력)
 * - 취소 → cancelled
 *
 * allowed_change_targets 항목은 ERow(수정 진입점)로 노출한다. 수정은 값을 인라인으로
 * 바꾸지 않고 재입력(re-prepare)을 요청한다 — Execute 는 고정된 조건만 신뢰하므로(계약 7.6).
 */
export const ConfirmModalUI: ToolCallMessagePartComponent = ({ args }) => {
  const approve = useApprove();
  const a = (args ?? {}) as ConfirmModalArgs;
  const approvalId = a.approvalId;
  const purpose = a.purpose ?? 'setting';
  const changeTargets = a.allowed_change_targets ?? [];

  const [outcome, setOutcome] = useState<ApprovalDecision | null>(null);

  const respond = (decision: ApprovalDecision, changeTarget?: string) => {
    if (!approvalId || outcome) return;
    setOutcome(decision);
    void approve(
      approvalId,
      decision,
      changeTarget ? { change_target: changeTarget } : undefined,
      purpose,
    );
  };

  if (outcome === 'cancelled') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <X className="h-3.5 w-3.5" />
        변경을 취소했어요.
      </div>
    );
  }
  if (outcome === 'change_requested') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        다시 입력할게요.
      </div>
    );
  }
  if (outcome === 'approve') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        변경을 승인했어요.
      </div>
    );
  }

  const account = a.account;
  const accountLabel = account
    ? [account.bank_name, account.masked_account_number]
        .filter(Boolean)
        .join(' ')
    : '';

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <p className="mb-3 text-sm font-semibold text-foreground">
        {a.title ?? '변경 내용을 확인해 주세요.'}
      </p>

      <div className="mb-4">
        {account ? (
          <div
            className="flex items-center gap-3 border-b py-2.5"
            style={{ borderColor: 'var(--border)' }}
          >
            <span className="w-18 shrink-0 text-xs text-muted-foreground">
              계좌
            </span>
            <span className="flex-1 text-sm text-foreground">
              {accountLabel}
            </span>
          </div>
        ) : null}

        {a.alias !== undefined ? (
          changeTargets.includes('alias') ? (
            <ERow
              label="새 별칭"
              value={a.alias ?? ''}
              isEditing={false}
              onToggle={() => respond('change_requested', 'alias')}
            />
          ) : (
            <div
              className="flex items-center gap-3 border-b py-2.5"
              style={{ borderColor: 'var(--border)' }}
            >
              <span className="w-18 shrink-0 text-xs text-muted-foreground">
                새 별칭
              </span>
              <span className="flex-1 text-sm text-foreground">{a.alias}</span>
            </div>
          )
        ) : null}
      </div>

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => respond('cancelled')}
          className="rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/40"
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => respond('approve')}
          className="rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground transition"
        >
          승인
        </button>
      </div>
    </div>
  );
};
