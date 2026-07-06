import { Check, Clock } from 'lucide-react';

import { NAVY, MINT, GRAY_BG } from '@/shared/constants/color';
import { M, F } from '@/shared/constants/font';
import { BANKS } from '@/features/mockData/mockData';

import {
  fmtAmt,
  parseAmtInput,
  kor,
  formatScheduled,
  parseContactText,
} from '@/shared/lib/utils';

import { useState, type ClipboardEvent } from 'react';

import { ERow } from './ERow';

interface TransferPrefill {
  name?: string;
  bank?: string;
  account?: string;
  amtRaw?: string;
  scheduled?: string;
}

export function TransferCard({ prefill }: { prefill?: TransferPrefill }) {
  const [name, setName] = useState(prefill?.name ?? '');
  const [bank, setBank] = useState(prefill?.bank ?? '신한은행');
  const [account, setAccount] = useState(prefill?.account ?? '');
  const [amtRaw, setAmtRaw] = useState(prefill?.amtRaw ?? '');
  const [timeOpt, setTimeOpt] = useState<'now' | 'schedule'>(
    prefill?.scheduled ? 'schedule' : 'now',
  );
  const [schedDT, setSchedDT] = useState(prefill?.scheduled ?? '');
  const [editingField, setEditingField] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const amtNum = Number(amtRaw) || 0;

  const handlePaste = (event: ClipboardEvent) => {
    const text = event.clipboardData.getData('text');
    const parsed = parseContactText(text);
    if (parsed.name || parsed.bank || parsed.account) {
      event.preventDefault();
      if (parsed.name) setName(parsed.name);
      if (parsed.bank) setBank(parsed.bank);
      if (parsed.account) setAccount(parsed.account);
    }
  };

  if (done) {
    return (
      <div className="flex flex-col items-center gap-2 py-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500">
          <Check size={22} color="#fff" strokeWidth={3} />
        </div>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          송금이 완료되었습니다 ✓
        </p>
        <p className="text-xs" style={{ color: '#6B7A99', fontFamily: F }}>
          {name}님께 {amtNum.toLocaleString()}원 전송됨
        </p>
      </div>
    );
  }

  return (
    <div onPaste={handlePaste}>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">💸</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          송금 확인
        </p>
      </div>

      <ERow
        label="받는 사람"
        value={name}
        isEditing={editingField === 'name'}
        onToggle={() =>
          setEditingField(editingField === 'name' ? null : 'name')
        }
      >
        <div className="pl-21 pr-2">
          <input
            autoFocus
            className="w-full border-b-2 bg-transparent text-sm outline-none"
            style={{ color: NAVY, fontFamily: F, borderColor: MINT }}
            value={name}
            onChange={(event) => setName(event.target.value)}
            onBlur={() => setEditingField(null)}
            onKeyDown={(event) =>
              event.key === 'Enter' && setEditingField(null)
            }
          />
        </div>
      </ERow>

      <ERow
        label="은행"
        value={bank}
        isEditing={editingField === 'bank'}
        onToggle={() =>
          setEditingField(editingField === 'bank' ? null : 'bank')
        }
      >
        <div className="pl-21 pr-2">
          <div
            className="overflow-hidden rounded-2xl bg-white shadow-sm"
            style={{ border: '1px solid rgba(15,30,61,0.08)' }}
          >
            {BANKS.map((bankName) => (
              <button
                key={bankName}
                type="button"
                onClick={() => {
                  setBank(bankName);
                  setEditingField(null);
                }}
                className="w-full border-b px-3 py-2 text-left text-xs hover:opacity-80 last:border-0"
                style={{
                  color: bank === bankName ? MINT : NAVY,
                  fontFamily: F,
                  fontWeight: bank === bankName ? 600 : 400,
                  borderColor: 'rgba(15,30,61,0.05)',
                }}
              >
                {bankName}
              </button>
            ))}
          </div>
        </div>
      </ERow>

      <ERow
        label="계좌번호"
        value={account}
        isEditing={editingField === 'account'}
        onToggle={() =>
          setEditingField(editingField === 'account' ? null : 'account')
        }
        mono
      >
        <div className="pl-21 pr-2">
          <input
            autoFocus
            className="w-full border-b-2 bg-transparent text-sm text-slate-50 placeholder:text-slate-500 outline-none"
            style={{ fontFamily: M, borderColor: MINT }}
            placeholder="계좌번호 입력"
            value={account}
            onChange={(event) => setAccount(event.target.value)}
            onBlur={() => setEditingField(null)}
            onKeyDown={(event) =>
              event.key === 'Enter' && setEditingField(null)
            }
            inputMode="numeric"
          />
        </div>
      </ERow>

      <ERow
        label="금액"
        value={amtNum > 0 ? `${amtNum.toLocaleString()}원` : ''}
        isEditing={editingField === 'amount'}
        onToggle={() =>
          setEditingField(editingField === 'amount' ? null : 'amount')
        }
        mono
      >
        <div className="pl-21 pr-2">
          <input
            autoFocus
            className="w-full border-b-2 bg-transparent text-sm text-slate-50 placeholder:text-slate-500 outline-none"
            style={{ fontFamily: M, borderColor: MINT }}
            inputMode="numeric"
            placeholder="0"
            value={fmtAmt(amtRaw)}
            onChange={(event) => setAmtRaw(parseAmtInput(event.target.value))}
            onBlur={() => setEditingField(null)}
            onKeyDown={(event) =>
              event.key === 'Enter' && setEditingField(null)
            }
          />
          {amtNum > 0 ? (
            <p className="mt-2 text-xs" style={{ color: MINT, fontFamily: F }}>
              {kor(amtNum)}
            </p>
          ) : null}
          <div className="mt-2 flex gap-1.5">
            {['10,000', '50,000', '100,000'].map((amount) => (
              <button
                key={amount}
                type="button"
                onClick={() => setAmtRaw(amount.replace(/,/g, ''))}
                className="flex-1 rounded-lg bg-slate-100 py-1 text-[10px] font-medium text-slate-700"
                style={{ fontFamily: F }}
              >
                {amount}
              </button>
            ))}
          </div>
        </div>
      </ERow>

      <ERow
        label="시간"
        value={
          timeOpt === 'now'
            ? '지금 바로'
            : schedDT
              ? formatScheduled(schedDT)
              : '날짜/시간 선택'
        }
        isEditing={editingField === 'time'}
        onToggle={() =>
          setEditingField(editingField === 'time' ? null : 'time')
        }
      >
        <div className="pl-21 pr-2 space-y-2">
          <div className="flex gap-2">
            {[
              { key: 'now' as const, label: '지금 바로' },
              { key: 'schedule' as const, label: '예약 송금' },
            ].map((option) => (
              <button
                key={option.key}
                type="button"
                onClick={() => setTimeOpt(option.key)}
                className="flex-1 rounded-lg py-1.5 text-[10px] font-medium"
                style={{
                  background: timeOpt === option.key ? NAVY : GRAY_BG,
                  color: timeOpt === option.key ? '#fff' : NAVY,
                  fontFamily: F,
                }}
              >
                <span className="inline-flex items-center gap-1">
                  <Clock size={11} />
                  {option.label}
                </span>
              </button>
            ))}
          </div>
          {timeOpt === 'schedule' ? (
            <input
              type="datetime-local"
              className="w-full rounded-lg border border-transparent bg-slate-100 px-3 py-2 text-xs outline-none"
              style={{ color: NAVY, fontFamily: M }}
              value={schedDT}
              onChange={(event) => setSchedDT(event.target.value)}
            />
          ) : null}
        </div>
      </ERow>

      <p className="mt-3 text-[10px] text-slate-400" style={{ fontFamily: F }}>
        💡 클립보드 텍스트 붙여넣기 자동인식 지원
      </p>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          className="flex-1 rounded-xl border border-slate-300 py-2.5 text-sm text-slate-200 hover:bg-white/5"
          style={{ fontFamily: F }}
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => setDone(true)}
          className="flex-1 rounded-xl bg-emerald-500 py-2.5 text-sm font-semibold text-white hover:opacity-90"
          style={{ fontFamily: F }}
        >
          송금하기 →
        </button>
      </div>
    </div>
  );
}
