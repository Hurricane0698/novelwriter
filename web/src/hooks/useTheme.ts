import { useState, useEffect } from 'react';

type Theme = 'light' | 'dark';

function readStoredTheme(): Theme {
    if (typeof window === 'undefined') return 'dark';
    try {
        const saved = localStorage.getItem('novwr_theme');
        if (saved === 'light' || saved === 'dark') return saved;
    } catch {
        // SecurityError (storage denied) or other — fall back silently
    }
    return 'dark';
}

export function useTheme() {
    const [theme, setTheme] = useState<Theme>(readStoredTheme);

    useEffect(() => {
        const root = document.documentElement;
        // :root is dark by default. Only add .light when light mode is active.
        if (theme === 'light') {
            root.classList.add('light');
        } else {
            root.classList.remove('light');
        }
        // Set color-scheme so native controls/scrollbars match the theme
        root.style.colorScheme = theme;
        try {
            localStorage.setItem('novwr_theme', theme);
        } catch {
            // QuotaExceededError or SecurityError — ignore
        }
    }, [theme]);

    const toggleTheme = () => {
        setTheme(prev => prev === 'light' ? 'dark' : 'light');
    };

    return { theme, setTheme, toggleTheme };
}
