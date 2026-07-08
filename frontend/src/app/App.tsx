import { useEffect, useState } from 'react';
import { AssistantProvider } from './providers/AssistantProvider';
import ChatThread from '@/widgets/ChatThread';
import LoginFeature from '@/features/auth/LoginFeature';
import SignupFeature from '@/features/auth/SignupFeature';
import { useTheme } from '@/shared/hooks/useTheme';
import { useUserStore } from '@/entities/user';
import { AppRouter } from './router';
import type { AuthView } from '@/shared/types/types';

export default function App() {
  const { theme } = useTheme();
  const isLoggedIn = useUserStore((state) => state.isLoggedIn);
  const login = useUserStore((state) => state.login);
  const [authView, setAuthView] = useState<AuthView>('login');

  useEffect(() => {
    if (sessionStorage.getItem('rf_logged_in') === '1') {
      login({ id: 'restored', name: '사용자' });
    }
  }, [login]);

  if (isLoggedIn) {
    return (
      <main
        data-theme={theme}
        className="min-h-screen bg-background text-foreground"
      >
        <AssistantProvider>
          <ChatThread />
        </AssistantProvider>
        <AppRouter /> {/* TODO: 화면 디버깅용이므로 제거하기 */}
      </main>
    );
  }

  return (
    <main
      data-theme={theme}
      className="min-h-screen bg-background text-foreground"
    >
      <div className="mx-auto flex min-h-screen w-full items-center justify-center px-4 py-8 sm:px-6 lg:px-8">
        <div
          className="w-full rounded-4xl border border-border bg-card/95 p-6 shadow-[0_32px_80px_rgba(15,23,42,0.18)] backdrop-blur-sm"
          style={{ maxWidth: 480 }}
        >
          {authView === 'login' ? (
            <LoginFeature
              onLogin={() => {
                sessionStorage.setItem('rf_logged_in', '1');
              }}
              onGoToSignup={() => setAuthView('signup')}
            />
          ) : (
            <SignupFeature
              onSignupSuccess={() => setAuthView('login')}
              onBackToLogin={() => setAuthView('login')}
            />
          )}
        </div>
      </div>
    </main>
  );
}
