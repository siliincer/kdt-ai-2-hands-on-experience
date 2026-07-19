import { useState } from 'react';

import { Check, X } from 'lucide-react';

import { BANKS } from '@/shared/constants/banks';

import { useSubmitInput } from '../model/submitInputContext';

import type { RecipientSelectArgs, RecentRecipient } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

// 정식 은행명만(짧은 별칭 제외) 노출한다.
const BANK_OPTIONS = BANKS.filter((bank) => bank.length > 2);

/**
 * need_input(recipient_select) 툴 파트 렌더러 (HITL, 계약 3.2).
 * 최근 수취인을 선택하거나 은행+계좌번호로 신규 수취인을 입력한다.
 * - 최근 선택: to_recipient_id 로 제출
 * - 신규 입력: 은행+계좌번호를 Backend 검증 후 to_recipient_candidate_id 로 제출
 *
 * 이름 검색은 제공하지 않는다(계약 3.2). 전체 계좌번호는 Agent State 를 통과하지 않는다.
 * TODO(FE): 신규 입력은 /recipient-candidates:verify 로 검증해 실제 candidate_id 를 받도록
 * 연결한다(현재 mock 은 검증 없이 후보 참조를 제출).
 */
export const RecipientSelectUI: ToolCallMessagePartComponent = ({ args }) => {
  const submitInput = useSubmitInput();
  const a = (args ?? {}) as RecipientSelectArgs;
  const inputRequestId = a.inputRequestId;
  const recent = a.recent_recipients ?? [];

  const [mode, setMode] = useState<'initial' | 'manual'>('initial');
  const [bankCode, setBankCode] = useState('');
  const [account, setAccount] = useState('');
  const [outcome, setOutcome] = useState<'selected' | 'cancelled' | null>(null);

  const selectRecent = (recipient: RecentRecipient) => {
    if (!inputRequestId || outcome) return;
    setOutcome('selected');
    void submitInput(inputRequestId, {
      recipient_selection_outcome: 'selected',
      to_recipient_id: recipient.to_recipient_id,
      to_recipient_candidate_id: null,
    });
  };

  const submitManual = () => {
    if (!inputRequestId || outcome || !bankCode || !account) return;
    setOutcome('selected');
    void submitInput(inputRequestId, {
      recipient_selection_outcome: 'selected',
      to_recipient_id: null,
      to_recipient_candidate_id: `rcp_candidate_${bankCode}_${account.slice(-4)}`,
    });
  };

  const cancel = () => {
    if (!inputRequestId || outcome) return;
    setOutcome('cancelled');
    void submitInput(inputRequestId, {
      recipient_selection_outcome: 'cancelled',
      to_recipient_id: null,
      to_recipient_candidate_id: null,
    });
  };

  if (outcome === 'cancelled') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <X className="h-3.5 w-3.5" />
        송금을 취소했어요.
      </div>
    );
  }
  if (outcome === 'selected') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        받는 분을 선택했어요.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <p className="mb-3 text-sm font-semibold text-foreground">
        {a.title ?? '받는 분을 선택해 주세요.'}
      </p>

      {mode === 'initial' ? (
        <>
          <div className="space-y-2">
            {recent.map((recipient) => (
              <button
                key={recipient.to_recipient_id}
                type="button"
                onClick={() => selectRecent(recipient)}
                className="flex w-full items-center justify-between gap-3 rounded-2xl border border-border p-3 text-left transition hover:bg-muted/30"
              >
                <span className="text-sm font-medium text-foreground">
                  {recipient.name}
                </span>
                <span className="text-xs text-muted-foreground">
                  {recipient.bank_name} · {recipient.masked_account_number}
                </span>
              </button>
            ))}
            {recent.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                최근 송금한 수취인이 없어요.
              </p>
            ) : null}
          </div>

          <div className="mt-3 flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => setMode('manual')}
              className="rounded-full border border-border px-4 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/40"
            >
              새 계좌 입력
            </button>
            <button
              type="button"
              onClick={cancel}
              className="rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/40"
            >
              취소
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="space-y-2">
            <select
              value={bankCode}
              onChange={(event) => setBankCode(event.target.value)}
              className="w-full rounded-xl border border-border bg-input-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
            >
              <option value="">은행 선택</option>
              {BANK_OPTIONS.map((bank) => (
                <option key={bank} value={bank}>
                  {bank}
                </option>
              ))}
            </select>
            <input
              inputMode="numeric"
              value={account}
              onChange={(event) =>
                setAccount(event.target.value.replace(/[^\d]/g, ''))
              }
              placeholder="계좌번호 입력"
              className="w-full rounded-xl border border-border bg-input-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
            />
          </div>
          <div className="mt-3 flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => setMode('initial')}
              className="rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/40"
            >
              뒤로
            </button>
            <button
              type="button"
              onClick={submitManual}
              disabled={!bankCode || !account}
              className="rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground transition disabled:opacity-40"
            >
              확인
            </button>
          </div>
        </>
      )}
    </div>
  );
};
