import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import { LogOut, Moon, SunMedium } from 'lucide-react';
import { useTheme } from '@/shared/hooks/useTheme';
import { useUserStore, logoutApi } from '@/entities/user';
import ActionButton from '@/shared/ui/ActionButton';

const links = [
  { path: '/', label: '홈' },
  { path: '/transfer', label: '송금' },
  { path: '/spending', label: '소비분석' },
  { path: '/transactions', label: '거래내역' },
  { path: '/budget', label: '예산관리' },
  { path: '/balance', label: '잔액조회' },
  { path: '/autotransfer', label: '자동이체등록' },
  { path: '/card', label: '카드관리' },
];

export default function NavigationBar() {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const logout = useUserStore((state) => state.logout);
  const userName = useUserStore((state) => state.user?.name);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLogout = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);

    try {
      await logoutApi();
    } catch {
      // 토큰 만료 등 API 실패해도 클라이언트 세션은 정리
    } finally {
      logout();
      setIsLoggingOut(false);
    }
  };

  return (
    <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <nav className="flex flex-wrap items-center gap-2">
        {links.map((link) => (
          <Link
            key={link.path}
            to={link.path}
            className={`rounded-full border px-3 py-2 text-sm transition ${
              location.pathname === link.path
                ? 'border-accent bg-accent/10 text-accent-foreground font-medium'
                : 'border-border text-muted-foreground hover:border-accent/40 hover:text-foreground'
            }`}
          >
            {link.label}
          </Link>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        {userName ? (
          <span className="hidden text-sm text-muted-foreground sm:inline">
            {userName}님
          </span>
        ) : null}
        <button
          type="button"
          onClick={toggleTheme}
          className="inline-flex h-10 items-center justify-center rounded-full border border-border bg-card/90 px-3 text-sm text-foreground transition hover:border-emerald-400/40 hover:text-foreground"
        >
          {theme === 'dark' ? (
            <SunMedium className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </button>
        <ActionButton
          variant="secondary"
          onClick={handleLogout}
          disabled={isLoggingOut}
          className="inline-flex items-center gap-1.5"
        >
          <LogOut className="h-4 w-4" />
          {isLoggingOut ? '로그아웃 중...' : '로그아웃'}
        </ActionButton>
      </div>
    </header>
  );
}
