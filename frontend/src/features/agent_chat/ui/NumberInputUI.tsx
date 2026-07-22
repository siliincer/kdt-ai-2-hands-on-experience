import { useState } from 'react';

import { useSubmitInput } from '../model/submitInputContext';
import { won } from '../utils/format';

import { OutcomeChip } from './OutcomeChip';
import {
  HITL_ACTIONS_ROW,
  HITL_BTN_PRIMARY,
  HITL_BTN_SECONDARY,
  HITL_CARD,
  HITL_INPUT,
} from './uiStyles';

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
    return <OutcomeChip variant="cancel">금액 입력을 취소했어요.</OutcomeChip>;
  }
  if (outcome === 'submitted') {
    return (
      <OutcomeChip variant="success">{won(amount)}을 입력했어요.</OutcomeChip>
    );
  }

  return (
    <div className={HITL_CARD}>
      <p className="text-sm font-semibold text-foreground">
        {a.title ?? '금액을 입력해 주세요.'}
      </p>
      <div className="mt-3 flex items-center gap-2">
        <input
          inputMode="numeric"
          value={raw ? amount.toLocaleString() : ''}
          onChange={(event) => setRaw(event.target.value)}
          placeholder="0"
          className={`${HITL_INPUT} text-right`}
        />
        <span className="text-sm text-muted-foreground">원</span>
      </div>

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
