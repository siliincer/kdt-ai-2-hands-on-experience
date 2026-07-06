import { Link, useLocation } from 'react-router';

const links = [
  { path: '/', label: '홈' },
  { path: '/transfer', label: '송금' },
  { path: '/spending', label: '소비분석' },
  { path: '/transactions', label: '거래내역' },
  { path: '/budget', label: '예산관리' },
];

export default function NavigationBar() {
  const location = useLocation();

  return (
    <nav className="flex flex-wrap gap-2">
      {links.map((link) => (
        <Link
          key={link.path}
          to={link.path}
          className={`rounded-full border px-3 py-2 text-sm transition ${
            location.pathname === link.path
              ? 'border-emerald-400 bg-emerald-500/10 text-emerald-200'
              : 'border-white/10 text-slate-300 hover:border-emerald-400/40 hover:text-emerald-200'
          }`}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
