import PageShell from '../widgets/PageShell';
import NavigationBar from '../widgets/NavigationBar';
import BalanceFeature from '../features/balance/BalanceFeature';

export default function BalancePage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="잔액 조회"
          description="전체 계좌와 입출금 내역을 빠르게 확인할 수 있습니다."
        >
          <BalanceFeature />
        </PageShell>
      </div>
    </div>
  );
}
