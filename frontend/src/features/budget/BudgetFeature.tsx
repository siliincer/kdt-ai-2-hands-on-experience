import { useState } from 'react';
import { useNavigate } from 'react-router';
import { ToggleLeft, ToggleRight } from 'lucide-react';

import { NAVY, MINT } from '@/shared/constants/color';
import { F, M } from '@/shared/constants/font';

import { subItems, budgetItems } from '@/features/mockData/mockData';

function BudgetCard() {
  const [subs, setSubs] = useState(subItems.map((item) => item.active));

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">🎯</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          예산 현황
        </p>
      </div>
      <div className="space-y-4 rounded-3xl bg-white p-5 shadow-sm">
        {budgetItems.map((item) => {
          const percent = Math.round((item.used / item.total) * 100);
          const progressColor =
            percent >= 100 ? '#FF4D4F' : percent >= 80 ? '#F59E0B' : '#52C41A';
          return (
            <div key={item.cat}>
              <div
                className="mb-2 flex items-center justify-between text-sm font-medium"
                style={{ color: NAVY, fontFamily: F }}
              >
                <span>{item.cat}</span>
                <span
                  className="text-[10px] text-slate-500"
                  style={{ fontFamily: M }}
                >
                  {item.used.toLocaleString()} / {item.total.toLocaleString()}원
                </span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full"
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
      <div className="mt-6 rounded-3xl bg-white p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <p
            className="text-xs font-semibold uppercase tracking-[0.25em]"
            style={{ color: NAVY, fontFamily: F }}
          >
            반복 결제
          </p>
          <span
            className="text-[10px] text-slate-500"
            style={{ fontFamily: M }}
          >
            월별 총액
          </span>
        </div>
        <div className="space-y-3">
          {subItems.map((item, index) => (
            <div
              key={item.name}
              className="flex items-center justify-between rounded-2xl border border-slate-200 px-3 py-3"
            >
              <div>
                <p
                  className="text-sm font-medium"
                  style={{ color: NAVY, fontFamily: F }}
                >
                  {item.name}
                </p>
                <p
                  className="text-[10px] text-slate-500"
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
              >
                {subs[index] ? (
                  <ToggleRight size={24} color={MINT} />
                ) : (
                  <ToggleLeft size={24} color="#CBD5E1" />
                )}
              </button>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-full border border-slate-200 px-3 py-2 text-[10px] font-medium text-slate-600 transition hover:opacity-90"
          style={{ fontFamily: F }}
        >
          예산 수정
        </button>
        <button
          type="button"
          className="rounded-full border border-slate-200 px-3 py-2 text-[10px] font-medium text-slate-600 transition hover:opacity-90"
          style={{ fontFamily: F }}
        >
          구독 추가
        </button>
      </div>
    </div>
  );
}

export default function BudgetFeature() {
  const navigate = useNavigate();

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">예산 관리</h2>
          <p className="mt-1 text-sm text-slate-400">
            예산을 설정하고 구독을 관리하여 소비 습관을 지속적으로 개선하세요.
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
      <BudgetCard />
    </div>
  );
}
