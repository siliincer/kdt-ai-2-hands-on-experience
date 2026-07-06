import PageShell from '../widgets/PageShell';
import NavigationBar from '../widgets/NavigationBar';
import CardFeature from '../features/card/CardFeature';

export default function CardPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <NavigationBar />
        <PageShell
          title="카드 관리"
          description="카드 정보와 청구 내역을 한 곳에서 확인하세요."
        >
          <CardFeature />
        </PageShell>
      </div>
    </div>
  );
}
