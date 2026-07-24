// crypto.randomUUID는 "보안 컨텍스트"(HTTPS 또는 localhost)에서만 존재한다.
// 이 앱은 HTTP 데모 환경(Elastic IP 평문 접속)도 지원해야 하므로, 항상 존재하는
// crypto.getRandomValues로 UUID v4를 직접 만들어 그 제약을 피한다.
function randomUuidV4(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-');
}

export function newId(): string {
  return randomUuidV4();
}
