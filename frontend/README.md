# Frontend

React/Vite 기반 사용자 화면을 개발하는 디렉터리입니다.

## 예정 작업

- 자연어 입력 화면
- 실행 결과 및 승인 요청 UI
- Backend Gateway API 연동

## 개발 서버 실행 방법

nvm 등으로 node.js랑 npm 설치했다 가정

node --version, -npm --version

cd frontend

npm install

npm run dev

## Feature Slice Design

FSD(Feature-Sliced Design)는 프론트엔드 코드를 '기능(Feature)'과 '계층(Layer)' 중심으로 나누는 설계 방법론입니다. 커다란 앱을 작은 블록 여러 개로 조립하는 방식과 같습니다.

🧱 FSD의 주요 4단계 계층 (가장 핵심)아래로 갈수록 독립적이고, 위로 갈수록 아래의 코드를 가져와서 사용합니다.

shared (공유)앱 전체에서 쓰는 가장 기초적인 도구들입니다.

예: 공통 버튼, API 통신 코드(axios), 테마 설정, 공통 타입.특징: 다른 계층의 코드를 절대로 가져오지 않습니다.

entities (엔티티 - 비즈니스 핵심)도메인(업무 단위)의 핵심 데이터 모델과 관련된 것들입니다.

예: User(사용자), Product(상품) 정보.

특징: shared 계층의 코드만 가져와서 씁니다.features (기능)

사용자가 실제로 '행동'하는 기능 단위입니다.
예: 장바구니 담기, 좋아요 버튼, 로그인 폼.

특징: entities와 shared 계층을 조합해서 만듭니다.widgets (위젯)화면에 보이는 커다란 덩어리(블록)입니다.

예: 상품 목록 페이지의 헤더, 상품 카드 그리드.특징: features와 entities를 합쳐서 완성된 하나의 화면 조각을 만듭니다.

```txt
src/
 ┣ app/          # 앱 진입점, 모바일/웹 라우팅, 실시간 통신 전역 Provider
 ┣ pages/        # 금융 화면 (예: 뱅킹 홈, Agent 채팅방)
 ┣ widgets/      # 대형 블록 (예: 자산 현황 요약 보드, Agent 대화창 컴포넌트)
 ┣ features/     # Agent 액션 (예: 송금하기, 챗봇-주식-매수, 실시간 알림 켜기)
 ┣ entities/     # 금융 데이터 모델 (예: 유저 신용도, 계좌 실시간 잔액 데이터)
 ┗ shared/       # 최하위 공통 계층
   ┗ ui/         # [★여기에 Atomic Design 적용]
     ┣ atoms/    # 순수 금융 UI 소부품 (예: 자산 표시용 Typography, 대시보드용 배지)
     ┗ molecules/# 단순 조합 (예: Input + 단위 Label 버튼)
```

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
]);
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x';
import reactDom from 'eslint-plugin-react-dom';

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
]);
```
