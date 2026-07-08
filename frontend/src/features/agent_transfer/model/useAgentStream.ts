import { useCallback, useEffect, useRef, useState } from 'react';

import { getSseTicket } from '../api/sseTicket';

import { CONNECT_URL, NAMED_EVENTS } from '../constants/constants';

import type {
  AgentStreamEvent,
  AgentStreamEventType,
  AgentStreamStatus,
} from '@/shared/types/sse';

import type {
  UseAgentStreamOptions,
  UseAgentStreamResult,
} from '@/features/agent_transfer/types/interface.ts';

/**
 * Agent 진행 이벤트를 SSE로 구독하는 훅.
 *
 * ADR-001: 티켓은 일회용이므로 네이티브 EventSource 자동재연결에 의존하지 않는다.
 * 이 훅이 재연결을 소유한다 — 끊기면 chat_session_id 로 티켓을 재발급받아
 * last_event_id 를 실어 다시 연결한다. [DONE] 이면 재연결하지 않는다.
 *
 * 렌더 최적화(BE_Technique #3): ms 단위로 쏟아지는 이벤트를 바로 setState 하지 않고
 * 버퍼에 쌓았다가 requestAnimationFrame 마다 한 번에 flush 한다.
 */
export function useAgentStream(
  options: UseAgentStreamOptions = {},
): UseAgentStreamResult {
  const { chatSessionId: initialChatSessionId, autoStart = false } = options;
  const maxRetries = options.maxRetries ?? 5;

  const [events, setEvents] = useState<AgentStreamEvent[]>([]);
  const [status, setStatus] = useState<AgentStreamStatus>('idle');
  const [chatSessionId, setChatSessionId] = useState<string | null>(
    initialChatSessionId ?? null,
  );
  const [error, setError] = useState<string | null>(null);

  // 콜백 내부에서 stale closure 를 피하기 위해 가변 상태는 ref 로 관리
  const esRef = useRef<EventSource | null>(null);
  const chatSessionIdRef = useRef<string | null>(initialChatSessionId ?? null);
  const lastEventIdRef = useRef<string | null>(null);
  const retryRef = useRef(0);
  const stoppedRef = useRef(false);
  const doneRef = useRef(false);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 이벤트 버퍼 + rAF flush
  const bufferRef = useRef<AgentStreamEvent[]>([]);
  const rafRef = useRef<number | null>(null);

  const flushBuffer = useCallback(() => {
    rafRef.current = null;
    if (bufferRef.current.length === 0) return;
    const pending = bufferRef.current;
    bufferRef.current = [];
    setEvents((prev) => [...prev, ...pending]);
  }, []);

  const enqueue = useCallback(
    (event: AgentStreamEvent) => {
      bufferRef.current.push(event);
      if (rafRef.current === null) {
        rafRef.current = requestAnimationFrame(flushBuffer);
      }
    },
    [flushBuffer],
  );

  // EventSource 만 정리(재연결 시 재사용). 타이머·rAF 는 건드리지 않음.
  const closeEventSource = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const teardown = useCallback(() => {
    closeEventSource();
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, [closeEventSource]);

  // 실제 연결(티켓 발급 → EventSource open). connectRef 로 감싸 재귀 재연결에 사용.
  const connectRef = useRef<() => Promise<void>>(async () => {});

  const scheduleReconnect = useCallback(() => {
    if (stoppedRef.current || doneRef.current) return;
    if (retryRef.current >= maxRetries) {
      setStatus('error');
      setError('스트림 재연결에 실패했습니다.');
      return;
    }
    retryRef.current += 1;
    const delay = Math.min(500 * 2 ** (retryRef.current - 1), 10_000);
    reconnectTimerRef.current = setTimeout(() => {
      void connectRef.current();
    }, delay);
  }, [maxRetries]);

  const connect = useCallback(async () => {
    if (stoppedRef.current) return;
    setStatus('connecting');
    setError(null);

    let ticket;
    try {
      ticket = await getSseTicket(chatSessionIdRef.current ?? undefined);
    } catch (e) {
      // 티켓 발급 실패(예: 401/네트워크) → 재연결 백오프
      setError(e instanceof Error ? e.message : '티켓 발급 실패');
      scheduleReconnect();
      return;
    }
    if (stoppedRef.current) return;

    chatSessionIdRef.current = ticket.chat_session_id;
    setChatSessionId(ticket.chat_session_id);

    const params = new URLSearchParams({
      sse_session_id: ticket.sse_session_id,
    });
    if (lastEventIdRef.current) {
      // 네이티브 EventSource 는 Last-Event-ID 헤더를 못 보내므로 쿼리로 재개점 전달
      params.set('last_event_id', lastEventIdRef.current);
    }

    const es = new EventSource(`${CONNECT_URL}?${params.toString()}`);
    esRef.current = es;

    es.onopen = () => {
      retryRef.current = 0; // 성공적으로 열리면 백오프 리셋
      setStatus('streaming');
    };

    const handleNamed = (type: AgentStreamEventType) => (ev: MessageEvent) => {
      if (ev.lastEventId) lastEventIdRef.current = ev.lastEventId;

      if (type === 'done') {
        // AgentStreamEvent(done) JSON 또는 raw "[DONE]" sentinel 둘 다 여기로 온다
        try {
          const parsed = JSON.parse(ev.data) as AgentStreamEvent;
          if (parsed && parsed.event_type) enqueue(parsed);
        } catch {
          /* raw "[DONE]" — 페이로드 없음, 종료만 처리 */
        }
        doneRef.current = true;
        closeEventSource();
        setStatus('done');
        return;
      }

      try {
        enqueue(JSON.parse(ev.data) as AgentStreamEvent);
      } catch {
        /* 파싱 불가한 페이로드는 무시 */
      }
    };

    NAMED_EVENTS.forEach((type) => {
      es.addEventListener(type, handleNamed(type) as EventListener);
    });

    es.onerror = () => {
      // 정상 종료(DONE) 후거나 사용자가 멈춘 경우가 아니면 수동 재연결
      if (doneRef.current || stoppedRef.current) return;
      closeEventSource(); // 네이티브 자동재연결(소비된 티켓 replay → 401) 방지
      scheduleReconnect();
    };
  }, [closeEventSource, enqueue, scheduleReconnect]);

  // 재귀 재연결이 항상 최신 connect 를 부르도록 렌더 후 ref 동기화
  useEffect(() => {
    connectRef.current = connect;
  });

  const start = useCallback(
    (nextChatSessionId?: string) => {
      stoppedRef.current = false;
      doneRef.current = false;
      retryRef.current = 0;
      // 턴마다 같은 대화 세션으로 재연결하도록 바인딩(넘기면 갱신)
      if (nextChatSessionId) chatSessionIdRef.current = nextChatSessionId;
      void connect();
    },
    [connect],
  );

  const stop = useCallback(() => {
    stoppedRef.current = true;
    teardown();
    setStatus((s) => (s === 'done' ? s : 'idle'));
  }, [teardown]);

  const reset = useCallback(() => {
    bufferRef.current = [];
    lastEventIdRef.current = null;
    setEvents([]);
    setError(null);
    if (!esRef.current) setStatus('idle');
  }, []);

  useEffect(() => {
    // setTimeout 0: 이펙트 동기 구간에서 setState 를 유발하지 않도록 다음 틱으로 미룸
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (autoStart) timer = setTimeout(() => start(), 0);
    return () => {
      if (timer) clearTimeout(timer);
      stoppedRef.current = true;
      teardown();
    };
    // 마운트/언마운트 1회만. start/teardown 은 안정적 참조.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { events, status, chatSessionId, error, start, stop, reset };
}
