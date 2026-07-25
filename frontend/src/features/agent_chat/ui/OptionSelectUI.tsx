import { useState } from 'react';

import { useSubmitInput } from '../model/submitInputContext';

import { OutcomeChip } from './OutcomeChip';
import {
  HITL_ACTIONS_ROW,
  HITL_BTN_PILL,
  HITL_BTN_SECONDARY,
  HITL_CARD,
} from './uiStyles';

import type { OptionItem, OptionSelectArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * need_input(option_select) 툴 파트 렌더러 (HITL, 계약 3.6).
 * 정해진 Enum 중 하나를 선택받아 useSubmitInput → POST /agent/input.
 * 제출값은 {option_selection_outcome, option} 형태로 보낸다.
 * 계약의 actions 에 cancel 이 있으면 취소 버튼을 노출해, 사용자가 후보를
 * 고르지 않고도 대화를 이어갈 수 있게 한다(모호한 요청은 실패가 아니라
 * 사용자 확인으로 이어가는 정상 흐름).
 */
export const OptionSelectUI: ToolCallMessagePartComponent = ({ args }) => {
  const submitInput = useSubmitInput();
  const a = (args ?? {}) as OptionSelectArgs;
  const inputRequestId = a.inputRequestId;
  const options = a.options ?? [];
  const canCancel = a.actions?.includes('cancel') ?? false;

  const [outcome, setOutcome] = useState<'selected' | 'cancelled' | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);

  const respond = (value: string) => {
    if (!inputRequestId || outcome) return;
    setOutcome('selected');
    setChosen(value);
    void submitInput(inputRequestId, {
      option_selection_outcome: 'selected',
      option: value,
    });
  };

  const cancel = () => {
    if (!inputRequestId || outcome) return;
    setOutcome('cancelled');
    void submitInput(inputRequestId, {
      option_selection_outcome: 'cancelled',
      option: null,
    });
  };

  if (outcome === 'cancelled') {
    return <OutcomeChip variant="cancel">업무 선택을 취소했어요.</OutcomeChip>;
  }
  if (outcome === 'selected') {
    const label = options.find((o) => o.value === chosen)?.label ?? chosen;
    return <OutcomeChip variant="success">{label}</OutcomeChip>;
  }

  return (
    <div className={HITL_CARD}>
      <p className="mb-3 text-sm font-semibold text-foreground">
        {a.title ?? '선택해 주세요.'}
      </p>
      <div className="flex flex-wrap gap-2">
        {options.map((option: OptionItem) => (
          <button
            key={option.value}
            type="button"
            onClick={() => respond(option.value)}
            className={HITL_BTN_PILL}
          >
            {option.label}
          </button>
        ))}
      </div>
      {canCancel ? (
        <div className={HITL_ACTIONS_ROW}>
          <button type="button" onClick={cancel} className={HITL_BTN_SECONDARY}>
            취소
          </button>
        </div>
      ) : null}
    </div>
  );
};
