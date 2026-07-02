import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettierPlugin from 'eslint-plugin-prettier';
import eslintConfigPrettier from 'eslint-config-prettier';

export default tseslint.config(
  // 1. 글로벌 무시 설정 (dist 폴더 제외)
  {
    ignores: ['dist'],
  },

  // 2. 기본 추천 설정들 결합
  js.configs.recommended,
  ...tseslint.configs.recommended,

  // 3. React 및 프로젝트 전용 설정
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 'latest', // esm 최신
      globals: globals.browser, // 코드가 실행되는 환경의 전역 변수들을 알려줍니다.
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      prettier: prettierPlugin, // Prettier 플러그인 등록
    },
    rules: {
      // React Hooks 추천 규칙 적용
      ...reactHooks.configs.recommended.rules,

      // Vite Hot Reload 관련 규칙
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],

      // Prettier 포맷팅 오류를 ESLint 에러로 표시 (오타 수정)
      'prettier/prettier': 'error',
    },
  },

  // 4. Prettier와 충돌하는 ESLint 규칙 비활성화 (가장 마지막에 위치)
  eslintConfigPrettier,
);
