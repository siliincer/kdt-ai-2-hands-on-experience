import { useState } from 'react';
import { AppRouter } from './router';
import LoginFeature from '@/features/auth/LoginFeature';

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(
    () => sessionStorage.getItem('rf_logged_in') === '1',
  );

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <div className="mx-auto flex min-h-screen w-full items-center justify-center px-4 py-8 sm:px-6 lg:px-8">
        {!isLoggedIn ? (
          <div
            className="w-full rounded-4xl border border-white/10 bg-slate-950/90 p-6 shadow-[0_32px_80px_rgba(15,23,42,0.35)] backdrop-blur-sm"
            style={{ maxWidth: 480 }}
          >
            <LoginFeature
              onLogin={() => {
                sessionStorage.setItem('rf_logged_in', '1');
                setIsLoggedIn(true);
              }}
            />
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
