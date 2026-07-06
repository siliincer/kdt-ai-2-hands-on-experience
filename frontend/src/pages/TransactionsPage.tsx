import PageShell from '../widgets/PageShell';
import NavigationBar from '../widgets/NavigationBar';
import TransactionsFeature from '../features/transactions/TransactionsFeature';

export default function TransactionsPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="거래 내역"
          description="최근 거래 기록과 지출 흐름을 한눈에 확인하세요."
        >
          <TransactionsFeature />
        </PageShell>
      </div>
    </div>
  );
}
