import { useState } from 'react';

import { useSubmitInput } from '../model/submitInputContext';

import { OutcomeChip } from './OutcomeChip';
import {
  HITL_ACTIONS_ROW,
  HITL_BTN_PRIMARY,
  HITL_BTN_SECONDARY,
  HITL_CARD,
  HITL_INPUT,
} from './uiStyles';

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
    return <OutcomeChip variant="cancel">입력을 취소했어요.</OutcomeChip>;
  }

  if (outcome === 'submitted') {
    return <OutcomeChip variant="success">입력을 제출했어요.</OutcomeChip>;
  }

  return (
    <div className={HITL_CARD}>
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
        className={`mt-3 ${HITL_INPUT}`}
      />
      {maxLength ? (
        <p className="mt-1 text-right text-[10px] text-muted-foreground">
          {trimmed.length}/{maxLength}
        </p>
      ) : null}

      <div className={HITL_ACTIONS_ROW}>
        <button
          type="button"
          onClick={() => respond('cancelled')}
          className={HITL_BTN_SECONDARY}
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => respond('submitted')}
          disabled={!canSubmit}
          className={HITL_BTN_PRIMARY}
        >
          확인
        </button>
      </div>
    </div>
  );
};
