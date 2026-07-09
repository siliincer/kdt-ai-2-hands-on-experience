import PageShell from '../widgets/PageShell';
import NavigationBar from '../widgets/NavigationBar';
import BudgetFeature from '../features/budget/BudgetFeature';

export default function BudgetPage() {
  return (
    // 전체 레이아웃의 시맨틱 컬러 구조 유지
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="예산 관리"
          description="예산을 설정하고 소비 목표를 관리할 수 있습니다."
        >
          <BudgetFeature />
        </PageShell>
      </div>
    </div>
  );
}
