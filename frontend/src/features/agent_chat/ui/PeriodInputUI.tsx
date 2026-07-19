import { useState } from 'react';

import { Check, X } from 'lucide-react';

import { useSubmitInput } from '../model/submitInputContext';

import type { PeriodInputArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

const PRESET_LABEL: Record<string, string> = {
  this_month: '이번 달',
  last_month: '지난 달',
  recent_1_month: '최근 1개월',
};

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** 프리셋을 [start_date, end_date] 로 변환한다(계약 3.5: FE 가 날짜로 변환). */
function presetRange(preset: string): [string, string] {
  const now = new Date();
  if (preset === 'this_month') {
    return [iso(new Date(now.getFullYear(), now.getMonth(), 1)), iso(now)];
  }
  if (preset === 'last_month') {
    return [
      iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      iso(new Date(now.getFullYear(), now.getMonth(), 0)),
    ];
  }
  // recent_1_month
  const from = new Date(now);
  from.setDate(from.getDate() - 30);
  return [iso(from), iso(now)];
}

/**
 * need_input(period_input) 툴 파트 렌더러 (HITL, 계약 3.5).
 * 프리셋 또는 직접 기간(start/end)을 선택해 정규화된 날짜로 제출한다.
 * Agent 에는 프리셋 이름이 아니라 start_date·end_date 만 전달한다.
 */
export const PeriodInputUI: ToolCallMessagePartComponent = ({ args }) => {
  const submitInput = useSubmitInput();
  const a = (args ?? {}) as PeriodInputArgs;
  const inputRequestId = a.inputRequestId;
  const presets = a.presets ?? [];

  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [outcome, setOutcome] = useState<'selected' | 'cancelled' | null>(null);

  const submit = (startDate: string, endDate: string) => {
    if (!inputRequestId || outcome) return;
    if (!startDate || !endDate) return;
    setOutcome('selected');
    void submitInput(inputRequestId, {
      period_selection_outcome: 'selected',
      start_date: startDate,
      end_date: endDate,
    });
  };

  const cancel = () => {
    if (!inputRequestId || outcome) return;
    setOutcome('cancelled');
    void submitInput(inputRequestId, {
      period_selection_outcome: 'cancelled',
      start_date: null,
      end_date: null,
    });
  };

  if (outcome === 'cancelled') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
        <X className="h-3.5 w-3.5" />
        조회를 취소했어요.
      </div>
    );
  }
  if (outcome === 'selected') {
    return (
      <div className="my-1 inline-flex items-center gap-2 rounded-full border border-chart-2/40 bg-chart-2/10 px-3 py-1.5 text-xs text-foreground">
        <Check className="h-3.5 w-3.5" />
        기간을 선택했어요.
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <p className="mb-3 text-sm font-semibold text-foreground">
        {a.title ?? '조회 기간을 선택해 주세요.'}
      </p>

      <div className="mb-3 flex flex-wrap gap-2">
        {presets.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => submit(...presetRange(preset))}
            className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/40"
          >
            {PRESET_LABEL[preset] ?? preset}
          </button>
        ))}
      </div>

      {a.manual_range ? (
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            className="flex-1 rounded-xl border border-border bg-input-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
          />
          <span className="text-xs text-muted-foreground">~</span>
          <input
            type="date"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            className="flex-1 rounded-xl border border-border bg-input-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
          />
        </div>
      ) : null}

      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={cancel}
          className="rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/40"
        >
          취소
        </button>
        {a.manual_range ? (
          <button
            type="button"
            onClick={() => submit(start, end)}
            disabled={!start || !end}
            className="rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground transition disabled:opacity-40"
          >
            확인
          </button>
        ) : null}
      </div>
    </div>
  );
};
