// 手绘 24px 线性图标（近似原型；平台徽标沿用现有 DNA）
const ICON_PATHS = {
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  plus: <path d="M12 5v14M5 12h14" />,
  search: <g><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.4-4.4" /></g>,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  dots: <g fill="currentColor" stroke="none"><circle cx="12" cy="5.4" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="18.6" r="1.5" /></g>,
  download: <g><path d="M12 4v10" /><path d="M7.5 10.5 12 15l4.5-4.5" /><path d="M5 19.5h14" /></g>,
  send: <path d="M4.5 11.2 20 4l-3.3 15.6-5-5.2-7.2-3.2ZM12.6 14.6 20 4" />,
  monitor: <g><rect x="3.5" y="4.5" width="17" height="11.5" rx="1.8" /><path d="M9 20h6M12 16v4" /></g>,
  phone: <g><rect x="7" y="3" width="10" height="18" rx="2.4" /><path d="M10.7 17.8h2.6" /></g>,
  sun: <g><circle cx="12" cy="12" r="3.6" /><path d="M12 2.8v2M12 19.2v2M2.8 12h2M19.2 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M5.2 18.8l1.4-1.4M17.4 6.6l1.4-1.4" /></g>,
  moon: <path d="M20 13.6A7.6 7.6 0 0 1 10.4 4 7.6 7.6 0 1 0 20 13.6Z" />,
  sparkle: <g><path d="M12 3.5l1.8 4.9 4.9 1.8-4.9 1.8L12 16.9l-1.8-4.9-4.9-1.8 4.9-1.8L12 3.5Z" /><path d="M18.4 15.6l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7.7-1.9Z" /></g>,
  file: <path d="M6.5 3h7L19 8.5V19a2 2 0 0 1-2 2H6.5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2ZM13 3v6h6" />,
  lang: <g><path d="M4 5.5h8M8 3.5v2M10.5 5.5c-.6 3.6-3 6.5-6.5 8.2" /><path d="M5.5 9.5c1.3 2.8 3.7 4.8 6.5 5.6" /><path d="M12.8 20.5 17 11l4.2 9.5M14.3 17.5h5.4" /></g>,
  list: <g><path d="M9 6h11M9 12h11M9 18h11" /><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" strokeWidth="2.4" /></g>,
  chevron: <path d="M6.5 9.5 12 15l5.5-5.5" />,
  external: <g><path d="M13.5 5H19v5.5" /><path d="M19 5l-8.2 8.2" /><path d="M17 13.5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h4.5" /></g>,
  check: <path d="M5 12.5 10 17.5 19 7" />,
  alert: <g><path d="M12 8.5v5" /><path d="M12 16.6v.01" /><path d="M10.3 3.9 2.9 16.9a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></g>,
  book: <g><path d="M4.5 5A1.5 1.5 0 0 1 6 3.5h12.5v14H6A1.5 1.5 0 0 0 4.5 19V5Z" /><path d="M6 17.5h12.5V21H6a1.75 1.75 0 0 1 0-3.5Z" /></g>,
  library: <g><rect x="3.5" y="3" width="17" height="18" rx="2" /><path d="M8 7.5h8M8 11.5h8M8 15.5h4.5" /></g>,
  zap: <path d="M13 2.5 4.5 13.5H11L10 21.5l8.5-11H12l1-7.5Z" />,
  link: <g><path d="M10.5 13.5a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.3 1.3" /><path d="M13.5 10.5a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.3-1.3" /></g>,
  compass: <g><circle cx="12" cy="12" r="8.2" /><path d="m15.2 8.8-2 4.4-4.4 2 2-4.4 4.2-2Z" /><path d="M12 3.6v1.6M12 18.8v1.6M4.4 12H6M18 12h1.6" opacity=".55" /></g>,
};

function Icon({ name, size = 16, strokeWidth = 1.7, className = "" }) {
  return (
    <svg
      aria-hidden="true"
      className={"icon" + (className ? " " + className : "")}
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={strokeWidth}
      viewBox="0 0 24 24"
      width={size}
    >
      {ICON_PATHS[name] || null}
    </svg>
  );
}

const PLATFORM_GLYPHS = { arxiv: "a", github: "◉", huggingface: "⌁", web: "◌", x: "𝕏", youtube: "▶" };

function PlatformChip({ platform, size = 22 }) {
  return (
    <span
      aria-hidden="true"
      className={"chip chip-" + platform}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.46) }}
    >
      {PLATFORM_GLYPHS[platform] || "◌"}
    </span>
  );
}

function Logo({ size = 30 }) {
  return <span aria-hidden="true" className="st-logo" style={{ width: size, height: size, fontSize: Math.round(size * 0.44) }}>X²</span>;
}

Object.assign(window, { Icon, PlatformChip, PLATFORM_GLYPHS, ICON_PATHS });
