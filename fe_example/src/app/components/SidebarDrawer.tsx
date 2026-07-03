import { useState } from "react";
import { Clock, Star } from "lucide-react";
import svgPaths from "../../imports/SideBar-1/svg-jp1mz49a91";

// ── SVG Icons ─────────────────────────────────────────────────────────────────
function RobotIcon() {
  return (
    <svg fill="none" viewBox="0 0 18 18" className="size-full">
      <path d="M9 6V3H6" stroke="#0F1E3D" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      <path d={svgPaths.p3e254b00} stroke="#0F1E3D" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      <path d="M1.5 10.5H3" stroke="#0F1E3D" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      <path d="M15 10.5H16.5" stroke="#0F1E3D" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      <path d="M11.25 9.75V11.25" stroke="#0F1E3D" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
      <path d="M6.75 9.75V11.25" stroke="#0F1E3D" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg fill="none" viewBox="0 0 20 20" className="size-full">
      <path d={svgPaths.pc176500} fill="rgba(255,255,255,0.7)" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      fill="none"
      viewBox="0 0 25 14.3818"
      style={{
        width: 16,
        height: 9,
        transition: "transform 0.2s ease",
        transform: open ? "rotate(180deg)" : "rotate(0deg)",
        flexShrink: 0,
      }}
    >
      <path d={svgPaths.p2150e600} fill="#A9A9A9" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg fill="none" viewBox="0 0 20 20" width={18} height={18}>
      <circle cx="10" cy="10" r="2.8" stroke="#6B7A99" strokeWidth="1.4" />
      <path
        d="M10 2v1.5M10 16.5V18M2 10h1.5M16.5 10H18M4.22 4.22l1.06 1.06M14.72 14.72l1.06 1.06M4.22 15.78l1.06-1.06M14.72 5.28l1.06-1.06"
        stroke="#6B7A99" strokeLinecap="round" strokeWidth="1.4"
      />
    </svg>
  );
}

// ── Menu data ─────────────────────────────────────────────────────────────────
const MENU_GROUPS = [
  {
    id: "chat",
    label: "AI 채팅",
    items: ["채팅 홈"],
    defaultOpen: false,
  },
  {
    id: "analysis",
    label: "분석",
    items: ["월간 소비 분석", "예산 관리"],
    defaultOpen: false,
  },
  {
    id: "inquiry",
    label: "조회",
    items: ["잔액 조회", "계좌 정보 조회", "거래 내역 조회"],
    defaultOpen: true,
  },
  {
    id: "card",
    label: "카드",
    items: ["카드 정보 조회", "카드 청구서 확인"],
    defaultOpen: false,
  },
  {
    id: "transfer",
    label: "이체/송금",
    items: ["본인 계좌 이체", "타인 송금", "자동 이체 설정"],
    defaultOpen: false,
  },
];

// ── Props ─────────────────────────────────────────────────────────────────────
interface SidebarDrawerProps {
  showCloseButton?: boolean;
  onClose?: () => void;
  onLogout?: () => void;
  onMenuSelect?: (item: string) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function SidebarDrawer({
  showCloseButton = true,
  onClose,
  onLogout,
  onMenuSelect,
}: SidebarDrawerProps) {
  const [openGroups, setOpenGroups] = useState<Set<string>>(
    new Set(MENU_GROUPS.filter(g => g.defaultOpen).map(g => g.id))
  );
  // ✅ Fix: no default selection
  const [activeItem, setActiveItem] = useState<string | null>(null);

  const toggleGroup = (id: string) =>
    setOpenGroups(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const handleItemClick = (item: string) => {
    setActiveItem(item);
    onMenuSelect?.(item);
  };

  return (
    <div
      className="flex flex-col bg-white h-full"
      style={{ fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      {/* ── Top Bar ── */}
      <div
        className="flex items-center justify-between px-5 py-4 flex-shrink-0"
        style={{ background: "#0F1E3D" }}
      >
        <div className="flex items-center gap-2">
          <div
            className="flex items-center justify-center rounded-full flex-shrink-0"
            style={{ width: 32, height: 32, background: "#2DD4BF" }}
          >
            <div style={{ width: 18, height: 18 }}>
              <RobotIcon />
            </div>
          </div>
          <span
            className="font-bold text-white text-lg"
            style={{ fontFamily: "'DM Sans', sans-serif" }}
          >
            RealFinance
          </span>
        </div>

        {showCloseButton && (
          <button
            onClick={onClose}
            className="flex items-center justify-center hover:opacity-70 transition-opacity"
            style={{ width: 34, height: 34 }}
            aria-label="닫기"
          >
            <div style={{ width: 20, height: 20 }}>
              <CloseIcon />
            </div>
          </button>
        )}
      </div>

      {/* ── Body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left panel — 148px, icon + label horizontal layout */}
        <div
          className="flex flex-col items-stretch py-4 flex-shrink-0 border-r"
          style={{
            width: 148,
            background: "#F4F6FA",
            borderColor: "rgba(15,30,61,0.08)",
          }}
        >
          {/* Avatar */}
          <div className="flex items-center gap-2.5 px-4 mb-5">
            <div
              className="flex items-center justify-center rounded-full flex-shrink-0"
              style={{ width: 40, height: 40, background: "#0F1E3D" }}
            >
              <span
                className="text-white font-bold text-base"
                style={{ fontFamily: "'DM Sans', sans-serif" }}
              >
                A
              </span>
            </div>
            <span
              className="text-xs font-medium truncate"
              style={{ color: "#0F1E3D", fontFamily: "'Noto Sans KR', sans-serif" }}
            >
              사용자
            </span>
          </div>

          {/* 최근 이용 메뉴 */}
          <button
            className="flex items-center gap-2.5 px-4 py-2.5 hover:opacity-70 transition-opacity text-left"
          >
            <div
              className="flex items-center justify-center rounded-lg flex-shrink-0"
              style={{ width: 32, height: 32, background: "rgba(45,212,191,0.12)" }}
            >
              <Clock size={16} color="#2DD4BF" />
            </div>
            <span
              className="text-xs leading-tight"
              style={{ color: "#6B7A99", fontFamily: "'Noto Sans KR', sans-serif" }}
            >
              최근 이용<br />메뉴
            </span>
          </button>

          {/* 즐겨찾는 메뉴 */}
          <button
            className="flex items-center gap-2.5 px-4 py-2.5 hover:opacity-70 transition-opacity text-left"
          >
            <div
              className="flex items-center justify-center rounded-lg flex-shrink-0"
              style={{ width: 32, height: 32, background: "rgba(45,212,191,0.12)" }}
            >
              <Star size={16} color="#2DD4BF" />
            </div>
            <span
              className="text-xs leading-tight"
              style={{ color: "#6B7A99", fontFamily: "'Noto Sans KR', sans-serif" }}
            >
              즐겨찾는<br />메뉴
            </span>
          </button>
        </div>

        {/* Right menu list */}
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex-1 overflow-y-auto">
            {MENU_GROUPS.map(group => {
              const isOpen = openGroups.has(group.id);
              return (
                <div key={group.id} className="border-b" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
                  {/* Group header */}
                  <button
                    className="w-full flex items-center justify-between px-4 hover:bg-gray-50 transition-colors"
                    style={{ height: 50 }}
                    onClick={() => toggleGroup(group.id)}
                  >
                    <span
                      style={{
                        fontSize: 15,
                        fontFamily: "'Noto Sans KR', sans-serif",
                        color: isOpen ? "#0F1E3D" : "#6B7A99",
                        fontWeight: isOpen ? 600 : 400,
                        transition: "color 0.15s",
                      }}
                    >
                      {group.label}
                    </span>
                    <ChevronIcon open={isOpen} />
                  </button>

                  {/* Sub-items (animated accordion) */}
                  <div
                    style={{
                      overflow: "hidden",
                      maxHeight: isOpen ? `${group.items.length * 44}px` : "0px",
                      transition: "max-height 0.22s ease",
                    }}
                  >
                    {group.items.map(item => {
                      const isActive = activeItem === item;
                      return (
                        <button
                          key={item}
                          onClick={() => handleItemClick(item)}
                          className="w-full flex items-center px-4 hover:opacity-80 transition-opacity"
                          style={{
                            height: 44,
                            borderLeft: isActive ? "3px solid #2DD4BF" : "3px solid transparent",
                            background: isActive ? "rgba(45,212,191,0.06)" : "#fff",
                          }}
                        >
                          <span
                            style={{
                              fontSize: 14,
                              fontFamily: "'Noto Sans KR', sans-serif",
                              color: isActive ? "#2DD4BF" : "#333",
                              fontWeight: isActive ? 600 : 400,
                              paddingLeft: 4,
                            }}
                          >
                            {item}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Bottom: settings + logout */}
          <div
            className="flex items-center gap-3 px-4 py-4 border-t flex-shrink-0"
            style={{ borderColor: "rgba(15,30,61,0.08)", background: "#fff" }}
          >
            <SettingsIcon />
            <button
              onClick={onLogout}
              className="text-sm hover:opacity-70 transition-opacity"
              style={{ color: "#6B7A99", fontFamily: "'Noto Sans KR', sans-serif" }}
            >
              로그아웃
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
