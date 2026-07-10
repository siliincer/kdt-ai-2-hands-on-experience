# Router Scaffold — RealFinance

React + Vite + Capacitor 환경을 위한 `createHashRouter` 기반 라우터 스캐폴딩.

## 배경

기존 `App.tsx`는 1319줄의 단일 컴포넌트로 모든 화면(송금, 잔액, 소비분석 등)을 채팅 메시지 상태 머신 안에서 인라인 렌더링했다.
라우터 스캐폴딩을 통해 각 화면을 독립 URL 라우트로 분리했다.

**Capacitor 환경에서 `file://` 프로토콜을 사용하므로 `BrowserRouter` 대신 `createHashRouter`를 사용한다.**

## 라우트 구조

| 경로 | 컴포넌트 | 설명 |
|------|----------|------|
| `/login` | `LoginRoute` | 로그인 화면 |
| `/` | `App` | 메인 채팅 UI |
| `/transfer` | `TransferRoute` | 송금 |
| `/balance` | `BalanceRoute` | 잔액 조회 |
| `/spending` | `SpendingRoute` | 소비 분석 |
| `/transactions` | `TransactionsRoute` | 거래 내역 |
| `/bill` | `BillRoute` | 카드 청구서 |
| `/budget` | `BudgetRoute` | 예산 관리 |
| `/autotransfer` | `AutoTransferRoute` | 자동 이체 |
| `/card` | `CardRoute` | 카드 정보 |
| `/error` | `ErrorMessageRoute` | 에러 메시지 시나리오 데모 (잔액부족/잘못된계좌/한도초과/네트워크오류) |
| `*` | `ErrorRoute` | 404 에러 카드 |

## 파일 구조

```
src/
├── router.tsx                  # createHashRouter 설정
├── main.tsx                    # RouterProvider 마운트
└── app/
    ├── App.tsx                 # 메인 채팅 UI (/ 라우트)
    └── routes/
        ├── LoginRoute.tsx
        ├── TransferRoute.tsx
        ├── BalanceRoute.tsx
        ├── SpendingRoute.tsx
        ├── TransactionsRoute.tsx
        ├── BillRoute.tsx
        ├── BudgetRoute.tsx
        ├── AutoTransferRoute.tsx
        ├── CardRoute.tsx
        ├── ErrorMessageRoute.tsx
        └── ErrorRoute.tsx
```

## 네비게이션 흐름

> ⚠️ **변경 이력**: 초기 설계는 chip 클릭 시 `navigate()`로 별도 라우트 페이지를 여는 방식이었으나, 채팅 UI가 완전히 우회되는 회귀(버그 2, 아래 참조)가 발견되어 **`onAddMsg()`로 채팅 말풍선에 인라인 렌더링하는 방식으로 교체**되었다. `CARD_ROUTE` 맵은 더 이상 존재하지 않는다. `/transfer` 등 라우트는 채팅과 **별개의 진입 경로**(직접 URL 접근용)로만 남아있다.

```
채팅 chip 클릭 / 자연어 입력
    ↓
routeMsg(text) 또는 send() 내 키워드 분기
    ↓
onAddMsg({ from: "ai-transfer" 등 }) — msgs 배열에 인라인 추가
    ↓
MsgRenderer가 해당 카드 컴포넌트를 채팅 말풍선으로 렌더링
```

라우트 페이지(`/transfer` 등)는 채팅과 독립적으로 동일 화면에 직접 접근하기 위한 경로이며, chip 클릭으로는 더 이상 진입하지 않는다.

## 각 라우트 공통 구조

모든 카드 라우트는 하단에 공통 푸터를 가진다:

```tsx
<footer>
  <button onClick={() => navigate("/")}>채팅으로 돌아가기</button>
  <button onClick={() => { sessionStorage.removeItem('rf_chat_msgs'); navigate("/"); }}>채팅 초기화</button>
</footer>
```

`채팅 초기화`는 `rf_chat_msgs` sessionStorage 키를 지우고 `/`로 이동한다. `App.tsx`가 마운트되며 저장된 로그가 없으므로 인사말부터 다시 시작한다.

## 스캐폴딩 범위 (현재)

- [x] `createHashRouter` 설정 (`src/router.tsx`)
- [x] `RouterProvider` 마운트 (`src/main.tsx`)
- [x] 10개 라우트 + 404 fallback
- [x] 채팅 chip → `onAddMsg()` 인라인 렌더링 (라우터 미개입)
- [x] 각 라우트: 채팅 복귀 버튼 + `채팅 초기화` (sessionStorage 연결 완료)
- [x] 채팅 메시지 로그 sessionStorage 영속화 (`rf_chat_msgs`) — 라우트 이동으로 `App` 언마운트돼도 유지
- [x] 헤더 "로그 지우기" 버튼 — 로그아웃 없이 채팅 로그만 즉시 초기화
- [x] `ai-error` 메시지 타입 — 잔액부족/잘못된계좌/한도초과/네트워크오류 등 시나리오별 키워드 매칭 + `/error` 라우트에서 버튼으로도 호출 가능
- [x] 생체 인증 로그인 UI (`LoginScreen`) — 버튼 클릭 시 지문 스캔 모달 표시 후 로그인, `LoginRoute`도 동일 컴포넌트 재사용

## 다음 단계 (미구현)

- [ ] 인증 가드 (`/login` 보호 라우트)
- [ ] 채팅↔라우트 공유 상태 (prefill, 승인 게이트)
- [ ] Capacitor 기기 빌드 검증 (`npx cap sync && npx cap open android`)
- [ ] `TransferRoute` 승인 게이트 (`ConfirmBottomSheet`) 연결
- [ ] 채팅에서 llm 에이전트를 불러오고 에이전트가 각 라우트를 불러오는 기능
- [ ] `ai-error` 실제 비즈니스 로직 연결 (현재는 키워드/버튼 트리거뿐 — 실제 송금 시 잔액 검증 등과 연동 안 됨)
- [ ] 생체 인증 실제 WebAuthn/디바이스 API 연동 (현재 `setTimeout` mock 모달)

## 에러 테스트 결과

### 라우트 오류 시나리오 (수동 검증)

| 테스트 | 입력 | 예상 결과 | 실제 결과 |
|--------|------|-----------|-----------|
| 존재하지 않는 경로 | `/#/없는경로` | ErrorRoute 렌더링 | ✅ 404 카드 출력 |
| 완전 랜덤 경로 | `/#/aaa/bbb/ccc` | ErrorRoute 렌더링 | ✅ 404 카드 출력 |
| 빈 해시 | `/#/` | App (채팅) 렌더링 | ✅ 정상 |
| 직접 라우트 입력 | `/#/transfer` | TransferRoute 렌더링 | ✅ 별도 라우트로 정상 접근 가능 (채팅 인라인과 별개) |
| 브라우저 뒤로가기 | 라우트 → `←` 버튼 | 이전 라우트 복귀 | ✅ 수정 완료 (sessionStorage 로그인 영속) |
| 채팅 복귀 버튼 | 각 라우트 하단 버튼 | `/#/` 이동 | ✅ 수정 완료 |

### 평가 중 발견된 회귀 및 수정

---

**회귀 1 (ooo evaluate Stage 2 REJECT — score 0.68)**

- **문제**: `TransferRoute.tsx`의 송금하기 버튼이 `onClick={() => setDone(true)}`로 구현되어 원래 `onApproval()` → `ConfirmBottomSheet` 게이트를 우회
- **영향**: 확인 절차 없이 완료 상태로 전환 — 금융 앱 치명적 동작 오류
- **수정**: 버튼을 stub으로 교체

```tsx
// 수정 전 (회귀)
onClick={() => setDone(true)}

// 수정 후 (stub)
onClick={() => { /* stub: approval flow wired in next iteration */ }}
```

- **파일**: `src/app/routes/TransferRoute.tsx:158`
- **상태**: ConfirmBottomSheet 연결은 다음 단계 미구현 항목으로 이전

---

**버그 2: 카드 화면이 채팅 말풍선 대신 별도 페이지로 렌더링**

- **문제**: `send()` 내 `navigate(cardRoute)` 블록이 채팅 메시지 추가 대신 라우트 이동을 실행. chip 클릭도 동일
- **영향**: 채팅 UI가 완전히 우회되어 대화 흐름 단절
- **수정**: navigate 블록 제거 → `setMsgs()` 인라인 렌더링 복원. `MsgRenderer`에 ai-transfer/ai-balance 등 10개 카드 타입 복원. chip/사이드바 메뉴 전부 `onAddMsg()` 직접 호출로 교체
- **파일**: `src/app/App.tsx`

---

**버그 3: 라우트 이동 후 채팅 복귀 시 로그인 화면 표시**

- **근본 원인**: `isLoggedIn = useState(false)` — `/#/transfer` 이동 시 App 컴포넌트 언마운트 → 복귀 시 재마운트 → 상태 초기화
- **영향**: 카드 라우트(`/transfer` 등) 에서 `/#/` 복귀 시마다 로그인 화면 출력
- **수정**:

```tsx
// 수정 전
const [isLoggedIn, setIsLoggedIn] = useState(false);

// 수정 후
const [isLoggedIn, setIsLoggedIn] = useState(() => sessionStorage.getItem('rf_logged_in') === '1');

// 로그인 시
sessionStorage.setItem('rf_logged_in', '1');

// 로그아웃 시
sessionStorage.removeItem('rf_logged_in');
```

- `LoginRoute.tsx`: `navigate("/")` → `navigate("/", { replace: true })` — 히스토리에서 `/login` 항목 제거
- **파일**: `src/app/App.tsx`, `src/app/routes/LoginRoute.tsx`

---

### 대화형 송금 말풍선 (`ai-transfer-confirm`) 사용법

채팅에는 두 가지 송금 인터페이스가 존재한다.

| 인터페이스 | 컴포넌트 | 트리거 조건 |
|-----------|---------|-----------|
| **폼 카드** | `TransferCard` | 송금 관련 키워드 (`"송금"`, `"보내"`, `"이체"`) 또는 부분 정보 |
| **대화형 말풍선** | `TransferConfirmBubble` | 이름 + 은행 + 계좌 + 금액 **4개 모두** 파싱 성공 시 |

**대화형 말풍선 트리거 방법:**

받는사람 이름, 은행명, 계좌번호, 금액을 **한 메시지에 모두** 입력한다.

```
예시 입력:
이서연 신한은행 110-123-456789 5만원 보내줘
김철수 카카오뱅크 3333-01-1234567 100000원 이체
```

조건 충족 시 렌더링 결과:

```
┌─────────────────────────────────────────┐
│ 이서연님 · 신한은행 · 110-123-456789에게  │
│ 50,000원을 송금하시겠어요?                │
│                                         │
│  [지금 송금]        [예약 송금]           │
└─────────────────────────────────────────┘
```

각 값(이름, 은행, 계좌, 금액)을 말풍선 내에서 직접 편집 가능 (민트색 점선 밑줄 탭).
"지금 송금" → `ConfirmBottomSheet` 최종 확인 → 완료 메시지 채팅 출력.

**조건 미충족 시** (은행/계좌 없이 `"이서연에게 5만원 보내줘"`) → 폼 카드 자동 표시.

**파싱 로직**: `src/app/App.tsx` — `parseContactText()` + `parseTransferIntent()` 결합, `send()` 내 `type === "ai-transfer"` 분기

### 채팅으로 라우트를 호출하는 UI

`ai-error`는 `/error` 라우트가 실제로 존재하며, 채팅 키워드 입력은 해당 라우트로 **이동하지 않고** 같은 메시지를 채팅에 인라인으로 호출하는 방식이다(버그 2 수정 이후 정착된 패턴과 동일). `/error` 라우트는 버튼 클릭 시 채팅에 메시지를 삽입하고 `/`로 이동한다. 생체 인증은 별도 라우트 없이 기존 `/login` 라우트(`LoginScreen`)를 그대로 공유한다. 로그 지우기는 채팅 화면 자체의 기능이라 라우트 대상이 아니다.

| UI | 트리거 | 대응 라우트 | 파일 |
|----|--------|------------|------|
| `ai-error` — 잔액 부족 | 채팅에 `"잔액"` + `"부족"` 포함 입력 | `/error` (버튼) | `src/app/App.tsx` `send()` 내 `resolveErrorText()`, `src/app/routes/ErrorMessageRoute.tsx` |
| `ai-error` — 잘못된 계좌번호 | `"계좌"` + (`"잘못"` \| `"틀"`) 포함 입력 | `/error` (버튼) | 상동 |
| `ai-error` — 송금 한도 초과 | `"한도"` 포함 입력 | `/error` (버튼) | 상동 |
| `ai-error` — 네트워크 오류 | `"네트워크"` \| `"연결"` 포함 입력 | `/error` (버튼) | 상동 |
| `ai-error` — 일반 실패 | `"에러"`/`"오류"`/`"실패"`/`"안 돼"` 등 그 외 매칭 없을 때 fallback | `/error` 없음 (fallback은 라우트에 없음) | 상동 |
| 생체 인증 로그인 | 로그인 화면 "생체 인증으로 로그인" 버튼 → 지문 스캔 모달 표시 → 자동 로그인 | `/login` (기존 로그인 폼과 같은 라우트·같은 `LoginScreen` 컴포넌트를 공유. `!isLoggedIn`일 때 `/`에서도 동일 컴포넌트 렌더링) | `src/app/components/LoginScreen.tsx` — `handleBiometricLogin()`, `scanning` 상태로 모달 표시 |
| 로그 지우기 | 채팅 화면 헤더 휴지통 아이콘 (로그아웃과 별개, 로그인 상태 유지) | 없음 (채팅 화면 자체의 헤더 버튼, 별도 라우트로 뺄 이유 없음) | `src/app/App.tsx` — 헤더의 `Trash2` 버튼 |

**주의**: 위 트리거는 모두 데모/키워드 기반이며, 실제 송금 로직(계좌 잔액 검증, 실제 계좌번호 유효성 검사, 네트워크 요청 실패 감지)과는 아직 연결되지 않았다.

### 알려진 미검증 항목

- Capacitor `file://` 실기기 라우팅 (에뮬레이터/기기 미실행)
- iOS WKWebView 해시 라우터 동작
- TransferRoute 승인 게이트 (stub — ConfirmBottomSheet 미연결)
- 생체 인증 로그인 (mock — 실제 기기 WebAuthn/지문 API 미검증)

## 실행

```bash
npm run dev     # 개발 서버 (http://localhost:5173)
npm run build   # Capacitor 배포용 빌드 (dist/)
npx cap sync    # 빌드 결과 Android/iOS 동기화
```
