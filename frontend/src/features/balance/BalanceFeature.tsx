import { useState } from 'react';
import { useNavigate } from 'react-router';

import { NAVY } from '@/shared/constants/color';
import { F, M } from '@/shared/constants/font';

import { accounts, ALL_TX } from '@/features/mockData/mockData';

function AccountDetailCard({
  accountId,
  onNavigate,
}: {
  accountId: number;
  onNavigate: (path: string) => void;
}) {
  const account = accounts.find((item) => item.id === accountId);
  if (!account) return null;

  const recent = ALL_TX.filter((tx) => tx.month === '2025-06').slice(0, 4);

  return (
    <div>
      <div
        className="mb-3 rounded-3xl p-4 text-white"
        style={{
          background: 'linear-gradient(135deg,#0F1E3D 0%,#1a3a6b 100%)',
        }}
      >
        <p className="text-xs opacity-80" style={{ fontFamily: F }}>
          {account.bank} · {account.alias} ···{account.tail}
        </p>
        <p
          className="mt-3 text-2xl font-bold"
          style={{ fontFamily: "'DM Sans',sans-serif" }}
        >
          {account.balance.toLocaleString()}원
        </p>
      </div>
      <div className="mb-4 grid grid-cols-4 gap-2">
        {['입금', '출금', '이체', '상세'].map((label) => (
          <button
            key={label}
            type="button"
            onClick={
              label === '이체' ? () => onNavigate('/transfer') : undefined
            }
            className="rounded-2xl bg-slate-100 py-2 text-[10px] font-medium text-slate-700 hover:opacity-90"
            style={{ fontFamily: F }}
          >
            {label}
          </button>
        ))}
      </div>
      <p
        className="mb-3 text-xs font-semibold"
        style={{ color: '#6B7A99', fontFamily: F }}
      >
        최근 거래
      </p>
      <div className="space-y-3">
        {recent.map((tx) => (
          <div
            key={tx.id}
            className="flex items-center gap-2 rounded-3xl border border-slate-200 px-3 py-3"
          >
            <span className="text-sm">{tx.emoji}</span>
            <div className="flex-1 min-w-0">
              <p
                className="truncate text-xs font-medium"
                style={{ color: NAVY, fontFamily: F }}
              >
                {tx.name}
              </p>
              <p
                className="text-[10px] text-slate-500"
                style={{ fontFamily: M }}
              >
                {tx.date}
              </p>
            </div>
            <p
              className="text-xs font-bold"
              style={{
                color: tx.type === 'in' ? '#52C41A' : NAVY,
                fontFamily: M,
              }}
            >
              {tx.type === 'in' ? '+' : ''}
              {Math.abs(tx.amount).toLocaleString()}원
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function BalanceCard({
  onSelectAccount,
  onNavigate,
}: {
  onSelectAccount: (id: number) => void;
  onNavigate: (path: string) => void;
}) {
  const total = accounts.reduce((sum, item) => sum + item.balance, 0);

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg">💳</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          내 자산 현황
        </p>
      </div>
      <p
        className="text-2xl font-bold"
        style={{ color: NAVY, fontFamily: "'DM Sans',sans-serif" }}
      >
        {total.toLocaleString()}원
      </p>
      <p className="mb-4 text-xs text-slate-500" style={{ fontFamily: F }}>
        총 자산
      </p>
      <div className="mb-4 space-y-3 rounded-3xl border border-slate-200 p-3">
        {accounts.map((account) => (
          <button
            key={account.id}
            type="button"
            onClick={() => onSelectAccount(account.id)}
            className="w-full rounded-3xl border border-slate-200 p-3 text-left hover:bg-slate-50"
            style={{ color: NAVY, fontFamily: F }}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-sm font-bold text-white"
                  style={{ background: account.color }}
                >
                  {account.bank[0]}
                </div>
                <div>
                  <p className="text-xs font-medium">{account.bank}</p>
                  <p className="text-[10px] text-slate-500">
                    ···{account.tail}
                  </p>
                </div>
              </div>
              <div>
                <p className="text-sm font-bold" style={{ fontFamily: M }}>
                  {account.balance.toLocaleString()}원
                </p>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onNavigate('/transfer');
                  }}
                  className="mt-2 rounded-full border border-emerald-200 px-3 py-1 text-[10px] font-medium text-emerald-700"
                  style={{ fontFamily: F }}
                >
                  이체
                </button>
              </div>
            </div>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onNavigate('/transactions')}
          className="rounded-full border border-emerald-200 px-3 py-2 text-[10px] font-medium text-emerald-700"
          style={{ fontFamily: F }}
        >
          거래내역 보기
        </button>
        <button
          type="button"
          onClick={() => onNavigate('/bill')}
          className="rounded-full border border-emerald-200 px-3 py-2 text-[10px] font-medium text-emerald-700"
          style={{ fontFamily: F }}
        >
          카드 청구서
        </button>
        <button
          type="button"
          onClick={() => onNavigate('/transfer')}
          className="rounded-full border border-emerald-200 px-3 py-2 text-[10px] font-medium text-emerald-700"
          style={{ fontFamily: F }}
        >
          계좌 이체
        </button>
      </div>
    </div>
  );
}

export default function BalanceFeature() {
  const navigate = useNavigate();
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(
    null,
  );

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">잔액 조회</h2>
          <p className="mt-1 text-sm text-slate-400">
            전체 자산과 계좌 세부 정보를 확인하고, 바로 이체할 수 있습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSelectedAccountId(selectedAccountId ? null : null)}
          className="rounded-2xl border border-slate-600 px-4 py-2 text-sm text-slate-200 transition hover:bg-slate-900"
        >
          {selectedAccountId ? '뒤로' : '전체'}
        </button>
      </div>
      {selectedAccountId ? (
        <AccountDetailCard
          accountId={selectedAccountId}
          onNavigate={navigate}
        />
      ) : (
        <BalanceCard
          onSelectAccount={setSelectedAccountId}
          onNavigate={navigate}
        />
      )}
    </div>
  );
}
