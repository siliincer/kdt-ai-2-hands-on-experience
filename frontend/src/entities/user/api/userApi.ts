import { customFetch } from '@/shared/api/customFetch';

import type {
  SignupRequest,
  LoginApiResponse,
  LoginRequest,
  UserReadResponse,
} from '@/shared/types/loginInterface';

/**
 * 회원가입 API
 * POST /backendApi/api/v1/users/signup
 */
export async function signupApi(
  payload: SignupRequest,
): Promise<UserReadResponse> {
  return customFetch<UserReadResponse>('/backendApi/api/v1/users/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

/**
 * 로그인 API
 * POST /backendApi/api/v1/users/login
 */
export async function loginApi(
  payload: LoginRequest,
): Promise<LoginApiResponse> {
  return customFetch<LoginApiResponse>('/backendApi/api/v1/users/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

/**
 * 로그아웃 API
 * POST /backendApi/api/v1/users/logout
 */
export async function logoutApi(): Promise<Record<string, never>> {
  const token = sessionStorage.getItem('rf_access_token') ?? '';
  return customFetch<Record<string, never>>('/backendApi/api/v1/users/logout', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });
}
