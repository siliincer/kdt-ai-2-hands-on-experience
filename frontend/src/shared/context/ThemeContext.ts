import { createContext } from 'react';
import type { ThemeContextValue } from '@/shared/types/interface';

export const ThemeContext = createContext<ThemeContextValue | null>(null);
