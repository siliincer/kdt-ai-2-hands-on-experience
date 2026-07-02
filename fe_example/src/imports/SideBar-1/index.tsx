import svgPaths from "./svg-jp1mz49a91";

function Icon() {
  return (
    <div className="relative shrink-0 size-[18px]" data-name="Icon">
      <svg className="absolute block inset-0 size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 18 18">
        <g id="Icon">
          <path d="M9 6V3H6" id="Vector" stroke="var(--stroke-0, #0F1E3D)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
          <path d={svgPaths.p3e254b00} id="Vector_2" stroke="var(--stroke-0, #0F1E3D)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
          <path d="M1.5 10.5H3" id="Vector_3" stroke="var(--stroke-0, #0F1E3D)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
          <path d="M15 10.5H16.5" id="Vector_4" stroke="var(--stroke-0, #0F1E3D)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
          <path d="M11.25 9.75V11.25" id="Vector_5" stroke="var(--stroke-0, #0F1E3D)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
          <path d="M6.75 9.75V11.25" id="Vector_6" stroke="var(--stroke-0, #0F1E3D)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
        </g>
      </svg>
    </div>
  );
}

function Container1() {
  return (
    <div className="bg-[#2dd4bf] relative rounded-[33554400px] shrink-0 size-[32px]" data-name="Container">
      <div className="bg-clip-padding border-0 border-[transparent] border-solid content-stretch flex items-center justify-center relative size-full">
        <Icon />
      </div>
    </div>
  );
}

function Text() {
  return (
    <div className="relative shrink-0" data-name="Text">
      <div className="bg-clip-padding border-0 border-[transparent] border-solid content-stretch flex flex-col items-center relative size-full">
        <p className="[word-break:break-word] font-['DM_Sans:Bold',sans-serif] font-bold leading-[28px] relative shrink-0 text-[18px] text-center text-white whitespace-nowrap" style={{ fontVariationSettings: '"opsz" 14' }}>
          RealFinance
        </p>
      </div>
    </div>
  );
}

function Button() {
  return (
    <div className="relative shrink-0" data-name="Button">
      <div className="bg-clip-padding border-0 border-[transparent] border-solid content-stretch flex gap-[8px] items-center relative size-full">
        <Container1 />
        <Text />
      </div>
    </div>
  );
}

function Icon1() {
  return (
    <div className="relative shrink-0 size-[20px]" data-name="Icon">
      <svg className="absolute block inset-0 size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 20 20">
        <g id="Icon">
          <path d={svgPaths.pc176500} fill="var(--fill-0, white)" fillOpacity="0.7" id="Union" />
        </g>
      </svg>
    </div>
  );
}

function Button1() {
  return (
    <div className="relative shrink-0 size-[34px]" data-name="Button">
      <div className="bg-clip-padding border-0 border-[transparent] border-solid content-stretch flex flex-col items-center justify-center relative size-full">
        <Icon1 />
      </div>
    </div>
  );
}

function TopBar() {
  return (
    <div className="bg-[#0f1e3d] relative shrink-0 w-full" data-name="Top Bar">
      <div className="flex flex-row items-center size-full">
        <div className="bg-clip-padding border-0 border-[transparent] border-solid content-stretch flex items-center justify-between px-[20px] py-[16px] relative size-full">
          <Button />
          <Button1 />
        </div>
      </div>
    </div>
  );
}

function Container2() {
  return (
    <div className="bg-[#f8f9fb] flex-[721_0_0] min-h-px relative w-full" data-name="Container">
      <div className="overflow-clip rounded-[inherit] size-full">
        <div className="bg-clip-padding border-0 border-[transparent] border-solid content-stretch flex flex-col items-start p-[16px] relative size-full" />
      </div>
    </div>
  );
}

function Container() {
  return (
    <div className="bg-white h-full max-h-[862px] max-w-[480px] relative shadow-[0px_0px_40px_0px_rgba(0,0,0,0.12)] shrink-0 w-[480px]" data-name="Container">
      <div className="bg-clip-padding border-0 border-[transparent] border-solid content-stretch flex flex-col items-start max-h-[inherit] max-w-[inherit] overflow-clip relative rounded-[inherit] size-full">
        <TopBar />
        <Container2 />
      </div>
    </div>
  );
}

function App() {
  return (
    <div className="absolute bg-[#f0f2f5] content-stretch flex h-[860px] items-start justify-center left-0 top-0 w-[480px]" data-name="App">
      <Container />
    </div>
  );
}

function a() {
  return (
    <div className="absolute contents left-0 top-[57.6px]" data-name="사이드바 배경A">
      <div className="absolute bg-white h-[75px] left-0 top-[64px] w-[480px]" data-name="A" />
      <div className="absolute bg-white h-[721px] left-[75px] top-[139px] w-[405px]" data-name="너비조절" />
      <div className="-translate-x-1/2 -translate-y-1/2 [word-break:break-word] absolute flex flex-col font-['SF_Pro:Medium','Noto_Sans_KR:Medium',sans-serif] font-[510] justify-center leading-[0] left-[37.5px] size-[75px] text-[#6b7a99] text-[10px] text-center top-[123.5px]" style={{ fontVariationSettings: '"wdth" 100' }}>
        <p className="leading-[normal]">최근 이용 메뉴</p>
      </div>
      <div className="-translate-x-1/2 -translate-y-1/2 [word-break:break-word] absolute flex flex-col font-['SF_Pro:Bold',sans-serif] font-bold justify-center leading-[0] left-[37.5px] size-[75px] text-[#6b7a99] text-[40px] text-center top-[95.1px]" style={{ fontVariationSettings: '"wdth" 100' }}>
        <p className="leading-[normal]">A</p>
      </div>
    </div>
  );
}

function Component() {
  return (
    <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-name="메뉴그룹 1">
      <div className="bg-white col-1 h-[37.5px] ml-0 mt-0 relative row-1 w-[405px]" />
      <div className="col-1 h-[14.382px] ml-[355px] mt-[17px] relative row-1 w-[25px]" data-name="펼치기 기호">
        <svg className="absolute block inset-0 size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 25 14.3818">
          <path d={svgPaths.p2150e600} fill="var(--fill-0, #A9A9A9)" id="í¼ì¹ê¸° ê¸°í¸" />
        </svg>
      </div>
      <div className="[word-break:break-word] col-1 flex flex-col font-['SF_Pro:Thin','Noto_Sans_KR:Light',sans-serif] font-[110.72500610351562] justify-center ml-[13px] mt-[10px] relative row-1 text-[#6b7a99] text-[15px] whitespace-nowrap" style={{ fontVariationSettings: '"wdth" 100' }}>
        <p className="leading-[normal]">분석</p>
      </div>
    </div>
  );
}

function Component1() {
  return (
    <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-name="메뉴그룹 2">
      <div className="bg-white col-1 h-[37.5px] ml-0 mt-0 relative row-1 w-[405px]" />
      <div className="col-1 h-[14.382px] ml-[355px] mt-[17px] relative row-1 w-[25px]" data-name="펼치기 기호">
        <svg className="absolute block inset-0 size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 25 14.3818">
          <path d={svgPaths.p2150e600} fill="var(--fill-0, #A9A9A9)" id="í¼ì¹ê¸° ê¸°í¸" />
        </svg>
      </div>
      <div className="[word-break:break-word] col-1 flex flex-col font-['SF_Pro:Thin','Noto_Sans_KR:Light',sans-serif] font-[110.72500610351562] justify-center ml-[13px] mt-[10px] relative row-1 text-[#6b7a99] text-[15px] whitespace-nowrap" style={{ fontVariationSettings: '"wdth" 100' }}>
        <p className="leading-[normal]">메뉴 2텍스트</p>
      </div>
    </div>
  );
}

function Component3() {
  return (
    <div className="content-stretch flex flex-col items-start relative shrink-0 w-full z-[3]" data-name="텍스트상자1">
      <div className="bg-white h-[37.5px] relative shrink-0 w-full" data-name="상자1" />
    </div>
  );
}

function Component4() {
  return (
    <div className="content-stretch flex flex-col items-center relative shrink-0 w-full z-[2]" data-name="텍스트상자2">
      <div className="bg-white h-[37.5px] relative shrink-0 w-full" data-name="상자1" />
      <div className="-translate-y-1/2 [word-break:break-word] absolute flex flex-col font-['SF_Pro:Thin','Noto_Sans_KR:Light',sans-serif] font-[110.72500610351562] h-[18px] justify-center leading-[0] left-[13px] text-[15px] text-black top-[19px] w-[91px]" style={{ fontVariationSettings: '"wdth" 100' }}>
        <p className="leading-[normal]">거래 내역 조회</p>
      </div>
    </div>
  );
}

function Component5() {
  return (
    <div className="content-stretch flex flex-col items-center relative shrink-0 w-full z-[1]" data-name="텍스트상자2">
      <div className="bg-white h-[37.5px] relative shrink-0 w-full" data-name="상자1" />
      <div className="-translate-y-1/2 [word-break:break-word] absolute flex flex-col font-['SF_Pro:Thin','Noto_Sans_KR:Light',sans-serif] font-[110.72500610351562] h-[18px] justify-center leading-[0] left-[13px] text-[15px] text-black top-[19px] w-[91px]" style={{ fontVariationSettings: '"wdth" 100' }}>
        <p className="leading-[normal]">월간 소비 분석</p>
      </div>
    </div>
  );
}

function Component2() {
  return (
    <div className="bg-white content-stretch flex flex-col isolate items-end relative shrink-0 w-full" data-name="메뉴그룹 3">
      <div className="absolute flex h-[14.382px] items-center justify-center left-[355px] top-[17px] w-[25px] z-[4]">
        <div className="-scale-y-100 flex-none">
          <div className="h-[14.382px] relative w-[25px]" data-name="펼치기 기호">
            <svg className="absolute block inset-0 size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 25 14.3818">
              <path d={svgPaths.p2150e600} fill="var(--fill-0, #A9A9A9)" id="í¼ì¹ê¸° ê¸°í¸" />
            </svg>
          </div>
        </div>
      </div>
      <Component3 />
      <Component4 />
      <Component5 />
    </div>
  );
}

function Component6() {
  return (
    <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-name="메뉴그룹 4">
      <div className="bg-white col-1 h-[37.5px] ml-0 mt-0 relative row-1 w-[405px]" />
      <div className="col-1 h-[14.382px] ml-[355px] mt-[17px] relative row-1 w-[25px]" data-name="펼치기 기호">
        <svg className="absolute block inset-0 size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 25 14.3818">
          <path d={svgPaths.p2150e600} fill="var(--fill-0, #A9A9A9)" id="í¼ì¹ê¸° ê¸°í¸" />
        </svg>
      </div>
      <div className="[word-break:break-word] col-1 flex flex-col font-['SF_Pro:Thin','Noto_Sans_KR:Light',sans-serif] font-[110.72500610351562] justify-center ml-[13px] mt-[10px] relative row-1 text-[#6b7a99] text-[15px] whitespace-nowrap" style={{ fontVariationSettings: '"wdth" 100' }}>
        <p className="leading-[normal]">메뉴 4텍스트</p>
      </div>
    </div>
  );
}

function Frame1() {
  return (
    <div className="absolute content-stretch flex flex-col items-start left-0 top-0 w-[405px]">
      <Component />
      <Component1 />
      <Component2 />
      <div className="-translate-y-1/2 [word-break:break-word] absolute flex flex-col font-['SF_Pro:Thin','Noto_Sans_KR:Light',sans-serif] font-[110.72500610351562] h-[18px] justify-center leading-[0] left-[13px] text-[15px] text-black top-[94px] w-[91px]" style={{ fontVariationSettings: '"wdth" 100' }}>
        <p className="leading-[normal]">조회 서비스</p>
      </div>
      <Component6 />
    </div>
  );
}

function Frame() {
  return (
    <div className="absolute h-[796px] left-[75px] overflow-clip top-[64px] w-[405px]">
      <Frame1 />
    </div>
  );
}

export default function SideBar() {
  return (
    <div className="bg-[#f4f6fa] relative size-full" data-name="SideBar">
      <App />
      <div className="absolute bg-[#f4f6fa] h-[796px] left-0 top-[64px] w-[480px]" data-name="Left bar" />
      <a />
      <Frame />
    </div>
  );
}