import { Link } from 'react-router';
import { ActionButton, AppShell, SectionCard } from '../shared/ui';
import PageShell from '../widgets/PageShell';
import NavigationBar from '../widgets/NavigationBar';
import {
  accounts,
  insights,
  quickActions,
  recentTransactions,
} from '../app/mockData';

import { formatCurrency } from '@/shared/lib/utils';

export default function HomePage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="AI 금융 코파일럿 대시보드"
          description="예시 화면을 기반으로 한 렌더링 가능 상태의 UI입니다. 백엔드 연결 전에도 주요 금융 정보와 행동 흐름을 확인할 수 있습니다."
        >
          <section className="space-y-6">
            <AppShell
              title="계좌 요약"
              description="실제 계좌 정보를 확인하는 섹션입니다."
            >
              <div className="mb-4 flex justify-end">
                <ActionButton variant="primary">새 계좌 추가</ActionButton>
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {accounts.map((account) => (
                  <article
                    key={account.id}
                    className="rounded-2xl border border-white/10 bg-slate-800/70 p-4"
                  >
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-sm font-medium text-slate-300">
                        {account.bank}
                      </p>
                      <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-[11px] text-emerald-300">
                        {account.badge}
                      </span>
                    </div>
                    <p className="text-lg font-semibold text-white">
                      {account.name}
                    </p>
                    <p className="mt-3 text-2xl font-semibold text-white">
                      {formatCurrency(account.balance)}
                    </p>
                  </article>
                ))}
              </div>
            </AppShell>

            <AppShell title="빠른 실행" description="자주 쓰는 기능 바로가기">
              <div className="grid gap-3 md:grid-cols-3">
                {quickActions.map((action) => (
                  <Link
                    key={action.label}
                    to={
                      action.label.includes('송금')
                        ? '/transfer'
                        : action.label.includes('지출')
                          ? '/spending'
                          : '/autotransfer'
                    }
                    className={`rounded-2xl bg-linear-to-br ${action.accent} p-4 text-left text-white shadow-md transition hover:scale-[1.01]`}
                  >
                    <p className="text-base font-semibold">{action.label}</p>
                    <p className="mt-2 text-sm text-white/80">
                      {action.description}
                    </p>
                  </Link>
                ))}
              </div>
            </AppShell>
          </section>

          <section className="space-y-6">
            <AppShell
              title="한눈에 보는 인사이트"
              description="현재 금융 상황을 요약한 정보입니다."
            >
              <div className="space-y-3">
                {insights.map((insight) => (
                  <SectionCard key={insight.title} title={insight.title}>
                    <p className="text-xl font-semibold text-white">
                      {insight.value}
                    </p>
                    <p className="mt-1 text-sm text-emerald-300">
                      {insight.tone}
                    </p>
                  </SectionCard>
                ))}
              </div>
            </AppShell>

            <AppShell
              title="최근 거래"
              description="최근 일주일 동향을 확인할 수 있습니다."
            >
              <div className="space-y-3">
                {recentTransactions.map((transaction) => (
                  <div
                    key={transaction.id}
                    className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-800/70 px-3 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-white">
                        {transaction.title}
                      </p>
                      <p className="text-xs text-slate-400">
                        {transaction.date}
                      </p>
                    </div>
                    <div className="text-right">
                      <p
                        className={`text-sm font-semibold ${
                          transaction.amount > 0
                            ? 'text-emerald-300'
                            : 'text-slate-100'
                        }`}
                      >
                        {transaction.amount > 0 ? '+' : ''}
                        {formatCurrency(transaction.amount)}
                      </p>
                      <p className="text-xs text-slate-400">
                        {transaction.note}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </AppShell>
          </section>
        </PageShell>
      </div>
    </div>
  );
}
