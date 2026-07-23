import { useState } from 'react';

import { ERow } from '@/features/transfer/ERow';

import { useApprove } from '../model/approveContext';
import { joinParts, won } from '../utils/format';

import { OutcomeChip } from './OutcomeChip';
import { HITL_BTN_PRIMARY, HITL_BTN_SECONDARY, HITL_CARD } from './uiStyles';

import type { ConfirmModalArgs } from '../types/hitl';
import type { ApprovalDecision } from '../types/interface';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

interface DisplayRow {
  label: string;
  value: string;
  /** allowed_change_targets 와 매칭되면 ERow(수정 진입점)로 노출한다. */
  target?: string;
}

/** confirm_modal 을 목적별 표시 행으로 변환한다(계약 3.7). */
function buildRows(a: ConfirmModalArgs): DisplayRow[] {
  const purpose = a.purpose ?? '';
  const rows: DisplayRow[] = [];

  if (purpose === 'external_transfer' || purpose === 'internal_transfer') {
    if (a.from_account) {
      rows.push({
        label: '보내는 계좌',
        value: joinParts(
          a.from_account.account_alias ?? a.from_account.bank_name,
          a.from_account.masked_account_number,
        ),
        target: 'from_account',
      });
    }
    // 타인송금은 recipient, 본인송금은 입금 계좌(to_account)를 표시한다(계약 3.7·4.5).
    if (a.recipient) {
      rows.push({
        label: '받는 분',
        value: joinParts(
          a.recipient.name,
          a.recipient.bank_name,
          a.recipient.masked_account_number,
        ),
        target: 'recipient',
      });
    }
    if (a.to_account) {
      rows.push({
        label: '받는 계좌',
        value: joinParts(
          a.to_account.account_alias ?? a.to_account.bank_name,
          a.to_account.masked_account_number,
        ),
        target: 'to_account',
      });
    }
    if (a.amount !== undefined) {
      rows.push({ label: '금액', value: won(a.amount), target: 'amount' });
    }
    return rows;
  }

  // 기본 출금 계좌 변경.
  if (purpose === 'default_account') {
    if (a.account) {
      rows.push({
        label: '새 기본 계좌',
        value: joinParts(
          a.account.account_alias ?? a.account.bank_name,
          a.account.masked_account_number,
        ),
      });
    }
    return rows;
  }

  // 설정(별칭) 목적.
  if (a.account) {
    rows.push({
      label: '계좌',
      value: joinParts(a.account.bank_name, a.account.masked_account_number),
    });
  }
  if (a.alias !== undefined) {
    rows.push({ label: '새 별칭', value: a.alias ?? '', target: 'alias' });
  }
  return rows;
}

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
    return <OutcomeChip variant="cancel">변경을 취소했어요.</OutcomeChip>;
  }
  if (outcome === 'change_requested') {
    return <OutcomeChip variant="neutral">다시 입력할게요.</OutcomeChip>;
  }
  if (outcome === 'approve') {
    return <OutcomeChip variant="success">변경을 승인했어요.</OutcomeChip>;
  }

  const rows = buildRows(a);

  return (
    <div className={HITL_CARD}>
      <p className="mb-3 text-sm font-semibold text-foreground">
        {a.title ?? '변경 내용을 확인해 주세요.'}
      </p>

      <div className="mb-4">
        {rows.map((row) =>
          row.target && changeTargets.includes(row.target) ? (
            <ERow
              key={row.label}
              label={row.label}
              value={row.value}
              isEditing={false}
              onToggle={() => respond('change_requested', row.target)}
            />
          ) : (
            <div
              key={row.label}
              className="flex items-center gap-3 border-b py-2.5"
              style={{ borderColor: 'var(--border)' }}
            >
              <span className="w-18 shrink-0 text-xs text-muted-foreground">
                {row.label}
              </span>
              <span className="flex-1 text-sm text-foreground">
                {row.value}
              </span>
            </div>
          ),
        )}
      </div>

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => respond('cancelled')}
          className={HITL_BTN_SECONDARY}
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => respond('approve')}
          className={HITL_BTN_PRIMARY}
        >
          승인
        </button>
      </div>
    </div>
  );
};
