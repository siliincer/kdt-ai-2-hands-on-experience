import { useState } from 'react';
import { kor, fmtAmt, parseAmtInput } from '@/shared/lib/utils';
import { Check } from 'lucide-react';
import { NAVY, MINT } from '@/shared/constants/color';
import { F, M } from '@/shared/constants/font';

export function AutoTransferFormCard({ onDone }: { onDone: () => void }) {
  const [account, setAccount] = useState('');
  const [amtRaw, setAmtRaw] = useState('');
  const [day, setDay] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const amtNum = Number(amtRaw) || 0;

  if (submitted) {
    return (
      <div className="flex items-center gap-2 py-2">
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500 text-white">
          <Check size={12} />
        </div>
        <p className="text-sm" style={{ color: NAVY, fontFamily: F }}>
          자동 이체가 등록되었습니다 ✓
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p
          className="text-xs font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          자동 이체 등록
        </p>
        <button
          type="button"
          onClick={onDone}
          className="text-xs text-slate-500"
          style={{ fontFamily: F }}
        >
          취소
        </button>
      </div>
      <div className="space-y-3 rounded-3xl border border-slate-200 bg-slate-50 p-3">
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
            className="flex items-center gap-3 border-b border-slate-200 py-2"
          >
            <span
              className="w-18 text-xs text-slate-500"
              style={{ fontFamily: F }}
            >
              {field.label}
            </span>
            <input
              className="flex-1 border-b-2 bg-transparent text-sm outline-none"
              style={{
                color: NAVY,
                fontFamily: field.mono ? M : F,
                borderColor: MINT,
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
          className="mt-2 text-right text-[10px] text-emerald-600"
          style={{ fontFamily: F }}
        >
          {kor(amtNum)}
        </p>
      ) : null}
      <button
        type="button"
        onClick={() => setSubmitted(true)}
        className="mt-4 w-full rounded-xl bg-emerald-500 py-2.5 text-sm font-semibold text-emerald-950"
        style={{ fontFamily: F }}
      >
        등록하기
      </button>
    </div>
  );
}
