/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { clearLlmConfig } from '@/lib/llmConfigStore';

interface User {
    id: number;
    username: string;
    nickname: string | null;
    role: string;
    is_active: boolean;
    generation_quota: number;
    feedback_submitted: boolean;
    preferences: Record<string, unknown> | null;
}

interface AuthContextType {
    isLoggedIn: boolean;
    isLoading: boolean;
    user: User | null;
    login: (username: string, password: string) => Promise<void>;
    inviteRegister: (inviteCode: string, nickname: string) => Promise<void>;
    logout: () => Promise<void>;
    refreshQuota: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const queryClient = useQueryClient();

    const probe = useCallback(async () => {
        try {
            const res = await fetch(
                `${(import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')}/api/auth/me`,
                {
                    credentials: 'include',
                },
            );
            if (res.ok) {
                const data = (await res.json()) as User;
                setUser(data);
            } else {
                setUser(null);
            }
        } catch {
            setUser(null);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        probe();
    }, [probe]);

    const login = async (username: string, password: string) => {
        setIsLoading(true);
        try {
            await api.login(username, password);
            await probe();
        } catch (error) {
            setIsLoading(false);
            throw error;
        }
    };

    const inviteRegister = async (inviteCode: string, nickname: string) => {
        setIsLoading(true);
        try {
            await api.inviteRegister(inviteCode, nickname);
            await probe();
        } catch (error) {
            setIsLoading(false);
            throw error;
        }
    };

    const logout = async () => {
        try {
            await api.logout();
        } catch {
            // Clearing local app state is more important than surfacing logout transport failures.
        } finally {
            await queryClient.cancelQueries();
            queryClient.clear();
            clearLlmConfig();
            setUser(null);
            setIsLoading(false);
        }
    };

    const refreshQuota = async () => {
        if (!user) return;
        try {
            const quota = await api.getQuota();
            setUser(prev => prev ? { ...prev, ...quota } : null);
        } catch {
            // Silently fail — quota display is non-critical
        }
    };

    return (
        <AuthContext.Provider value={{ isLoggedIn: user !== null, isLoading, user, login, inviteRegister, logout, refreshQuota }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
