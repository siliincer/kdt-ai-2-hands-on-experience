import { Link, useLocation } from 'react-router';
import { Moon, SunMedium } from 'lucide-react';
import { useTheme } from '@/shared/hooks/useTheme';

const links = [
  { path: '/', label: '홈' },
  { path: '/transfer', label: '송금' },
  { path: '/spending', label: '소비분석' },
  { path: '/transactions', label: '거래내역' },
  { path: '/budget', label: '예산관리' },
  { path: '/balance', label: '잔액조회' },
  { path: '/autotransfer', label: '자동이체등록' },
  { path: '/card', label: '카드관리' },
  //{ path: '/logout  ', label: '로그아웃' },
];

export default function NavigationBar() {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();

  return (
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
    </nav>
  );
}
