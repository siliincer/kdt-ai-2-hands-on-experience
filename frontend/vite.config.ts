import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 1. 모노리포 루트 폴더의 절대 경로를 지정합니다.
  const monorepoRoot = path.resolve(__dirname, '../');

  // 2. 모노리포 루트 폴더에서 환경변수를 로드합니다.
  // 세번째 인자를 ''로 두면 VITE_ 접두사가 없어도 모두 로드
  const env = loadEnv(mode, monorepoRoot, '');

  const isProd = mode === 'production';
  //const isDev = mode === 'development';

  return {
    plugins: [react(), tailwindcss()],
    envDir: monorepoRoot,
    server: {
      proxy: {
        // 프론트엔드에서 '/api'로 시작하는 요청을 감지하면 아래 설정을 적용합니다.
        '/api': {
          // 실제 백엔드 API 서버 주소 (본인의 백엔드 포트에 맞게 수정하세요)
          target: String(env.VITE_API_BASE_URL),
          // 만약 백엔드 주소가 로컬환경이 아닌 실제 배포된 서버 주소
          // (예: https://myapp.com)라면 target에 해당 주소를 적어주시면 됩니다.

          // 대상 서버(target)의 호스트 헤더가 변경되도록 허용 (CORS 예방 필수 설정)
          changeOrigin: true,

          // 필요 시 URL 주소 변환 (예: 프론트 /api/users -> 백엔드 /users로 /api를 제거하고 싶을 때 사용)
          // 만약 백엔드 엔드포인트 자체에도 /api가 포함되어 있다면 아래 주석을 풀지 마세요.
          // rewrite: (path) => path.replace(/^\/api/, ''),

          // 보안 연결(https) 검증 여부 (로컬 http 환경이므로 false)
          secure: isProd,
        },
      },
    },
  };
});
