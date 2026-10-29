import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '../../icons';
import type { IconName } from '../../icons';

type ToastTone = 'success' | 'danger' | 'warning' | 'info';

interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
}

interface ToastApi {
  push: (toast: { title: string; description?: string; tone?: ToastTone }) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const TONE_ICON: Record<ToastTone, IconName> = {
  success: 'check',
  danger: 'alert-octagon',
  warning: 'alert-triangle',
  info: 'info',
};

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const [leaving, setLeaving] = useState<number[]>([]);
  const timers = useRef(new Map<number, number>());

  const remove = useCallback((id: number) => {
    setLeaving((current) => (current.includes(id) ? current : [...current, id]));
    const timer = window.setTimeout(() => {
      setItems((current) => current.filter((item) => item.id !== id));
      setLeaving((current) => current.filter((value) => value !== id));
      timers.current.delete(id);
    }, 180);
    timers.current.set(id, timer);
  }, []);

  const push = useCallback(
    ({ title, description, tone = 'info' }: { title: string; description?: string; tone?: ToastTone }) => {
      const id = nextId;
      nextId += 1;
      setItems((current) => [...current.slice(-3), { id, title, description, tone }]);
      const timer = window.setTimeout(() => remove(id), 5200);
      timers.current.set(id, timer);
    },
    [remove],
  );

  useEffect(() => {
    const active = timers.current;
    return () => {
      for (const timer of active.values()) window.clearTimeout(timer);
      active.clear();
    };
  }, []);

  const api = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {createPortal(
        <div className="toast-viewport" aria-live="polite" aria-atomic="false">
          {items.map((item) => (
            <div
              key={item.id}
              className={'toast toast--' + item.tone}
              data-leaving={leaving.includes(item.id) ? 'true' : undefined}
            >
              <span className="toast__icon" aria-hidden="true">
                <Icon name={TONE_ICON[item.tone]} />
              </span>
              <div className="toast__body">
                <div className="toast__title">{item.title}</div>
                {item.description ? <div className="toast__desc">{item.description}</div> : null}
              </div>
              <button
                type="button"
                className="toast__close"
                aria-label="关闭提示"
                title="关闭提示"
                onClick={() => remove(item.id)}
              >
                <Icon name="close" size={12} />
              </button>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const value = useContext(ToastContext);
  if (!value) {
    throw new Error('useToast must be used inside ToastProvider');
  }
  return value;
}
