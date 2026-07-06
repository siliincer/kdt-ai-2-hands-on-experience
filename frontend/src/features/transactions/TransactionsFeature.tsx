import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Bell, X, ChevronDown, ChevronUp, Tag } from 'lucide-react';

import { NAVY, MINT, GRAY_BG } from '@/shared/constants/color';
import { F, M } from '@/shared/constants/font';

import { CATS, ALL_TX_ITEM as ALL_TX } from '@/features/mockData/mockData';

import type { TxItem } from '@/shared/types/interface';

function detectRecurring(transactions: TxItem[]) {
  const groups: Record<string, Set<string>> = {};
  transactions
    .filter((tx) => tx.type === 'out')
    .forEach((tx) => {
      const key = `${tx.name}__${Math.abs(tx.amount)}__${tx.day}`;
      if (!groups[key]) groups[key] = new Set();
      groups[key].add(tx.month);
    });

  return Object.entries(groups)
    .filter(([, months]) => months.size >= 2)
    .map(([key]) => {
      const [name, amount, day] = key.split('__');
      return { name, amount: Number(amount), day: Number(day) };
    });
}

function CatBadge({
  cat,
  onEdit,
}: {
  cat: string;
  onEdit: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState('');

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium"
        style={{ background: '#EFEFEF', color: '#6B7A99', fontFamily: F }}
      >
        <Tag size={9} />
        {cat}
      </button>
      {open ? (
        <div className="absolute left-0 top-full z-10 mt-2 w-60 rounded-2xl border border-slate-200 bg-white p-3 shadow-lg">
          <div className="grid grid-cols-4 gap-1 mb-2">
            {CATS.map((category) => (
              <button
                key={category}
                type="button"
                onClick={() => {
                  onEdit(category);
                  setOpen(false);
                }}
                className="rounded py-1 text-[10px] font-medium"
                style={{
                  background: cat === category ? MINT : GRAY_BG,
                  color: cat === category ? NAVY : '#6B7A99',
                  fontFamily: F,
                }}
              >
                {category}
              </button>
            ))}
          </div>
          <div className="flex gap-1">
            <input
              value={custom}
              onChange={(event) => setCustom(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && custom) {
                  onEdit(custom);
                  setOpen(false);
                  setCustom('');
                }
              }}
              className="flex-1 rounded px-2 py-1 text-[10px] outline-none"
              style={{ background: GRAY_BG, color: NAVY, fontFamily: F }}
              placeholder="직접 입력..."
            />
            {custom ? (
              <button
                type="button"
                onClick={() => {
                  onEdit(custom);
                  setOpen(false);
                  setCustom('');
                }}
                className="rounded px-2 text-[10px] font-medium"
                style={{ background: MINT, color: NAVY, fontFamily: F }}
              >
                ✓
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </span>
  );
}

function TransactionsCard() {
  const months = ['2025-06', '2025-05', '2025-04', '2025-03', '2025-02'];
  const labels: Record<string, string> = {
    '2025-06': '6월',
    '2025-05': '5월',
    '2025-04': '4월',
    '2025-03': '3월',
    '2025-02': '2월',
  };

  const [selectedMonth, setSelectedMonth] = useState('2025-06');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [txCategories, setTxCategories] = useState<Record<number, string>>({});
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [toasts, setToasts] = useState<string[]>([]);

  const currentTransactions = ALL_TX.filter(
    (tx) => tx.month === selectedMonth,
  ).sort((a, b) => b.day - a.day);
  const recurring = detectRecurring(ALL_TX);
  const suggestions = recurring.filter((recurringItem) => {
    const found = currentTransactions.find(
      (tx) =>
        tx.name === recurringItem.name &&
        Math.abs(tx.amount) === recurringItem.amount &&
        tx.day === recurringItem.day,
    );
    if (!found) return false;
    return (
      (txCategories[found.id] || found.category) !== '고정비' &&
      !dismissed.includes(recurringItem.name)
    );
  });

  const registerFixedCost = (item: {
    name: string;
    amount: number;
    day: number;
  }) => {
    ALL_TX.filter(
      (tx) =>
        tx.name === item.name &&
        Math.abs(tx.amount) === item.amount &&
        tx.day === item.day,
    ).forEach((tx) =>
      setTxCategories((prev) => ({ ...prev, [tx.id]: '고정비' })),
    );

    setDismissed((prev) => [...prev, item.name]);
    const message = `${item.name}가(이) 고정비로 등록되었습니다 ✓`;
    setToasts((prev) => [...prev, message]);
    setTimeout(
      () => setToasts((prev) => prev.filter((toast) => toast !== message)),
      3000,
    );
  };

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">📋</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          거래 내역
        </p>
      </div>

      <div className="mb-3 flex gap-1.5 overflow-x-auto pb-1">
        {months.map((month) => (
          <button
            key={month}
            type="button"
            onClick={() => {
              setSelectedMonth(month);
              setExpandedId(null);
            }}
            className="shrink-0 rounded-full px-3 py-1 text-[10px] font-medium"
            style={{
              background: selectedMonth === month ? NAVY : '#E8EDF5',
              color: selectedMonth === month ? '#fff' : '#6B7A99',
              fontFamily: F,
            }}
          >
            {labels[month]}
          </button>
        ))}
      </div>

      {toasts.map((toast) => (
        <div
          key={toast}
          className="mb-2 rounded-xl px-3 py-2 text-[10px] font-medium"
          style={{
            background: `${MINT}15`,
            border: `1px solid ${MINT}30`,
            color: MINT,
            fontFamily: F,
          }}
        >
          {toast}
        </div>
      ))}

      {suggestions.length > 0 ? (
        <div className="mb-3 overflow-hidden rounded-2xl bg-emerald-50 border border-emerald-200">
          <div className="flex items-center justify-between px-3 py-2">
            <div className="flex items-center gap-1.5">
              <Bell size={13} color={MINT} />
              <p
                className="text-xs font-semibold"
                style={{ color: NAVY, fontFamily: F }}
              >
                고정비 제안
              </p>
            </div>
            <button
              type="button"
              onClick={() =>
                setDismissed((prev) => [
                  ...prev,
                  ...suggestions.map((item) => item.name),
                ])
              }
            >
              <X size={13} color="#6B7A99" />
            </button>
          </div>
          {suggestions.map((item) => (
            <div
              key={item.name}
              className="flex flex-col gap-2 border-t px-3 py-2"
              style={{ borderColor: `${MINT}30` }}
            >
              <p className="text-[10px]" style={{ color: NAVY, fontFamily: F }}>
                {item.name}가(이) 고정비로 등록 가능한 거래입니다. 매월{' '}
                {item.day}일에 {item.amount.toLocaleString()}원씩 발생합니다.
              </p>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => registerFixedCost(item)}
                  className="rounded-xl bg-emerald-500 px-2 py-1 text-[10px] font-semibold text-emerald-950"
                  style={{ fontFamily: F }}
                >
                  고정비 등록
                </button>
                <button
                  type="button"
                  onClick={() => setDismissed((prev) => [...prev, item.name])}
                  className="rounded-xl bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-600"
                  style={{ fontFamily: F }}
                >
                  닫기
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <div>
        {currentTransactions.map((tx) => {
          const category = txCategories[tx.id] || tx.category;
          const isExpanded = expandedId === tx.id;

          return (
            <div
              key={tx.id}
              className="border-b"
              style={{ borderColor: 'rgba(15,30,61,0.06)' }}
            >
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : tx.id)}
                className="w-full flex items-center gap-2 py-2.5 text-left"
              >
                <span className="text-sm shrink-0">{tx.emoji}</span>
                <div className="min-w-0 flex-1">
                  <p
                    className="truncate text-xs font-medium"
                    style={{ color: NAVY, fontFamily: F }}
                  >
                    {tx.name}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <p
                      className="text-[10px] text-slate-500"
                      style={{ fontFamily: M }}
                    >
                      {tx.date}
                    </p>
                    {tx.type === 'out' ? (
                      <CatBadge
                        cat={category}
                        onEdit={(value) =>
                          setTxCategories((prev) => ({
                            ...prev,
                            [tx.id]: value,
                          }))
                        }
                      />
                    ) : null}
                  </div>
                </div>
                <p
                  className="shrink-0 text-xs font-bold"
                  style={{
                    color: tx.type === 'in' ? '#52C41A' : NAVY,
                    fontFamily: M,
                  }}
                >
                  {tx.type === 'in' ? '+' : ''}
                  {Math.abs(tx.amount).toLocaleString()}원
                </p>
                {isExpanded ? (
                  <ChevronUp size={13} color="#6B7A99" />
                ) : (
                  <ChevronDown size={13} color="#6B7A99" />
                )}
              </button>
              {isExpanded ? (
                <div
                  className="mx-2 mb-2 rounded-2xl bg-white px-4 py-2 text-[10px]"
                  style={{ border: '1px solid rgba(15,30,61,0.08)' }}
                >
                  <div className="flex justify-between">
                    <span style={{ color: '#6B7A99', fontFamily: F }}>
                      거래처
                    </span>
                    <span style={{ color: NAVY, fontFamily: F }}>
                      {tx.name}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span style={{ color: '#6B7A99', fontFamily: F }}>
                      카테고리
                    </span>
                    <CatBadge
                      cat={category}
                      onEdit={(value) =>
                        setTxCategories((prev) => ({ ...prev, [tx.id]: value }))
                      }
                    />
                  </div>
                  <div className="flex justify-between">
                    <span style={{ color: '#6B7A99', fontFamily: F }}>
                      날짜/시간
                    </span>
                    <span style={{ color: NAVY, fontFamily: M }}>
                      {tx.date}
                    </span>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function TransactionsFeature() {
  const navigate = useNavigate();

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">거래 내역</h2>
          <p className="mt-1 text-sm text-slate-400">
            최근 거래 기록과 지출 흐름을 자세히 확인해보세요.
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
      <TransactionsCard />
    </div>
  );
}
