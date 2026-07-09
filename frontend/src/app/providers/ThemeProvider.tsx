import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import {
  STORAGE_KEY,
  getInitialTheme,
  applyThemeClass,
} from '@/shared/lib/theme';
import { ThemeContext } from '@/shared/context/ThemeContext';
import type { ThemeMode } from '@/shared/types/types';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeMode>(getInitialTheme);

  useEffect(() => {
    applyThemeClass(theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      toggleTheme: () =>
        setTheme((prev) => (prev === 'dark' ? 'light' : 'dark')),
    }),
    [theme],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}
