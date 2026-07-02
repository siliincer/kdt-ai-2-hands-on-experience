import { useNavigate } from "react-router";
import { X } from "lucide-react";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";

const ERROR_SCENARIOS = [
  { label: "잔액 부족", text: "잔액이 부족합니다." },
  { label: "잘못된 계좌번호", text: "잘못된 계좌번호입니다." },
  { label: "송금 한도 초과", text: "1회 송금 한도를 초과했습니다." },
  { label: "네트워크 오류", text: "네트워크 연결을 확인해주세요." },
];

// ── Route ─────────────────────────────────────────────────────────────────────
export default function ErrorMessageRoute() {
  const navigate = useNavigate();

  const triggerError = (text: string) => {
    const saved = sessionStorage.getItem('rf_chat_msgs');
    let msgs = [];
    try { msgs = saved ? JSON.parse(saved) : []; } catch { msgs = []; }
    msgs.push({ id: Date.now(), from: "ai-error", text });
    sessionStorage.setItem('rf_chat_msgs', JSON.stringify(msgs));
    navigate("/");
  };

  return (
    <div className="flex h-screen overflow-hidden justify-center" style={{ background: "#F0F2F5" }}>
      <div className="w-full flex flex-col bg-white" style={{ maxWidth: 480, boxShadow: "0 0 40px rgba(0,0,0,0.08)" }}>
        <div className="flex items-center gap-3 px-5 py-4 flex-shrink-0" style={{ background: NAVY }}>
          <button
            onClick={() => navigate(-1)}
            className="text-white/70 hover:text-white transition-colors"
            aria-label="뒤로가기"
          >
            ←
          </button>
          <span className="font-bold text-white text-base" style={{ fontFamily: "'DM Sans',sans-serif" }}>
            ⚠️ 에러 메시지
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <div className="flex items-center gap-2 mb-3">
            <X size={15} color="#FF4D4F" />
            <p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>실패 시나리오 선택</p>
          </div>
          <p className="text-xs mb-4" style={{ color: "#6B7A99", fontFamily: F }}>
            선택하면 채팅에 해당 에러 메시지가 추가되고 채팅 화면으로 이동합니다.
          </p>
          <div className="space-y-2">
            {ERROR_SCENARIOS.map(s => (
              <button
                key={s.label}
                onClick={() => triggerError(s.text)}
                className="w-full text-left px-4 py-3 rounded-xl text-sm font-medium hover:opacity-80 transition-opacity"
                style={{ background: "#FFF1F0", color: "#7F1D1D", fontFamily: F, border: "1px solid #FFCCC7" }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        {/* AC4: return-to-chat nav + 채팅 초기화 */}
        <div className="flex gap-2 px-4 py-3 border-t flex-shrink-0" style={{ borderColor: "rgba(15,30,61,0.08)" }}>
          <button
            onClick={() => navigate("/")}
            className="flex-1 py-2 rounded-xl text-xs font-medium border"
            style={{ borderColor: MINT, color: NAVY, fontFamily: F }}
          >
            채팅으로 돌아가기
          </button>
          <button
            onClick={() => { sessionStorage.removeItem('rf_chat_msgs'); navigate("/"); }}
            className="flex-1 py-2 rounded-xl text-xs font-medium"
            style={{ background: "#F4F6FA", color: "#6B7A99", fontFamily: F }}
          >
            채팅 초기화
          </button>
        </div>
      </div>
    </div>
  );
}
