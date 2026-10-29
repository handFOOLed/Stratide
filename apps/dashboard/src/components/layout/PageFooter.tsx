import { formatClock } from '../../lib/format';

export function PageFooter() {
  const build = __BUILD_SHA__ === 'local' ? 'local build' : 'build ' + __BUILD_SHA__;
  return (
    <footer className="app-footer">
      <p>
        <span>Stratide · 本地 Paper 工作空间</span>
        <span className="footer-sep" aria-hidden="true">·</span>
        <span>本地只读数据 · 不构成投资建议</span>
      </p>
      <p>
        <span>UI {__UI_VERSION__}</span>
        <span className="footer-sep" aria-hidden="true">·</span>
        <span className="footer-version">{build}</span>
        <span className="footer-sep" aria-hidden="true">·</span>
        <span>127.0.0.1</span>
      </p>
    </footer>
  );
}

export function FreshnessNote({ loadedAt }: { loadedAt: number | null }) {
  if (!loadedAt) return null;
  return <span>读取于 {formatClock(loadedAt)}</span>;
}