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
    // 1. 최상위 배경과 글자색은 시스템 변수를 따릅니다.
    <div className="min-h-screen bg-background text-foreground transition-colors duration-200">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="AI 금융 코파일럿 대시보드"
          description="금융 AI Agent 플랫폼에 오신 것을 환영합니다."
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
                    // 2. 하드코딩된 bg-slate-800 대신 테마 변수 bg-card, border-border 적용
                    className="rounded-2xl border border-border bg-card p-4 shadow-xs"
                  >
                    <div className="mb-3 flex items-center justify-between">
                      {/* text-muted-foreground로 라이트(회색)/다크(연회색) 자동 대응 */}
                      <p className="text-sm font-medium text-muted-foreground">
                        {account.bank}
                      </p>
                      {/* 포인트 컬러는 CSS에 정의된 핵심 컬러(--accent) 혹은 보조 컬러 매핑 */}
                      <span className="rounded-full bg-chart-2/10 px-2.5 py-1 text-[11px] font-medium text-chart-2">
                        {account.badge}
                      </span>
                    </div>
                    {/* text-foreground로 라이트(진한네이비)/다크(화이트) 자동 대응 */}
                    <p className="text-lg font-semibold text-foreground">
                      {account.name}
                    </p>
                    <p className="mt-3 text-2xl font-semibold text-foreground">
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
                    // 3. 카드 자체에 그라데이션이 강하게 들어간 포인트 카드는 text-white를 유지하는 것이 디자인적으로 옳습니다.
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
                    {/* SectionCard 내부 컴포넌트 내부도 변수 처리가 안 되어 있다면 여기서 명시적으로 덮어씌웁니다. */}
                    <p className="text-xl font-semibold text-foreground">
                      {insight.value}
                    </p>
                    <p className="mt-1 text-sm text-chart-2 font-medium">
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
                    // 4. 리스트 아이템 행 레이아웃 테마 변수화
                    className="flex items-center justify-between rounded-2xl border border-border bg-card px-4 py-3 shadow-xs"
                  >
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        {transaction.title}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {transaction.date}
                      </p>
                    </div>
                    <div className="text-right">
                      <p
                        className={`text-sm font-semibold ${
                          transaction.amount > 0
                            ? 'text-chart-2' // 양수 수입 컬러 (초록/블루 계열 변수)
                            : 'text-foreground' // 음수 지출 컬러 (기본 글자색 변수)
                        }`}
                      >
                        {transaction.amount > 0 ? '+' : ''}
                        {formatCurrency(transaction.amount)}
                      </p>
                      <p className="text-xs text-muted-foreground">
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
