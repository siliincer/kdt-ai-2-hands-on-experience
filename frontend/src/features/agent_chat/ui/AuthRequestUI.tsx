import { useState } from 'react';

import { ShieldCheck, X } from 'lucide-react';

import { useAuthenticate } from '../model/authenticateContext';

import { OutcomeChip } from './OutcomeChip';
import {
  HITL_ACTIONS_ROW,
  HITL_BTN_PRIMARY,
  HITL_BTN_SECONDARY,
  HITL_CARD,
  HITL_INPUT,
} from './uiStyles';

import type { AuthRequestArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * authentication_required(auth_request) 툴 파트 렌더러 (HITL, 계약 3.8).
 * 추가 인증은 비밀번호 재확인으로 처리한다. 비밀번호 원문은 Backend 인증 API 로만
 * 전달되고(계약 7.2), 결과 상태(verified/failed)에 따라 후속이 SSE 로 흘러온다.
 */
export const AuthRequestUI: ToolCallMessagePartComponent = ({ args }) => {
  const authenticate = useAuthenticate();
  const a = (args ?? {}) as AuthRequestArgs;
  const authContextId = a.authContextId;

  const [password, setPassword] = useState('');
  const [phase, setPhase] = useState<
    'idle' | 'verifying' | 'cancelling' | 'done' | 'cancelled' | 'error'
  >('idle');

  const busy = phase === 'verifying' || phase === 'cancelling';

  const submit = async () => {
    if (!authContextId || !password || busy) return;
    setPhase('verifying');
    try {
      const status = await authenticate(authContextId, password);
      setPhase(status === 'verified' ? 'done' : 'error');
    } catch {
      setPhase('error');
    }
    setPassword('');
  };

  const cancel = async () => {
    if (!authContextId || busy || phase === 'done' || phase === 'cancelled') {
      return;
    }
    // 취소도 Backend 로 알려 Agent 를 cancelled 로 재개해야 한다. 그래야 워크플로우가
    // 종료되고 terminal done 이 와서 채팅 입력이 다시 열린다(로컬 표시만 바꾸면 채팅이
    // 계속 대기 상태로 잠긴다).
    setPhase('cancelling');
    try {
      await authenticate(authContextId, '', { cancel: true });
    } catch {
      // 취소 통지 실패는 무시하고 UI 는 취소로 마감한다(사용자 관점 종료).
    }
    setPassword('');
    setPhase('cancelled');
  };

  if (phase === 'done') {
    return <OutcomeChip variant="success">인증을 확인했어요.</OutcomeChip>;
  }
  if (phase === 'cancelled') {
    return <OutcomeChip variant="cancel">인증을 취소했어요.</OutcomeChip>;
  }

  return (
    <div className={HITL_CARD}>
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-primary" />
        <p className="text-sm font-semibold text-foreground">
          {a.title ?? '비밀번호를 다시 입력해 주세요.'}
        </p>
      </div>

      {phase === 'error' ? (
        <div className="mb-2 inline-flex items-center gap-1.5 text-xs text-destructive">
          <X className="h-3.5 w-3.5" />
          비밀번호가 일치하지 않아요. 다시 입력해 주세요.
        </div>
      ) : null}

      <input
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') void submit();
        }}
        disabled={busy}
        placeholder="비밀번호"
        className={`${HITL_INPUT} disabled:opacity-50`}
      />

      <div className={HITL_ACTIONS_ROW}>
        <button
          type="button"
          onClick={() => void cancel()}
          disabled={busy}
          className={`${HITL_BTN_SECONDARY} disabled:opacity-50`}
        >
          {phase === 'cancelling' ? '취소 중...' : '취소'}
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!password || busy}
          className={HITL_BTN_PRIMARY}
        >
          {phase === 'verifying' ? '확인 중...' : '인증'}
        </button>
      </div>
    </div>
  );
};
