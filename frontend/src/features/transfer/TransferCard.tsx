import { Check, Clock } from 'lucide-react';

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

import type { TransferCardProps } from '@/features/transfer/types/interface.ts';

export function TransferCard({
  prefill,
  onConfirm,
  onCancel,
  submitLabel = '송금하기 →',
  disabled = false,
}: TransferCardProps) {
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

  // TODO: done 변수는 차후 지우기
  if (done) {
    return (
      <div className="flex flex-col items-center gap-2 py-4">
        {/* 완료 아이콘 배경은 시스템 파괴/경고와 대비되는 에메랄드/차트 컬러 매핑 */}
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-chart-2">
          <Check size={22} color="var(--card)" strokeWidth={3} />
        </div>
        <p
          className="text-sm font-semibold"
          style={{ color: 'var(--foreground)', fontFamily: F }}
        >
          송금이 완료되었습니다 ✓
        </p>
        <p
          className="text-xs"
          style={{ color: 'var(--muted-foreground)', fontFamily: F }}
        >
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
          className="text-sm font-semibold text-foreground"
          style={{ fontFamily: F }}
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
            style={{
              color: 'var(--foreground)',
              fontFamily: F,
              borderColor: 'var(--accent)',
            }}
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
            className="overflow-hidden rounded-2xl bg-card shadow-sm"
            style={{ border: '1px solid var(--border)' }}
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
                  color:
                    bank === bankName ? 'var(--accent)' : 'var(--foreground)',
                  fontFamily: F,
                  fontWeight: bank === bankName ? 600 : 400,
                  borderColor: 'var(--border)',
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
            className="w-full border-b-2 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
            style={{ fontFamily: M, borderColor: 'var(--accent)' }}
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
            className="w-full border-b-2 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
            style={{ fontFamily: M, borderColor: 'var(--accent)' }}
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
            <p
              className="mt-2 text-xs"
              style={{ color: 'var(--accent)', fontFamily: F }}
            >
              {kor(amtNum)}
            </p>
          ) : null}
          <div className="mt-2 flex gap-1.5">
            {['10,000', '50,000', '100,000'].map((amount) => (
              <button
                key={amount}
                type="button"
                // 입력창 blur→편집 종료를 막아 프리셋 클릭이 정상 반영되게 한다
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setAmtRaw(amount.replace(/,/g, ''))}
                className="flex-1 rounded-lg bg-secondary py-1 text-[10px] font-medium text-secondary-foreground"
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
                className="flex-1 rounded-lg py-1.5 text-[10px] font-medium transition-colors"
                style={{
                  background:
                    timeOpt === option.key ? 'var(--primary)' : 'var(--muted)',
                  color:
                    timeOpt === option.key
                      ? 'var(--primary-foreground)'
                      : 'var(--foreground)',
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
              className="w-full rounded-lg border border-transparent bg-input-background px-3 py-2 text-xs text-foreground outline-none"
              style={{ fontFamily: M }}
              value={schedDT}
              onChange={(event) => setSchedDT(event.target.value)}
            />
          ) : null}
        </div>
      </ERow>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={onCancel}
          className="flex-1 rounded-xl border border-border bg-transparent py-2.5 text-sm text-foreground hover:bg-muted/30 transition-colors disabled:opacity-50"
          style={{ fontFamily: F }}
        >
          취소
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            if (onConfirm) {
              onConfirm({
                name,
                bank,
                account,
                amount: amtRaw,
                time: timeOpt === 'now' ? '지금 바로' : schedDT,
              });
            } else {
              // TODO: transfer card 자체적으로 성공 UI를 띄우는게 아니고
              // onConfirm으로 서버에 전송 후 나중에 성공 메시지를 따로 받는다.
              // agent 연결 후 done변수는 제거한다.
              setDone(true);
            }
          }}
          className="flex-1 rounded-xl bg-chart-1 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
          style={{ fontFamily: F }}
        >
          {submitLabel}
        </button>
      </div>
    </div>
  );
}
