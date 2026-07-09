import PageShell from '../widgets/PageShell';
import NavigationBar from '../widgets/NavigationBar';
import AutoTransferFeature from '../features/autotransfer/AutoTransferFeature';

export default function AutoTransferPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="자동 이체"
          description="정기적인 송금을 간편하게 설정하고 관리하세요."
        >
          <AutoTransferFeature />
        </PageShell>
      </div>
    </div>
  );
}
