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
  login: (userData) => {
    // 새로고침 시 이름/식별자를 복원할 수 있도록 세션에 저장한다(App 복원 effect 가 읽음).
    sessionStorage.setItem('rf_user_id', userData.id);
    sessionStorage.setItem('rf_user_name', userData.name);
    set({ user: userData, isLoggedIn: true });
  },
  logout: () => {
    sessionStorage.removeItem('rf_access_token');
    sessionStorage.removeItem('rf_logged_in');
    sessionStorage.removeItem('rf_user_id');
    sessionStorage.removeItem('rf_user_name');
    set({ user: null, isLoggedIn: false });
  },
}));
