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
  const [phase, setPhase] = useState<'idle' | 'verifying' | 'done' | 'error'>(
    'idle',
  );

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

  const cancel = () => {
    if (phase === 'verifying' || phase === 'done') return;
    setPhase('done');
    // 취소는 인증을 제출하지 않는다. 후속 흐름은 사용자가 다시 시도하거나 종료한다.
  };

  if (phase === 'done') {
    return <OutcomeChip variant="success">인증을 확인했어요.</OutcomeChip>;
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
