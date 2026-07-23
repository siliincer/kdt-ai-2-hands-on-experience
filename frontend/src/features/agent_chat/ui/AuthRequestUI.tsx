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
 * 전달되고(계약 7.2), 결과 상태(verified/failed/cancelled)에 따라 후속이 SSE 로
 * 흘러온다. 취소도 Backend 에 제출해야 Agent 쪽 interrupt 가 정리된다 — 로컬에서만
 * 끝낸 것처럼 표시하면 Agent thread 가 그 Step 에 계속 멈춰 있어 이후 턴이 막힌다.
 */
export const AuthRequestUI: ToolCallMessagePartComponent = ({ args }) => {
  const authenticate = useAuthenticate();
  const a = (args ?? {}) as AuthRequestArgs;
  const authContextId = a.authContextId;

  const [password, setPassword] = useState('');
  const [phase, setPhase] = useState<
    'idle' | 'verifying' | 'done' | 'cancelled' | 'error'
  >('idle');

  const submit = async () => {
    if (!authContextId || !password || phase === 'verifying') return;
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
    if (!authContextId || phase === 'verifying' || phase === 'done') return;
    setPhase('verifying');
    try {
      await authenticate(authContextId, undefined, true);
      setPhase('cancelled');
    } catch {
      setPhase('error');
    }
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
        disabled={phase === 'verifying'}
        placeholder="비밀번호"
        className={`${HITL_INPUT} disabled:opacity-50`}
      />

      <div className={HITL_ACTIONS_ROW}>
        <button
          type="button"
          onClick={cancel}
          disabled={phase === 'verifying'}
          className={`${HITL_BTN_SECONDARY} disabled:opacity-50`}
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!password || phase === 'verifying'}
          className={HITL_BTN_PRIMARY}
        >
          {phase === 'verifying' ? '확인 중...' : '인증'}
        </button>
      </div>
    </div>
  );
};
