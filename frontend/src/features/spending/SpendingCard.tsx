import { useState } from 'react';

import {
  PieChart,
  Pie,
  Cell,
  Tooltip as RChartTip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  LineChart,
  Line,
  ResponsiveContainer,
} from 'recharts';

import { M, F } from '@/shared/constants/font';

import type { PieClickEntry } from '@/shared/types/interface';
import type { SpendingData } from '@/shared/types/ui';

import { CatBadge } from '@/shared/ui/CatBadge';
import { BarTip } from './BarTip';

export function SpendingCard({
  data,
  onPrompt,
}: {
  data: SpendingData;
  onPrompt?: (text: string) => void;
}) {
  const { pie: pieData, bar: barData, monthly: monthlySpend, catTx } = data;
  const [tab, setTab] = useState<'donut' | 'bar' | 'monthly'>('donut');
  const [selCat, setSelCat] = useState<string | null>(null);
  const [catEdit, setCatEdit] = useState<Record<string, string>>({});

  const toggleCat = (name: string) =>
    setSelCat((current) => (current === name ? null : name));

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">📊</span>
        <p
          className="text-sm font-semibold"
          style={{ color: 'var(--foreground)', fontFamily: F }}
        >
          카테고리별 지출
        </p>
      </div>

      {/* 탭 컨테이너의 고정 배경색을 시스템 보조 배경(bg-secondary)으로 매핑 */}
      <div className="mb-4 flex gap-1 rounded-2xl bg-secondary p-1">
        {[
          { key: 'donut' as const, label: '도넛' },
          { key: 'bar' as const, label: '막대' },
          { key: 'monthly' as const, label: '월별비교' },
        ].map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className="flex-1 rounded-xl px-3 py-2 text-[11px] font-semibold transition-all"
            style={{
              background: tab === item.key ? 'var(--card)' : 'transparent',
              color:
                tab === item.key
                  ? 'var(--foreground)'
                  : 'var(--muted-foreground)',
              fontFamily: F,
              boxShadow: tab === item.key ? '0 1px 4px var(--border)' : 'none',
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'donut' && (
        <div>
          <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
            <div className="h-55 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={42}
                    outerRadius={62}
                    dataKey="value"
                    paddingAngle={3}
                    onClick={(entry: PieClickEntry) => toggleCat(entry.name)}
                  >
                    {pieData.map((entry) => (
                      <Cell
                        key={`cell-${entry.name}`}
                        fill={entry.color}
                        opacity={selCat && selCat !== entry.name ? 0.3 : 1}
                        stroke={selCat === entry.name ? 'var(--card)' : 'none'}
                        strokeWidth={selCat === entry.name ? 3 : 0}
                      />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2">
              {pieData.map((entry) => (
                <button
                  key={entry.name}
                  type="button"
                  onClick={() => toggleCat(entry.name)}
                  className="flex w-full items-center justify-between rounded-2xl border border-border px-3 py-3 text-left transition-colors"
                  style={{
                    background:
                      selCat === entry.name
                        ? 'var(--secondary)'
                        : 'transparent',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ background: entry.color }}
                    />
                    <span
                      className="text-xs font-medium"
                      style={{
                        color: 'var(--muted-foreground)',
                        fontFamily: F,
                      }}
                    >
                      {entry.name}
                    </span>
                  </div>
                  <div className="text-right">
                    <p
                      className="text-xs font-semibold"
                      style={{ color: 'var(--foreground)', fontFamily: M }}
                    >
                      {entry.value}%
                    </p>
                    <p
                      className="text-[10px] text-muted-foreground"
                      style={{ fontFamily: M }}
                    >
                      {entry.amount.toLocaleString()}원
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>
          {selCat && catTx[selCat] ? (
            <div className="mt-4 rounded-3xl border border-border bg-card p-4">
              <p
                className="mb-3 text-[10px] font-semibold uppercase tracking-[0.25em]"
                style={{ color: 'var(--foreground)', fontFamily: F }}
              >
                {selCat} 거래 내역
              </p>
              <div className="space-y-2">
                {catTx[selCat].map((tx, index) => (
                  <div
                    key={`${tx.name}-${index}`}
                    className="flex items-center gap-3 rounded-2xl border border-border px-3 py-2"
                  >
                    <p
                      className="w-12 text-[10px] text-muted-foreground"
                      style={{ fontFamily: M }}
                    >
                      {tx.date}
                    </p>
                    <p
                      className="flex-1 text-xs font-medium"
                      style={{ color: 'var(--foreground)', fontFamily: F }}
                    >
                      {tx.name}
                    </p>
                    <CatBadge
                      cat={catEdit[`${selCat}-${index}`] || selCat}
                      onEdit={(value) =>
                        setCatEdit((prev) => ({
                          ...prev,
                          [`${selCat}-${index}`]: value,
                        }))
                      }
                    />
                    <p
                      className="text-[10px] font-semibold"
                      style={{ color: 'var(--foreground)', fontFamily: M }}
                    >
                      {tx.amount.toLocaleString()}원
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {tab === 'bar' && (
        <div>
          <div className="h-55 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={barData}
                margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="name"
                  tick={{
                    fontSize: 11,
                    fill: 'var(--muted-foreground)',
                    fontFamily: F,
                  }}
                />
                <YAxis
                  tick={{
                    fontSize: 10,
                    fill: 'var(--muted-foreground)',
                    fontFamily: M,
                  }}
                />
                <RChartTip content={BarTip} />
                <Bar dataKey="change" radius={[6, 6, 0, 0]}>
                  {barData.map((entry) => (
                    <Cell
                      key={`bar-${entry.name}`}
                      /* 변동 표시는 직관성을 위해 시스템 디스트럭티브(파괴/감소) 및 액센트(성장) 대입 가능하나 차트 컬러 규격 매핑 */
                      fill={
                        entry.change >= 0 ? 'var(--chart-5)' : 'var(--chart-2)'
                      }
                      opacity={selCat && selCat !== entry.name ? 0.3 : 1}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {selCat
            ? (() => {
                const current = barData.find((item) => item.name === selCat);
                if (
                  !current ||
                  (!current.added.length && !current.removed.length)
                )
                  return null;
                return (
                  <div className="mt-4 rounded-3xl border border-border bg-card p-4 shadow-sm">
                    <p
                      className="mb-3 text-[10px] font-semibold uppercase tracking-[0.25em]"
                      style={{ color: 'var(--foreground)', fontFamily: F }}
                    >
                      {selCat} 전월 대비 변동
                    </p>
                    {current.added.map((item) => (
                      <div
                        key={`add-${item.name}`}
                        className="mb-2 flex justify-between text-[10px]"
                      >
                        <p
                          style={{ color: 'var(--foreground)', fontFamily: F }}
                        >
                          <span
                            className="mr-1"
                            style={{ color: 'var(--chart-2)' }}
                          >
                            +
                          </span>
                          {item.name}
                        </p>
                        <p style={{ color: 'var(--chart-2)', fontFamily: M }}>
                          +{item.amount.toLocaleString()}원
                        </p>
                      </div>
                    ))}
                    {current.removed.map((item) => (
                      <div
                        key={`rm-${item.name}`}
                        className="mb-2 flex justify-between text-[10px]"
                      >
                        <p
                          style={{ color: 'var(--foreground)', fontFamily: F }}
                        >
                          <span
                            className="mr-1"
                            style={{ color: 'var(--chart-5)' }}
                          >
                            −
                          </span>
                          {item.name}
                        </p>
                        <p style={{ color: 'var(--chart-5)', fontFamily: M }}>
                          -{item.amount.toLocaleString()}원
                        </p>
                      </div>
                    ))}
                  </div>
                );
              })()
            : null}
        </div>
      )}

      {tab === 'monthly' && (
        <div className="h-55 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={monthlySpend}
              margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="month"
                tick={{
                  fontSize: 11,
                  fill: 'var(--muted-foreground)',
                  fontFamily: F,
                }}
              />
              <YAxis
                tick={{
                  fontSize: 9,
                  fill: 'var(--muted-foreground)',
                  fontFamily: M,
                }}
                tickFormatter={(value) => `${(value / 10000).toFixed(0)}만`}
              />
              <RChartTip
                formatter={(value: number) => [
                  `${value.toLocaleString()}원`,
                  '지출',
                ]}
              />
              <Line
                type="monotone"
                dataKey="amount"
                stroke="var(--accent)"
                strokeWidth={2.5}
                dot={{ fill: 'var(--accent)', r: 4 }}
                activeDot={{ fill: 'var(--primary)', r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 하단 보조 액션 → 자연어 프롬프트 전송(라우팅 대신 chat 흐름) */}
      <div className="mt-4 flex flex-wrap gap-2">
        {[
          { label: '지난달 비교', prompt: '지난달과 소비 현황 비교해줘' },
          { label: '예산 설정', prompt: '예산 현황 보여줘' },
          { label: '거래 내역 전체', prompt: '거래 내역 보여줘' },
        ].map(({ label, prompt }) => (
          <button
            key={label}
            type="button"
            onClick={prompt ? () => onPrompt?.(prompt) : undefined}
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
