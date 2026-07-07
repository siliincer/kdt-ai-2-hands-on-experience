// 백엔드 UserReadSchema와 동일한 타입
export interface UserReadResponse {
  id: string;
  email: string;
  name: string | null;
}

// 회원가입 요청 페이로드
export interface SignupRequest {
  email: string;
  password: string;
  name?: string;
}

// 로그인 응답 타입
export interface LoginApiResponse {
  access_token: string;
  token_type: string;
  user: UserReadResponse;
}

// 로그인 요청 페이로드
export interface LoginRequest {
  email: string;
  password: string;
}
