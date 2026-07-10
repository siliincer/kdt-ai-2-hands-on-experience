import PageShell from '../widgets/PageShell';
import NavigationBar from '../widgets/NavigationBar';
import SpendingFeature from '../features/spending/SpendingFeature';

export default function SpendingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="소비 분석"
          description="지출 패턴을 확인하고 카테고리별 소비 동향을 살펴보세요."
        >
          <SpendingFeature />
        </PageShell>
      </div>
    </div>
  );
}
