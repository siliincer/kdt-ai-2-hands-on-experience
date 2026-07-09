import svgPaths from '@/widgets/imports/SideBar-1/svg-jp1mz49a91';

import { NAVY } from '@/shared/constants/color';

export function RobotIcon() {
  return (
    <svg
      fill="none"
      viewBox="0 0 18 18"
      style={{ width: '100%', height: '100%' }}
    >
      <path
        d="M9 6V3H6"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d={svgPaths.p3e254b00}
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M1.5 10.5H3"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M15 10.5H16.5"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M11.25 9.75V11.25"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M6.75 9.75V11.25"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}
