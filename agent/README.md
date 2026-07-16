# Agent — 금융 AI 에이전트

"김철수한테 5만원 보내줘" 같은 **자연어 요청을 받아, 안전장치를 거쳐, 실제로
실행**하는 서비스입니다 (Fake Money 기반). FastAPI로 떠 있고(포트 8001),
backend 게이트웨이가 채팅을 이쪽으로 넘겨줍니다.

이 문서는 agent 폴더를 처음 보는 팀원(프론트/백엔드)을 위한 전체 개요입니다.

---

## 1. 대화 한 턴이 처리되는 흐름

```
사용자 발화 ("김철수한테 5만원 보내줘")
   │
   ▼
① 가드레일 검사 ─── 위험한 요청("이전 지침 무시...")은 여기서 차단
   │
   ▼
② 업무 분류 ─────── 어떤 업무인가? (잔액조회 / 타인송금 / 해당 없음)
   │
   ▼
③ 워크플로우 실행 ── 해당 업무의 절차를 스텝별로 진행
   │                  (수취인 확인 → 금액 확인 → 잔액 확인 → 정책 검사 → ...)
   │
   ├─ 정보가 부족하면 ──────┐
   ├─ 승인이 필요하면 ──────┤ ⏸ 멈추고 사용자에게 묻는다
   ├─ 본인 인증이 필요하면 ─┘   (답을 받으면 멈춘 지점부터 재개 ▶)
   │
   ▼
④ 실행 + 응답 ────── 송금 실행(원장 차감), 감사 로그, 결과 문장 반환
```

핵심은 **"멈추고 묻기"** 입니다. 금융 앱이므로 에이전트가 마음대로 실행하지
않고, 정보가 부족하거나 돈이 움직이기 직전에는 반드시 멈춰서 사용자의
입력·승인·인증을 받습니다. HTTP에서는 이 멈춤이 `status: "waiting_input"`
응답으로 나타나고, 클라이언트가 `thread_id`를 회송하며 답하면 이어집니다.

## 2. 폴더 구조

```
agent/
├── src/agent/
│   ├── main.py               # FastAPI 진입점 — POST /chat, GET /health
│   ├── service.py            # 대화 한 턴 실행 (멈춤/재개, thread_id 관리)
│   ├── schemas.py            # /chat 요청·응답 형식 정의
│   │
│   ├── graph.py              # 전체 흐름 조립 (①→②→③ 연결)
│   ├── nodes.py              # 가드레일·업무분류 등 공통 단계 함수
│   ├── subgraph_builder.py   # 워크플로우 YAML → 실행 그래프 자동 변환 엔진
│   ├── workflow_matcher.py   # ② 업무 분류 (LLM + 키워드 폴백)
│   ├── workflow_loader.py    # config YAML 읽기
│   ├── state.py              # 대화 진행 상황을 담는 데이터 상자 정의
│   │
│   ├── tools/
│   │   ├── bank_tools.py     # 실제 기능들 — 금액 파싱, 계좌 확인, 승인 카드,
│   │   │                     #   송금 실행 등 (워크플로우의 각 스텝이 호출)
│   │   └── registry.py       # "스텝 이름 → 함수" 연결표
│   │
│   ├── bank_client.py        # 돈 데이터 접근 경계 — 계좌/수취인/송금은
│   │                         #   반드시 여기를 거침 (local/http 전환 가능)
│   ├── policy/
│   │   └── guardrail_engine.py  # ① 가드레일 규칙 검사
│   ├── data/
│   │   └── mock_bank.py      # 내장 mock 원장 (local 모드에서 사용)
│   ├── config/               # 워크플로우 정의 YAML (팀 스프레드시트에서 생성)
│   ├── llm.py                # OpenAI 연결 (키 없으면 규칙 기반으로 동작)
│   └── paths.py              # config 경로 상수
│
├── scripts/
│   └── sync_config_from_sheets.py  # 스프레드시트 → config YAML 재생성
├── notebooks/                # 실행 과정을 눈으로 보는 노트북 3권 (아래 6절)
├── tests/                    # 자동 테스트 (LLM 키 없이 전부 실행됨)
└── docs/                     # 상세 설계 문서 (아래 7절)
```

## 3. 꼭 알아야 할 개념 4가지

**① 업무 절차는 코드가 아니라 스프레드시트에 있다.**
"수취인 확인 → 금액 확인 → 승인 → 실행" 같은 절차(스텝과 분기)는 팀
스프레드시트에 정의되어 있고, 스크립트가 이를 `config/*.yaml`로 내려받으면
엔진(`subgraph_builder.py`)이 자동으로 실행 그래프를 만듭니다. **절차를
바꾸고 싶으면 시트를 고치고 재생성하면 됩니다** — 파이썬 수정 불필요.

**② state = 대화 진행 상황을 담는 상자.**
"지금 어느 스텝인지, 수취인은 누구로 확정됐는지, 금액은 얼마인지"가 전부
state에 쌓입니다. 엔진용 고정 필드(응답 문장, 분기 키 등)와 업무 데이터
칸(`data` — `transfer.recipient` 같은 이름표가 붙은 값들)으로 나뉩니다.

**③ 멈추고 묻기(interrupt)는 전부 같은 메커니즘이다.**
"누구에게 보낼까요?" 되묻기, 송금 승인 카드, 본인 인증 — 셋 다 그래프가
멈추고 사용자 답을 기다리는 동일한 방식입니다. 대화 상태는 `thread_id`별로
저장되어, 같은 `thread_id`로 답이 오면 멈춘 지점부터 이어집니다.

**④ 돈 데이터는 반드시 bank_client를 거친다.**
계좌 조회·송금 실행 같은 원장 작업은 tool이 직접 하지 않고
`bank_client.py`를 통합니다. 환경변수 하나로 내장 mock(`local`, 기본)과
실제 원장 서비스 호출(`http` → mock-financial-service:8002)을 전환합니다.

## 4. 다른 서비스와의 접점 (내 파트는 뭘 보면 되나)

| 담당 | 접점 | 봐야 할 것 |
|---|---|---|
| **프론트** | 채팅 응답의 `ui` 필드로 화면을 그린다 — 계좌 카드 목록, 승인 카드(버튼 라벨 포함) 등. 버튼 라벨("송금하기")을 **그대로 다음 메시지로 보내면** 에이전트가 인식 | `frontend/src/features/agent_chat/api/types.ts` (타입), [docs/README.md](docs/README.md) 3절 (ui 종류별 예시) |
| **백엔드** | `/api/v1/agent/chat`이 이 서비스의 `/chat`으로 프록시. 요청/응답을 그대로 전달만 하면 됨 | `backend/src/backend/api/agent_api.py`, `backend/src/backend/services/agent_client.py` |
| **원장(mock-financial-service)** | 에이전트가 http 모드에서 호출하는 계좌/송금 REST API | `mock-financial-service/README.md` (구현된 API와 에러 규칙) |

## 5. 직접 실행해 보기

```bash
# 레포 루트에서 (OPENAI_API_KEY 없어도 동작 — 규칙 기반 폴백)
uv sync
uv run uvicorn agent.main:app --reload --port 8001

# 잔액 조회 (한 턴에 완료)
curl -X POST localhost:8001/chat -H 'content-type: application/json' \
  -d '{"message":"생활비 통장 잔액 얼마야?"}'

# 송금 (멈추고 묻기 체험: 응답의 thread_id를 다음 요청에 넣어 "송금하기",
# "인증완료"를 차례로 보내면 완료된다)
curl -X POST localhost:8001/chat -H 'content-type: application/json' \
  -d '{"message":"김철수한테 5만원 보내줘"}'

# 테스트 (전부 LLM 키 없이 실행)
uv run pytest agent
```

## 6. 구조를 빠르게 이해하는 최단 경로 — 노트북 3권

`notebooks/`에 **실행 결과가 포함된** 노트북이 있습니다. 코드를 안 돌려도
GitHub에서 출력까지 그대로 볼 수 있습니다:

1. `01_balance_inquiry.ipynb` — 잔액조회가 스텝별로 어떻게 처리되는지
2. `02_multiturn.ipynb` — "멈추고 묻기"(interrupt)가 어떻게 동작하는지
3. `03_external_transfer.ipynb` — 송금 전 과정: 되묻기·승인·인증·실행 시나리오 8종

**직접 실행하려면** — 별도 pip/conda 설치 없이 `uv sync` 한 번이면 됩니다
(에이전트 코드와 ipykernel이 레포 루트 `.venv`에 들어감):

- **VS Code / Cursor**: 노트북을 열고 우상단 커널 선택에서
  **레포 루트의 `.venv`** (Python 3.11) 를 고르면 끝
- **브라우저(JupyterLab)**: 레포 루트에서 `uv run --with jupyter jupyter lab`

## 7. 더 알아보기 (docs/)

| 문서 | 내용 |
|---|---|
| [docs/README.md](docs/README.md) | **통합 문서** — 아키텍처·통신 경로, 계약별 정본과 변경 루틴, 채팅 API/UI 계약(ui 5종·회신 규약), 은행 API 경계, state 설계·tool 작성 가이드, 연결 현황과 파트별 인계 |
| [docs/naming-convention.md](docs/naming-convention.md) | step_id/tool_id 명명규칙과 시트 재작성 지시서 |

알아두면 좋은 제약: 대화 상태는 서버 메모리에만 있어서 **재시작하면 진행
중이던 대화가 사라지고**, 서버는 1개 프로세스로 띄워야 합니다 (개선 예정).
