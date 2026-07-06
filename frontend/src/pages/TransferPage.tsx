import PageShell from '../widgets/PageShell';
import NavigationBar from '../widgets/NavigationBar';
import TransferFeature from '../features/transfer/TransferFeature';

export default function TransferPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="송금"
          description="받는 사람, 금액, 일시를 빠르게 입력하고 송금 흐름을 확인하세요."
        >
          <TransferFeature />
        </PageShell>
      </div>
    </div>
  );
}
