import { useNavigate } from "react-router";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";

export default function ErrorRoute() {
  const navigate = useNavigate();
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
            페이지를 찾을 수 없습니다
          </span>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6">
          <span style={{ fontSize: 52 }}>🔍</span>
          <p className="text-lg font-bold" style={{ color: NAVY, fontFamily: F }}>404</p>
          <p className="text-sm" style={{ color: "#6B7A99", fontFamily: F }}>요청하신 페이지를 찾을 수 없어요</p>
          <button
            onClick={() => navigate("/")}
            className="px-6 py-3 rounded-xl text-sm font-semibold"
            style={{ background: MINT, color: NAVY, fontFamily: F }}
          >
            채팅으로 돌아가기
          </button>
        </div>
      </div>
    </div>
  );
}
