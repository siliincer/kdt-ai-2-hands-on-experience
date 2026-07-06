# Agent Docs

agent 서비스(LangGraph 금융 에이전트) 문서입니다.

> 처음이라면 **[agent/README.md](../README.md)** 부터 — 폴더 구조와
> 동작 원리를 코드 지식 없이 읽을 수 있는 전체 개요입니다.

## 문서 목록

- [agent-integration.md](agent-integration.md) — 아키텍처, 포팅 결정사항,
  API 계약, state 설계, tool 구현 가이드, 제약과 향후 과제
- [agent-sheet-v2-review.md](agent-sheet-v2-review.md) — 스프레드시트 v2
  검토 결과 (변경 요약, 모순 목록, state 개편 기록, sync 스크립트)
- [sheet-cleanup-guide.md](sheet-cleanup-guide.md) — **스프레드시트 수정
  지시서**: 이 문서만 보고 시트를 정리할 수 있게 탭/행/컬럼 단위로 작성
- [tool-api-integration.md](tool-api-integration.md) — **서비스 간 통신 경로
  총괄** (frontend↔backend↔agent↔원장 3경로), tool→은행 API 경계
  (BankClient, mock-financial-service), frontend 구조화 UI 계약
  (ChatResponse.ui, ui_type별 payload)

## 실행 검증 노트북

`agent/notebooks/`에 실행 출력이 포함된 노트북 3권이 있습니다:
01 잔액조회 단계별 / 02 멀티턴 / 03 타인송금 시나리오.
