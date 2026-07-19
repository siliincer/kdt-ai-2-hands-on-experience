import { useState } from 'react';

import { Check, X } from 'lucide-react';

import { useSubmitInput } from '../model/submitInputContext';

import type { TextInputArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * need_input(text_input) 툴 파트 렌더러 (HITL, 계약 3.1).
 * 계좌 별칭 등 자유 텍스트를 입력받고, 하단 제출/취소 버튼으로
 * useSubmitInput → POST /agent/input 하여 에이전트를 재개한다.
 */
export const TextInputUI: ToolCallMessagePartComponent = ({ args }) => {
  const submitInput = useSubmitInput();
  const a = (args ?? {}) as TextInputArgs;
  const inputRequestId = a.inputRequestId;
  const maxLength = a.validation?.max_length;

  const [text, setText] = useState('');
  const [outcome, setOutcome] = useState<'submitted' | 'cancelled' | null>(
    null,
  );

  const trimmed = text.trim();
  const canSubmit = a.validation?.required ? trimmed.length > 0 : true;

  const respond = (next: 'submitted' | 'cancelled') => {
    if (!inputRequestId || outcome) return;
    if (next === 'submitted' && !canSubmit) return;
    setOutcome(next);
    void submitInput(
      inputRequestId,
      next === 'submitted'
        ? { alias_input_outcome: 'submitted', alias: trimmed }
        : { alias_input_outcome: 'cancelled', alias: null },
    );
  };

  if (outcome === 'cancelled') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <X className="h-3.5 w-3.5" />
        입력을 취소했어요.
      </div>
    );
  }

  if (outcome === 'submitted') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        입력을 제출했어요.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <p className="text-sm font-semibold text-foreground">
        {a.title ?? '입력해 주세요.'}
      </p>
      {a.description ? (
        <p className="mt-1 text-xs text-muted-foreground">{a.description}</p>
      ) : null}

      <input
        type="text"
        value={text}
        maxLength={maxLength}
        onChange={(event) => setText(event.target.value)}
        placeholder="내용을 입력해 주세요"
        className="mt-3 w-full rounded-xl border border-border bg-input-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
      />
      {maxLength ? (
        <p className="mt-1 text-right text-[10px] text-muted-foreground">
          {trimmed.length}/{maxLength}
        </p>
      ) : null}

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
