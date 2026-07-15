/**
 * 대기 UX: assistant 가 아직 아무 내용도 못 낸 idle 구간에 "생각 중" 표시.
 * MessageText 가 빈 running 텍스트 플레이스홀더일 때 이걸 렌더한다
 * (confirm 카드처럼 tool-call 로 끝나는 메시지엔 나오지 않음).
 */
export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <span className="inline-flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground" />
      </span>
      🤖 Agent가 생각 중입니다…
    </div>
  );
}
