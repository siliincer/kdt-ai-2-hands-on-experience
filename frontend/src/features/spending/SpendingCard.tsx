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

import { NAVY, MINT } from '@/shared/constants/color';
import { M, F } from '@/shared/constants/font';

import {
  barData,
  pieData,
  monthlySpend,
  catTx,
} from '@/features/mockData/mockData';

import type { PieClickEntry } from '@/shared/types/interface';

import { CatBadge } from '@/shared/ui/CatBadge';
import { BarTip } from './BarTip';

export function SpendingCard({
  onNavigate,
}: {
  onNavigate: (path: string) => void;
}) {
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
          style={{ color: '#F8FAFC', fontFamily: F }}
        >
          카테고리별 지출
        </p>
      </div>
      <div className="mb-4 flex gap-1 rounded-2xl bg-slate-100 p-1">
        {[
          { key: 'donut' as const, label: '도넛' },
          { key: 'bar' as const, label: '막대' },
          { key: 'monthly' as const, label: '월별비교' },
        ].map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className="flex-1 rounded-xl px-3 py-2 text-[11px] font-semibold transition"
            style={{
              background: tab === item.key ? '#fff' : 'transparent',
              color: tab === item.key ? NAVY : '#6B7A99',
              fontFamily: F,
              boxShadow:
                tab === item.key ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
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
                    // === entry: any에서 entry: PieClickEntry로 수정 ===
                    onClick={(entry: PieClickEntry) => toggleCat(entry.name)}
                  >
                    {pieData.map((entry) => (
                      <Cell
                        key={`cell-${entry.name}`}
                        fill={entry.color}
                        opacity={selCat && selCat !== entry.name ? 0.3 : 1}
                        stroke={selCat === entry.name ? '#fff' : 'none'}
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
                  className="flex w-full items-center justify-between rounded-2xl border border-slate-200 px-3 py-3 text-left"
                  style={{
                    background: selCat === entry.name ? '#fff' : 'transparent',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ background: entry.color }}
                    />
                    <span
                      className="text-xs font-medium"
                      style={{ color: '#6B7A99', fontFamily: F }}
                    >
                      {entry.name}
                    </span>
                  </div>
                  <div className="text-right">
                    <p
                      className="text-xs font-semibold"
                      style={{ color: NAVY, fontFamily: M }}
                    >
                      {entry.value}%
                    </p>
                    <p
                      className="text-[10px] text-slate-500"
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
            <div className="mt-4 rounded-3xl border border-slate-200 bg-white p-4">
              <p
                className="mb-3 text-[10px] font-semibold uppercase tracking-[0.25em]"
                style={{ color: NAVY, fontFamily: F }}
              >
                {selCat} 거래 내역
              </p>
              <div className="space-y-2">
                {catTx[selCat].map((tx, index) => (
                  <div
                    key={`${tx.name}-${index}`}
                    className="flex items-center gap-3 rounded-2xl border border-slate-200 px-3 py-2"
                  >
                    <p
                      className="w-12 text-[10px] text-slate-500"
                      style={{ fontFamily: M }}
                    >
                      {tx.date}
                    </p>
                    <p
                      className="flex-1 text-xs font-medium"
                      style={{ color: NAVY, fontFamily: F }}
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
                      style={{ color: NAVY, fontFamily: M }}
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
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="rgba(15,30,61,0.06)"
                />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11, fill: '#6B7A99', fontFamily: F }}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: '#6B7A99', fontFamily: M }}
                />
                <RChartTip content={BarTip} />
                <Bar dataKey="change" radius={[6, 6, 0, 0]}>
                  {barData.map((entry) => (
                    <Cell
                      key={`bar-${entry.name}`}
                      fill={entry.change >= 0 ? '#FF4D4F' : '#3B82F6'}
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
                  <div className="mt-4 rounded-3xl bg-white p-4 shadow-sm">
                    <p
                      className="mb-3 text-[10px] font-semibold uppercase tracking-[0.25em]"
                      style={{ color: NAVY, fontFamily: F }}
                    >
                      {selCat} 전월 대비 변동
                    </p>
                    {current.added.map((item) => (
                      <div
                        key={`add-${item.name}`}
                        className="mb-2 flex justify-between text-[10px]"
                      >
                        <p style={{ color: NAVY, fontFamily: F }}>
                          <span className="mr-1" style={{ color: '#3B82F6' }}>
                            +
                          </span>
                          {item.name}
                        </p>
                        <p style={{ color: '#3B82F6', fontFamily: M }}>
                          +{item.amount.toLocaleString()}원
                        </p>
                      </div>
                    ))}
                    {current.removed.map((item) => (
                      <div
                        key={`rm-${item.name}`}
                        className="mb-2 flex justify-between text-[10px]"
                      >
                        <p style={{ color: NAVY, fontFamily: F }}>
                          <span className="mr-1" style={{ color: '#FF4D4F' }}>
                            −
                          </span>
                          {item.name}
                        </p>
                        <p style={{ color: '#FF4D4F', fontFamily: M }}>
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
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(15,30,61,0.06)"
              />
              <XAxis
                dataKey="month"
                tick={{ fontSize: 11, fill: '#6B7A99', fontFamily: F }}
              />
              <YAxis
                tick={{ fontSize: 9, fill: '#6B7A99', fontFamily: M }}
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
                stroke={MINT}
                strokeWidth={2.5}
                dot={{ fill: MINT, r: 4 }}
                activeDot={{ fill: NAVY, r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-full border border-slate-200 px-3 py-2 text-[10px] font-medium text-slate-600 transition hover:opacity-90"
          style={{ fontFamily: F }}
        >
          지난달 비교
        </button>
        <button
          type="button"
          onClick={() => onNavigate('/budget')}
          className="rounded-full border border-slate-200 px-3 py-2 text-[10px] font-medium text-slate-600 transition hover:opacity-90"
          style={{ fontFamily: F }}
        >
          예산 설정
        </button>
        <button
          type="button"
          onClick={() => onNavigate('/transactions')}
          className="rounded-full border border-slate-200 px-3 py-2 text-[10px] font-medium text-slate-600 transition hover:opacity-90"
          style={{ fontFamily: F }}
        >
          거래 내역 전체
        </button>
      </div>
    </div>
  );
}
