import { useState } from 'react';
import { AppRouter } from './router';
import LoginFeature from '@/features/auth/LoginFeature';
import SignupFeature from '@/features/auth/SignupFeature';
import { useTheme } from '@/shared/hooks/useTheme';

type AuthView = 'login' | 'signup';

export default function App() {
  const { theme } = useTheme();
  const [isLoggedIn, setIsLoggedIn] = useState(
    () => sessionStorage.getItem('rf_logged_in') === '1',
  );
  const [authView, setAuthView] = useState<AuthView>('login');

  return (
    <main
      data-theme={theme}
      className="min-h-screen bg-background text-foreground"
    >
      <div className="mx-auto flex min-h-screen w-full items-center justify-center px-4 py-8 sm:px-6 lg:px-8">
        {!isLoggedIn ? (
          <div
            className="w-full rounded-4xl border border-border bg-card/95 p-6 shadow-[0_32px_80px_rgba(15,23,42,0.18)] backdrop-blur-sm"
            style={{ maxWidth: 480 }}
          >
            {authView === 'login' ? (
              <LoginFeature
                onLogin={() => {
                  sessionStorage.setItem('rf_logged_in', '1');
                  setIsLoggedIn(true);
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
        ) : (
          <div className="w-full">
            <AppRouter />
          </div>
        )}
      </div>
    </main>
  );
}
