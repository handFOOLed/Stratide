import type { ReactNode } from 'react';

export type IconName =
  | 'overview'
  | 'history'
  | 'agent'
  | 'notifications'
  | 'settings'
  | 'sun'
  | 'moon'
  | 'monitor'
  | 'chevron-down'
  | 'chevron-right'
  | 'chevron-left'
  | 'chevrons-left'
  | 'chevrons-right'
  | 'close'
  | 'check'
  | 'alert-triangle'
  | 'alert-octagon'
  | 'info'
  | 'shield'
  | 'database'
  | 'wallet'
  | 'chart'
  | 'refresh'
  | 'plus'
  | 'pause'
  | 'play'
  | 'lock'
  | 'unlock'
  | 'search'
  | 'menu'
  | 'retry'
  | 'ban'
  | 'clock'
  | 'file'
  | 'layers'
  | 'activity'
  | 'key'
  | 'server'
  | 'user'
  | 'arrow-up-right'
  | 'arrow-right'
  | 'calendar'
  | 'list';

const paths: Record<IconName, ReactNode> = {
  overview: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
  history: (
    <>
      <path d="M3.5 12a8.5 8.5 0 1 0 2.7-6.2" />
      <path d="M3.5 4.5V9h4.5" />
      <path d="M12 7.5V12l3 1.8" />
    </>
  ),
  agent: (
    <>
      <path d="M12 3.5 13.6 9l5.4 1.6-5.4 1.6L12 17.5l-1.6-5.3L5 10.6 10.4 9 12 3.5Z" />
      <path d="M18.5 15.5 19.2 18l2.3.8-2.3.8-.7 2.4-.7-2.4-2.3-.8 2.3-.8.7-2.5Z" />
    </>
  ),
  notifications: (
    <>
      <path d="M18 9.2c0-3.2-2.4-5.7-6-5.7s-6 2.5-6 5.7c0 5.3-2 6.2-2 7.8h16c0-1.6-2-2.5-2-7.8Z" />
      <path d="M9.8 20h4.4" />
    </>
  ),
  settings: (
    <>
      <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
      <circle cx="15" cy="7" r="2.2" />
      <circle cx="9" cy="17" r="2.2" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="3.7" />
      <path d="M12 2.8v2M12 19.2v2M2.8 12h2M19.2 12h2M5.4 5.4l1.4 1.4M17.2 17.2l1.4 1.4M18.6 5.4l-1.4 1.4M6.8 17.2l-1.4 1.4" />
    </>
  ),
  moon: (
    <path d="M20 14.2A8.4 8.4 0 0 1 9.8 4 8.5 8.5 0 1 0 20 14.2Z" />
  ),
  monitor: (
    <>
      <rect x="3" y="4.5" width="18" height="12" rx="2" />
      <path d="M9 20h6M12 16.5V20" />
    </>
  ),
  'chevron-down': <path d="m6 9 6 6 6-6" />,
  'chevron-right': <path d="m9 6 6 6-6 6" />,
  'chevron-left': <path d="m15 6-6 6 6 6" />,
  'chevrons-left': <path d="m11 7-5 5 5 5M18 7l-5 5 5 5" />,
  'chevrons-right': <path d="m13 7 5 5-5 5M6 7l5 5-5 5" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  check: <path d="m5 12.5 4.2 4.2L19 7" />,
  'alert-triangle': (
    <>
      <path d="M12 3.5 21 19.5H3L12 3.5Z" />
      <path d="M12 9v4.5M12 16.6v.1" />
    </>
  ),
  'alert-octagon': (
    <>
      <path d="M8.2 3.5h7.6L20.5 8.2v7.6l-4.7 4.7H8.2l-4.7-4.7V8.2L8.2 3.5Z" />
      <path d="M12 8v4.5M12 15.8v.1" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5M12 8v.1" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.2 19 6v5.4c0 4.2-2.9 7.3-7 9.4-4.1-2.1-7-5.2-7-9.4V6l7-2.8Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5.5" rx="7.5" ry="3" />
      <path d="M4.5 5.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
      <path d="M4.5 11.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
    </>
  ),
  wallet: (
    <>
      <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H18a2 2 0 0 1 2 2v11H6.5A2.5 2.5 0 0 1 4 15.5v-8Z" />
      <path d="M4 8h13M16 12h4v3h-4a1.5 1.5 0 0 1 0-3Z" />
    </>
  ),
  chart: (
    <>
      <path d="M4 4v16h16" />
      <path d="m7 15 4-4 3 2.5 5-6" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 11a8 8 0 0 0-14.5-4.4L4 9" />
      <path d="M4 4.5V9h4.5" />
      <path d="M4 13a8 8 0 0 0 14.5 4.4L20 15" />
      <path d="M20 19.5V15h-4.5" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  pause: (
    <>
      <rect x="6.5" y="5" width="3.6" height="14" rx="1" />
      <rect x="13.9" y="5" width="3.6" height="14" rx="1" />
    </>
  ),
  play: <path d="M8 5.2v13.6L19 12 8 5.2Z" />,
  lock: (
    <>
      <rect x="4.5" y="10" width="15" height="10.5" rx="2" />
      <path d="M8 10V7.5a4 4 0 0 1 8 0V10M12 14v2.5" />
    </>
  ),
  unlock: (
    <>
      <rect x="4.5" y="10" width="15" height="10.5" rx="2" />
      <path d="M8 10V7.5a4 4 0 0 1 7.4-2.1M12 14v2.5" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.5 4.5" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  retry: (
    <>
      <path d="M4 10a8 8 0 0 1 14-3l2 2" />
      <path d="M20 4v5h-5" />
      <path d="M20 14a8 8 0 0 1-14 3l-2-2" />
      <path d="M4 20v-5h5" />
    </>
  ),
  ban: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m6 6 12 12" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 1.8" />
    </>
  ),
  file: (
    <>
      <path d="M6 3.5h7l5 5v12H6v-17Z" />
      <path d="M13 3.5V9h5M9 13h6M9 16.5h4" />
    </>
  ),
  layers: (
    <>
      <path d="m12 3.5 8.5 4.5L12 12.5 3.5 8 12 3.5Z" />
      <path d="m3.5 12 8.5 4.5 8.5-4.5M3.5 16l8.5 4.5 8.5-4.5" />
    </>
  ),
  activity: <path d="M3 12h4l2.2-6 4.2 12 2.4-6H21" />,
  key: (
    <>
      <circle cx="8" cy="12" r="4" />
      <path d="M12 12h8.5M17 12v3M20 12v2.5" />
    </>
  ),
  server: (
    <>
      <rect x="3.5" y="4" width="17" height="6.5" rx="1.7" />
      <rect x="3.5" y="13.5" width="17" height="6.5" rx="1.7" />
      <path d="M7 7.2h.1M7 16.7h.1" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8.2" r="3.7" />
      <path d="M4.8 20c0-3.4 3.2-5.6 7.2-5.6s7.2 2.2 7.2 5.6" />
    </>
  ),
  'arrow-up-right': <path d="M7 17 17 7M8 7h9v9" />,
  'arrow-right': <path d="M4 12h16M14 6l6 6-6 6" />,
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M7.5 3.5V7M16.5 3.5V7M3.5 9.5h17" />
    </>
  ),
  list: <path d="M8 6h12M8 12h12M8 18h12M4 6h.1M4 12h.1M4 18h.1" />,
};

export function Icon({
  name,
  size = 18,
  strokeWidth = 1.6,
  className,
}: {
  name: IconName;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {paths[name]}
    </svg>
  );
}

export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <span className="brand-mark" style={{ width: size, height: size, borderRadius: size * 0.3 }}>
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" focusable="false">
        <path
          d="M4 15h4v-4h4V7h4M4 5v10h12"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}
