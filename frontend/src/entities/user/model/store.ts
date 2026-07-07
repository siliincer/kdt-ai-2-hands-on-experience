// Zustand 스토어 (유저 정보, 로그인 상태)
import { create } from 'zustand';

interface UserState {
  user: { id: string; name: string } | null;
  isLoggedIn: boolean;
  login: (userData: { id: string; name: string }) => void;
  logout: () => void;
}

export const useUserStore = create<UserState>((set) => ({
  user: null,
  isLoggedIn: false,
  login: (userData) => set({ user: userData, isLoggedIn: true }),
  logout: () => {
    sessionStorage.removeItem('rf_access_token');
    sessionStorage.removeItem('rf_logged_in');
    set({ user: null, isLoggedIn: false });
  },
}));
