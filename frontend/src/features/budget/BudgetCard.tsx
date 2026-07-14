import { useState } from 'react';

import { ToggleLeft, ToggleRight } from 'lucide-react';

import { F, M } from '@/shared/constants/font';

import type { BudgetData } from '@/shared/types/ui';

export function BudgetCard({ data }: { data: BudgetData }) {
  const { budgetItems, subItems } = data;
  const [subs, setSubs] = useState(subItems.map((item) => item.active));

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">🎯</span>
        <p
          className="text-sm font-semibold text-foreground"
          style={{ fontFamily: F }}
        >
          예산 현황
        </p>
      </div>

      {/* 하드코딩 bg-white를 bg-secondary 혹은 카드 내부 보조 컨테이너 규격으로 보정 */}
      <div className="space-y-4 rounded-3xl bg-secondary/40 border border-border p-5 shadow-sm">
        {budgetItems.map((item) => {
          const percent = Math.round((item.used / item.total) * 100);

          {
            /* 다크 모드 가독성을 고려한 시스템 차트/경고 스펙 매핑 (100% 이상: 위험, 80% 이상: 경고, 정상: 안전) */
          }
          const progressColor =
            percent >= 100
              ? 'var(--chart-5)'
              : percent >= 80
                ? 'var(--chart-4)'
                : 'var(--chart-2)';

          return (
            <div key={item.cat}>
              <div
                className="mb-2 flex items-center justify-between text-sm font-medium"
                style={{ color: 'var(--foreground)', fontFamily: F }}
              >
                <span>{item.cat}</span>
                <span
                  className="text-[10px] text-muted-foreground"
                  style={{ fontFamily: M }}
                >
                  {item.used.toLocaleString()} / {item.total.toLocaleString()}원
                </span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full transition-all duration-350"
                  style={{
                    width: `${Math.min(percent, 100)}%`,
                    background: progressColor,
                  }}
                />
              </div>
              <p
                className="mt-1 text-right text-[10px] font-semibold"
                style={{ color: progressColor, fontFamily: M }}
              >
                {percent}%
              </p>
            </div>
          );
        })}
      </div>

      <div className="mt-6 rounded-3xl bg-secondary/40 border border-border p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <p
            className="text-xs font-semibold uppercase tracking-[0.25em]"
            style={{ color: 'var(--foreground)', fontFamily: F }}
          >
            반복 결제
          </p>
          <span
            className="text-[10px] text-muted-foreground"
            style={{ fontFamily: M }}
          >
            월별 총액
          </span>
        </div>
        <div className="space-y-3">
          {subItems.map((item, index) => (
            <div
              key={item.name}
              className="flex items-center justify-between rounded-2xl border border-border bg-card px-3 py-3"
            >
              <div>
                <p
                  className="text-sm font-medium"
                  style={{ color: 'var(--foreground)', fontFamily: F }}
                >
                  {item.name}
                </p>
                <p
                  className="text-[10px] text-muted-foreground"
                  style={{ fontFamily: M }}
                >
                  {item.amount.toLocaleString()}원/월
                </p>
              </div>
              <button
                type="button"
                onClick={() =>
                  setSubs((prev) => {
                    const next = [...prev];
                    next[index] = !next[index];
                    return next;
                  })
                }
                aria-label={subs[index] ? '끄기' : '켜기'}
                className="transition-opacity hover:opacity-80"
              >
                {subs[index] ? (
                  <ToggleRight size={24} color="var(--accent)" />
                ) : (
                  <ToggleLeft size={24} color="var(--muted-foreground)" />
                )}
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {['예산 수정', '구독 추가'].map((label) => (
          <button
            key={label}
            type="button"
            className="rounded-full border border-border px-3 py-2 text-[10px] font-medium text-muted-foreground bg-transparent transition hover:bg-muted/20"
            style={{ fontFamily: F }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
