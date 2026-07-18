import { useState } from 'react';

import { Check, X } from 'lucide-react';

import { useSubmitInput } from '../model/submitInputContext';

import type { AccountCardItem, AccountCardListArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * need_input(account_card_list) 툴 파트 렌더러 (HITL, 계약 3.3).
 * 계좌 후보를 선택 가능한 카드로 띄우고, 하단 선택/취소 버튼으로
 * useSubmitInput → POST /agent/input 하여 에이전트를 재개한다.
 *
 * 단일·복수 모두 account_ids 배열로 제출한다(계약 3.3). 취소는 outcome=cancelled.
 */
export const AccountCardListUI: ToolCallMessagePartComponent = ({ args }) => {
  const submitInput = useSubmitInput();
  const a = (args ?? {}) as AccountCardListArgs;
  const accounts = a.accounts ?? [];
  const inputRequestId = a.inputRequestId;

  const [selected, setSelected] = useState<string[]>([]);
  const [outcome, setOutcome] = useState<'selected' | 'cancelled' | null>(null);

  const toggle = (accountId: string) =>
    setSelected((prev) =>
      prev.includes(accountId)
        ? prev.filter((id) => id !== accountId)
        : [...prev, accountId],
    );

  const respond = (next: 'selected' | 'cancelled') => {
    if (!inputRequestId || outcome) return;
    if (next === 'selected' && selected.length === 0) return;
    setOutcome(next);
    void submitInput(
      inputRequestId,
      next === 'selected'
        ? { account_selection_outcome: 'selected', account_ids: selected }
        : { account_selection_outcome: 'cancelled', account_ids: [] },
    );
  };

  if (outcome === 'cancelled') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <X className="h-3.5 w-3.5" />
        계좌 선택을 취소했어요.
      </div>
    );
  }

  if (outcome === 'selected') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        계좌를 선택했어요.
      </div>
    );
  }

  if (accounts.length === 0) {
    return (
      <div className="mt-2 rounded-2xl border border-border bg-card p-4 text-sm text-muted-foreground">
        선택 가능한 계좌가 없어요.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <p className="mb-3 text-sm font-semibold text-foreground">
        {a.title ?? '계좌를 선택해 주세요.'}
      </p>

      <div className="space-y-2">
        {accounts.map((account: AccountCardItem) => {
          const isSelected = selected.includes(account.account_id);
          return (
            <button
              key={account.account_id}
              type="button"
              onClick={() => toggle(account.account_id)}
              aria-pressed={isSelected}
              className={`flex w-full items-center justify-between gap-3 rounded-2xl border p-3 text-left transition ${
                isSelected
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:bg-muted/30'
              }`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {account.account_alias || account.bank_name}
                  </span>
                  {account.is_default ? (
                    <span className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] text-secondary-foreground">
                      기본
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {account.bank_name} · {account.masked_account_number}
                </p>
              </div>
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                  isSelected
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border'
                }`}
              >
                {isSelected ? <Check className="h-3 w-3" /> : null}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-4 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => respond('cancelled')}
          className="rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/40"
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => respond('selected')}
          disabled={selected.length === 0}
          className="rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground transition disabled:opacity-40"
        >
          선택 완료
        </button>
      </div>
    </div>
  );
};
