/**
 * Theme Context & Provider for AUREN Personal AI.
 * Supports Executive White (Light default), Dark Slate, Midnight Indigo, and Pure Obsidian (OLED).
 * Persists selection in localStorage and synchronizes with user profile preferences.
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

export type ThemeMode = 'light' | 'dark' | 'midnight' | 'obsidian';

interface ThemeContextType {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: 'light',
  setTheme: () => {},
});

export const applyThemeToDom = (theme: ThemeMode) => {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.classList.remove('theme-light', 'theme-dark', 'theme-midnight', 'theme-obsidian');
    document.documentElement.classList.add(`theme-${theme}`);
    try {
      localStorage.setItem('auren_theme', theme);
    } catch {
      // In case localStorage is blocked in some environments
    }
  }
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    if (typeof window !== 'undefined') {
      try {
        // Migration check: ensure White is immediate default for users
        const whiteMigrated = localStorage.getItem('auren_white_bg_default_v1');
        if (!whiteMigrated) {
          localStorage.setItem('auren_white_bg_default_v1', 'true');
          localStorage.setItem('auren_theme', 'light');
          return 'light';
        }

        const saved = localStorage.getItem('auren_theme') as ThemeMode;
        if (saved && ['light', 'dark', 'midnight', 'obsidian'].includes(saved)) {
          return saved;
        }
      } catch {
        // Fallback
      }
    }
    return 'light';
  });

  const setTheme = useCallback((newTheme: ThemeMode) => {
    setThemeState(newTheme);
    applyThemeToDom(newTheme);
  }, []);

  useEffect(() => {
    applyThemeToDom(theme);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
