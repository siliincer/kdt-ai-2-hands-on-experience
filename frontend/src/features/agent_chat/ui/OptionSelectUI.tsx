import { useState } from 'react';

import { Check } from 'lucide-react';

import { useSubmitInput } from '../model/submitInputContext';

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
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        {label}
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <p className="mb-3 text-sm font-semibold text-foreground">
        {a.title ?? '선택해 주세요.'}
      </p>
      <div className="flex flex-wrap gap-2">
        {options.map((option: OptionItem) => (
          <button
            key={option.value}
            type="button"
            onClick={() => respond(option.value)}
            className="rounded-full border border-border px-4 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/40"
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
};
