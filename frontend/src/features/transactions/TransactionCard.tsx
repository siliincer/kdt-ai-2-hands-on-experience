import { useState } from 'react';
import { Bell, X, ChevronDown, ChevronUp } from 'lucide-react';

import { F, M } from '@/shared/constants/font';
import { ALL_TX_ITEM as ALL_TX } from '@/features/mockData/mockData';
import { detectRecurring } from '@/shared/lib/utils';

import { CatBadge } from '@/shared/ui/CatBadge';

export function TransactionsCard() {
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
          className="text-sm font-semibold text-foreground"
          style={{ fontFamily: F }}
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
            className="shrink-0 rounded-full px-3 py-1 text-[10px] font-medium transition-colors"
            style={{
              background:
                selectedMonth === month ? 'var(--primary)' : 'var(--muted)',
              color:
                selectedMonth === month
                  ? 'var(--primary-foreground)'
                  : 'var(--muted-foreground)',
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
          className="mb-2 rounded-xl px-3 py-2 text-[10px] font-medium border"
          style={{
            background: 'var(--accent)/15',
            borderColor: 'var(--accent)/30',
            color: 'var(--accent)',
            fontFamily: F,
          }}
        >
          {toast}
        </div>
      ))}

      {suggestions.length > 0 ? (
        // 고정비 제안 박스를 시스템 시맨틱 토글에 맞춘 차트 컬러(에메랄드/민트 성격) 및 변수 결합으로 보정
        <div
          className="mb-3 overflow-hidden rounded-2xl border"
          style={{
            backgroundColor: 'var(--accent)/5',
            borderColor: 'var(--accent)/30',
          }}
        >
          <div className="flex items-center justify-between px-3 py-2">
            <div className="flex items-center gap-1.5">
              <Bell size={13} color="var(--accent)" />
              <p
                className="text-xs font-semibold"
                style={{ color: 'var(--foreground)', fontFamily: F }}
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
              <X size={13} className="text-muted-foreground" />
            </button>
          </div>
          {suggestions.map((item) => (
            <div
              key={item.name}
              className="flex flex-col gap-2 border-t px-3 py-2"
              style={{ borderColor: 'var(--accent)/20' }}
            >
              <p
                className="text-[10px]"
                style={{ color: 'var(--foreground)', fontFamily: F }}
              >
                {item.name}가(이) 고정비로 등록 가능한 거래입니다. 매월{' '}
                {item.day}일에 {item.amount.toLocaleString()}원씩 발생합니다.
              </p>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => registerFixedCost(item)}
                  className="rounded-xl bg-chart-2 px-2 py-1 text-[10px] font-semibold text-primary-foreground transition-opacity hover:opacity-90"
                  style={{ fontFamily: F }}
                >
                  고정비 등록
                </button>
                <button
                  type="button"
                  onClick={() => setDismissed((prev) => [...prev, item.name])}
                  className="rounded-xl bg-secondary px-2 py-1 text-[10px] font-medium text-secondary-foreground transition-colors hover:bg-muted"
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
              style={{ borderColor: 'var(--border)' }}
            >
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : tx.id)}
                className="w-full flex items-center gap-2 py-2.5 text-left transition-colors hover:bg-muted/20"
              >
                <span className="text-sm shrink-0">{tx.emoji}</span>
                <div className="min-w-0 flex-1">
                  <p
                    className="truncate text-xs font-medium"
                    style={{ color: 'var(--foreground)', fontFamily: F }}
                  >
                    {tx.name}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <p
                      className="text-[10px] text-muted-foreground"
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
                    // 입금(+)의 경우 시스템 긍정 지표인 var(--chart-2) 매핑, 출금은 var(--foreground) 매핑
                    color:
                      tx.type === 'in' ? 'var(--chart-2)' : 'var(--foreground)',
                    fontFamily: M,
                  }}
                >
                  {tx.type === 'in' ? '+' : ''}
                  {Math.abs(tx.amount).toLocaleString()}원
                </p>
                {isExpanded ? (
                  <ChevronUp size={13} className="text-muted-foreground" />
                ) : (
                  <ChevronDown size={13} className="text-muted-foreground" />
                )}
              </button>
              {isExpanded ? (
                <div
                  className="mx-2 mb-2 rounded-2xl bg-secondary px-4 py-2 text-[10px]"
                  style={{ border: '1px solid var(--border)' }}
                >
                  <div className="flex justify-between py-1">
                    <span
                      className="text-muted-foreground"
                      style={{ fontFamily: F }}
                    >
                      거래처
                    </span>
                    <span style={{ color: 'var(--foreground)', fontFamily: F }}>
                      {tx.name}
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-1">
                    <span
                      className="text-muted-foreground"
                      style={{ fontFamily: F }}
                    >
                      카테고리
                    </span>
                    <CatBadge
                      cat={category}
                      onEdit={(value) =>
                        setTxCategories((prev) => ({ ...prev, [tx.id]: value }))
                      }
                    />
                  </div>
                  <div className="flex justify-between py-1">
                    <span
                      className="text-muted-foreground"
                      style={{ fontFamily: F }}
                    >
                      날짜/시간
                    </span>
                    <span style={{ color: 'var(--foreground)', fontFamily: M }}>
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
