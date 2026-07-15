import { useState } from 'react';
import { kor, fmtAmt, parseAmtInput } from '@/shared/lib/utils';
import { Check } from 'lucide-react';
import { F, M } from '@/shared/constants/font';

import type { AutoTransferFormCardProps } from './types/interface';

export function AutoTransferFormCard({
  prefill,
  onConfirm,
  onCancel,
  submitLabel = '등록하기',
  disabled = false,
  onDone,
}: AutoTransferFormCardProps) {
  const [account, setAccount] = useState(prefill?.account ?? '');
  const [amtRaw, setAmtRaw] = useState(prefill?.amount ?? '');
  const [day, setDay] = useState(prefill?.day ?? '');
  const [submitted, setSubmitted] = useState(false);
  const amtNum = Number(amtRaw) || 0;

  const handleSubmit = () => {
    if (onConfirm) {
      onConfirm({ account, amount: amtRaw, day });
    } else {
      // 레거시(라우트) 경로: 자체 완료 UI 표시. agent 연동 후 제거 예정.
      setSubmitted(true);
    }
  };

  if (submitted) {
    return (
      <div className="flex items-center gap-2 py-2">
        {/* 완료 표시 배경을 차트 긍정 컬러 지표인 var(--chart-2) 매핑 */}
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-chart-2 text-card">
          <Check size={12} strokeWidth={3} />
        </div>
        <p
          className="text-sm font-semibold"
          style={{ color: 'var(--foreground)', fontFamily: F }}
        >
          자동 이체가 등록되었습니다 ✓
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p
          className="text-xs font-semibold text-foreground"
          style={{ fontFamily: F }}
        >
          자동 이체 등록
        </p>
        <button
          type="button"
          disabled={disabled}
          onClick={onCancel ?? onDone}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          style={{ fontFamily: F }}
        >
          취소
        </button>
      </div>
      <div className="space-y-3 rounded-3xl border border-border bg-secondary/30 p-3">
        {[
          {
            label: '받는 계좌',
            value: account,
            setter: setAccount,
            placeholder: '계좌번호 또는 이름',
            mono: false,
          },
          {
            label: '금액',
            value: fmtAmt(amtRaw),
            setter: (value: string) => setAmtRaw(parseAmtInput(value)),
            placeholder: '0원',
            mono: true,
          },
          {
            label: '날짜',
            value: day,
            setter: setDay,
            placeholder: '매월 ?일',
            mono: false,
          },
        ].map((field) => (
          <div
            key={field.label}
            className="flex items-center gap-3 border-b border-border py-2 last:border-0"
          >
            <span
              className="w-18 text-xs text-muted-foreground"
              style={{ fontFamily: F }}
            >
              {field.label}
            </span>
            <input
              className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/60"
              style={{
                fontFamily: field.mono ? M : F,
              }}
              placeholder={field.placeholder}
              value={field.value}
              onChange={(event) => field.setter(event.target.value)}
              inputMode={field.mono ? 'numeric' : 'text'}
            />
          </div>
        ))}
      </div>
      {amtNum > 0 ? (
        <p
          className="mt-2 text-right text-[10px]"
          style={{ color: 'var(--chart-2)', fontFamily: F }}
        >
          {kor(amtNum)}
        </p>
      ) : null}
      <button
        type="button"
        disabled={disabled}
        onClick={handleSubmit}
        className="mt-4 w-full rounded-xl bg-chart-2 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
        style={{ fontFamily: F }}
      >
        {submitLabel}
      </button>
    </div>
  );
}
