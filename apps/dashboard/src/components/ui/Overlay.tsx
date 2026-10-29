import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useFocusTrap, usePresence } from '../../lib/hooks';

let inertCount = 0;

function acquireInert() {
  inertCount += 1;
  if (inertCount === 1) {
    document.querySelector('.app-shell')?.setAttribute('inert', '');
  }
}

function releaseInert() {
  inertCount = Math.max(0, inertCount - 1);
  if (inertCount === 0) {
    document.querySelector('.app-shell')?.removeAttribute('inert');
  }
}

export function Overlay({
  open,
  onClose,
  placement = 'right',
  duration = 300,
  labelId,
  children,
  className = '',
  closeOnBackdrop = true,
}: {
  open: boolean;
  onClose: () => void;
  placement?: 'right' | 'center' | 'left';
  duration?: number;
  labelId: string;
  children: ReactNode;
  className?: string;
  closeOnBackdrop?: boolean;
}) {
  const { mounted, state } = usePresence(open, duration);
  const panelRef = useRef<HTMLDivElement>(null);

  useFocusTrap(panelRef, mounted, onClose);

  useEffect(() => {
    if (!mounted) return;
    acquireInert();
    return () => releaseInert();
  }, [mounted]);

  if (!mounted) return null;

  return createPortal(
    <div
      className={['overlay', 'overlay--' + placement, className].filter(Boolean).join(' ')}
      data-state={state}
      onPointerDown={(event) => {
        if (
          closeOnBackdrop &&
          (event.target === event.currentTarget || event.target === panelRef.current)
        ) {
          onClose();
        }
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        tabIndex={-1}
        className="overlay__panel"
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

export function Drawer({
  open,
  onClose,
  eyebrow,
  title,
  meta,
  children,
  footer,
  side = 'right',
}: {
  open: boolean;
  onClose: () => void;
  eyebrow?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  side?: 'right' | 'left';
}) {
  const titleId = 'drawer-title';
  return (
    <Overlay
      open={open}
      onClose={onClose}
      placement={side}
      duration={300}
      labelId={titleId}
      className="overlay--drawer"
    >
      <div className={'drawer' + (side === 'left' ? ' drawer--left' : '')}>
        <header className="drawer__head">
          <div className="drawer__heading">
            {eyebrow ? <div className="drawer__eyebrow">{eyebrow}</div> : null}
            <h2 className="drawer__title" id={titleId}>{title}</h2>
            {meta ? <div className="drawer__title-meta">{meta}</div> : null}
          </div>
          <button type="button" className="icon-btn" aria-label="关闭详情" title="关闭详情" onClick={onClose}>
            <span aria-hidden="true" className="overlay-close-glyph">×</span>
          </button>
        </header>
        <div className="drawer__body">{children}</div>
        {footer ? <footer className="drawer__foot">{footer}</footer> : null}
      </div>
    </Overlay>
  );
}

export function Modal({
  open,
  onClose,
  eyebrow,
  title,
  description,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const titleId = 'modal-title';
  const descriptionId = 'modal-description';
  return (
    <Overlay
      open={open}
      onClose={onClose}
      placement="center"
      duration={220}
      labelId={titleId}
      className="overlay--modal"
    >
      <div className={'modal' + (wide ? ' modal--wide' : '')} aria-describedby={description ? descriptionId : undefined}>
        <header className="modal__head">
          <div>
            {eyebrow ? <div className="modal__eyebrow">{eyebrow}</div> : null}
            <h2 className="modal__title" id={titleId}>{title}</h2>
            {description ? <p className="modal__desc" id={descriptionId}>{description}</p> : null}
          </div>
          <button type="button" className="icon-btn" aria-label="关闭对话框" title="关闭对话框" onClick={onClose}>
            <span aria-hidden="true" className="overlay-close-glyph">×</span>
          </button>
        </header>
        <div className="modal__body">{children}</div>
        {footer ? <footer className="modal__foot">{footer}</footer> : null}
      </div>
    </Overlay>
  );
}