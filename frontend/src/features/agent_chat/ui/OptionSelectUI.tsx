import { useState } from 'react';

import { useSubmitInput } from '../model/submitInputContext';

import { OutcomeChip } from './OutcomeChip';
import { HITL_BTN_PILL, HITL_CARD } from './uiStyles';

import type { OptionItem, OptionSelectArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * need_input(option_select) 툴 파트 렌더러 (HITL, 계약 3.6).
 * 정해진 Enum 중 하나를 선택받아 useSubmitInput → POST /agent/input.
 * 제출값은 {option_selection_outcome, option} 형태로 보낸다.
 */
export const OptionSelectUI: ToolCallMessagePartComponent = ({ args }) => {
  const submitInput = useSubmitInput();
  const a = (args ?? {}) as OptionSelectArgs;
  const inputRequestId = a.inputRequestId;
  const options = a.options ?? [];

  const [chosen, setChosen] = useState<string | null>(null);

  const respond = (value: string) => {
    if (!inputRequestId || chosen) return;
    setChosen(value);
    void submitInput(inputRequestId, {
      option_selection_outcome: 'selected',
      option: value,
    });
  };

  if (chosen) {
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
    </div>
  );
};
