import LoginFeature from '@/features/auth/LoginFeature';

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex items-center justify-center px-4 py-8">
      <LoginFeature onLogin={() => console.log('login')} />
    </div>
  );
}
