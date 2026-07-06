import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Check, Plus } from 'lucide-react';
import { autoTxItems } from '@/features/mockData/mockData';
import { NAVY, MINT } from '@/shared/constants/color';
import { F, M } from '@/shared/constants/font';
import { kor, fmtAmt, parseAmtInput } from '@/shared/lib/utils';

function AutoTransferFormCard({ onDone }: { onDone: () => void }) {
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

function AutoTransferCard({ onShowForm }: { onShowForm: () => void }) {
  const [toggles, setToggles] = useState(
    autoTxItems.map((item) => item.active),
  );

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">🔄</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          자동 이체 목록
        </p>
      </div>
      <div className="space-y-3">
        {autoTxItems.map((item, index) => (
          <div
            key={item.name}
            className="flex items-center justify-between rounded-3xl border border-slate-200 px-3 py-3"
          >
            <div>
              <p
                className="text-xs font-semibold"
                style={{ color: NAVY, fontFamily: F }}
              >
                {item.name}
              </p>
              <p
                className="text-[10px] text-slate-500"
                style={{ fontFamily: F }}
              >
                {item.cycle}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <p
                className="text-xs font-bold"
                style={{ color: NAVY, fontFamily: M }}
              >
                {item.amount.toLocaleString()}원
              </p>
              <button
                type="button"
                onClick={() =>
                  setToggles((prev) => {
                    const next = [...prev];
                    next[index] = !next[index];
                    return next;
                  })
                }
                className="rounded-full px-3 py-1 text-[10px] font-semibold"
                style={{
                  background: toggles[index] ? '#D1FAE5' : '#F8FAFC',
                  color: toggles[index] ? '#047857' : '#6B7280',
                  fontFamily: F,
                }}
              >
                {toggles[index] ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={onShowForm}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-200 py-2.5 text-sm font-semibold text-emerald-700"
        style={{ fontFamily: F }}
      >
        <Plus size={14} /> 자동 이체 추가
      </button>
    </div>
  );
}

export default function AutoTransferFeature() {
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">자동 이체</h2>
          <p className="mt-1 text-sm text-slate-400">
            정기 결제를 등록하고 관리할 수 있습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="rounded-2xl border border-slate-600 px-4 py-2 text-sm text-slate-200 transition hover:bg-slate-900"
        >
          홈으로
        </button>
      </div>
      {showForm ? (
        <AutoTransferFormCard onDone={() => setShowForm(false)} />
      ) : (
        <AutoTransferCard onShowForm={() => setShowForm(true)} />
      )}
    </div>
  );
}
