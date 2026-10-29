import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '../icons';
import { navigate } from '../lib/route';
import { useOnClickOutside } from '../lib/hooks';
import { useTheme } from '../state/ThemeProvider';

const ITEM_SELECTOR = '[data-account-menu-item]';

/**
 * Sidebar account entry. There is no user account API in this local build, so the
 * avatar is a neutral glyph and the identity label is the local Owner workspace,
 * never private profile data.
 */
export function UserMenu({ onNavigate }: { onNavigate?: () => void }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme, toggleTheme } = useTheme();

  const close = useCallback(
    (restoreFocus = true) => {
      setOpen(false);
      if (restoreFocus) triggerRef.current?.focus({ preventScroll: true });
    },
    [],
  );

  useOnClickOutside([wrapRef], () => close(false), open);

  useEffect(() => {
    if (!open) return;
    const node = menuRef.current;
    if (node) {
      const first = node.querySelector<HTMLElement>(ITEM_SELECTOR);
      window.requestAnimationFrame(() => first?.focus({ preventScroll: true }));
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp' && event.key !== 'Home' && event.key !== 'End') {
        return;
      }
      const menu = menuRef.current;
      if (!menu) return;
      const items = Array.from(menu.querySelectorAll<HTMLElement>(ITEM_SELECTOR)).filter(
        (item) => !item.hasAttribute('disabled'),
      );
      if (items.length === 0) return;
      event.preventDefault();
      const current = items.indexOf(document.activeElement as HTMLElement);
      let next = current;
      if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = items.length - 1;
      else if (event.key === 'ArrowDown') next = current < 0 ? 0 : (current + 1) % items.length;
      else next = current <= 0 ? items.length - 1 : current - 1;
      items[next]?.focus({ preventScroll: true });
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [close, open]);

  const go = (section: 'appearance' | 'about') => {
    setOpen(false);
    onNavigate?.();
    navigate({ page: 'settings', section });
  };

  return (
    <div className="sidebar-account">
      <div className="account-menu-wrap" ref={wrapRef}>
        <button
          ref={triggerRef}
          type="button"
          className="account-button"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls="account-menu"
          onClick={() => setOpen((current) => !current)}
        >
          <span className="avatar" aria-hidden="true"><Icon name="user" size={15} /></span>
          <span className="account-copy">
            <span className="account-name">本机 Owner</span>
            <span className="account-sub">Paper 工作空间</span>
          </span>
          <span className="account-chevron" aria-hidden="true"><Icon name="chevron-down" size={14} /></span>
        </button>

        {open ? (
          <div className="account-menu" id="account-menu" role="menu" aria-label="个人资料与工作空间" ref={menuRef}>
            <div className="account-menu__head">
              <span className="avatar avatar--lg" aria-hidden="true"><Icon name="user" size={17} /></span>
              <div>
                <div className="account-menu__title">本机 Owner</div>
                <div className="account-menu__sub">localhost · 仅本机</div>
              </div>
            </div>
            <div className="account-menu__list">
              <button
                type="button"
                role="menuitem"
                data-account-menu-item=""
                className="account-menu__item"
                onClick={() => go('appearance')}
              >
                <Icon name="settings" size={16} />
                设置
              </button>
              <button
                type="button"
                role="menuitem"
                data-account-menu-item=""
                className="account-menu__item"
                onClick={() => go('about')}
              >
                <Icon name="info" size={16} />
                关于 Stratide
              </button>
              <button
                type="button"
                role="menuitem"
                data-account-menu-item=""
                className="account-menu__item"
                onClick={toggleTheme}
              >
                <Icon name={resolvedTheme === 'dark' ? 'sun' : 'moon'} size={16} />
                切换到{resolvedTheme === 'dark' ? '浅色' : '深色'}外观
              </button>
            </div>
            <div className="account-menu__foot">
              <span>本机只读工作空间</span>
              <span className="mono">v{__UI_VERSION__}</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
