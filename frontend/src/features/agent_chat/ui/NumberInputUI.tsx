import { useState } from 'react';

import { Check, X } from 'lucide-react';

import { useSubmitInput } from '../model/submitInputContext';

import type { NumberInputArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * need_input(number_input) 툴 파트 렌더러 (HITL, 계약 3.4).
 * 송금 금액을 입력받고, 제출/취소로 useSubmitInput → POST /agent/input.
 * 잔액·한도·정책은 Backend 가 Prepare/Execute 에서 검증한다(FE 는 형식만).
 */
export const NumberInputUI: ToolCallMessagePartComponent = ({ args }) => {
  const submitInput = useSubmitInput();
  const a = (args ?? {}) as NumberInputArgs;
  const inputRequestId = a.inputRequestId;
  const min = a.min ?? 1;

  const [raw, setRaw] = useState('');
  const [outcome, setOutcome] = useState<'submitted' | 'cancelled' | null>(
    null,
  );

  const amount = Number(raw.replace(/[^\d]/g, ''));
  const canSubmit = Number.isFinite(amount) && amount >= min;

  const respond = (next: 'submitted' | 'cancelled') => {
    if (!inputRequestId || outcome) return;
    if (next === 'submitted' && !canSubmit) return;
    setOutcome(next);
    void submitInput(
      inputRequestId,
      next === 'submitted'
        ? { amount_input_outcome: 'submitted', amount }
        : { amount_input_outcome: 'cancelled', amount: null },
    );
  };

  if (outcome === 'cancelled') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <X className="h-3.5 w-3.5" />
        금액 입력을 취소했어요.
      </div>
    );
  }
  if (outcome === 'submitted') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        {amount.toLocaleString()}원을 입력했어요.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <p className="text-sm font-semibold text-foreground">
        {a.title ?? '금액을 입력해 주세요.'}
      </p>
      <div className="mt-3 flex items-center gap-2">
        <input
          inputMode="numeric"
          value={raw ? amount.toLocaleString() : ''}
          onChange={(event) => setRaw(event.target.value)}
          placeholder="0"
          className="w-full rounded-xl border border-border bg-input-background px-3 py-2 text-right text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
        />
        <span className="text-sm text-muted-foreground">원</span>
      </div>

      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => respond('cancelled')}
          className="rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/40"
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => respond('submitted')}
          disabled={!canSubmit}
          className="rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground transition disabled:opacity-40"
        >
          확인
        </button>
      </div>
    </div>
  );
};
