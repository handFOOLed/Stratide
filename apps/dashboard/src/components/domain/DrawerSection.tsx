import type { ReactNode } from 'react';

export function DrawerSection({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <section className="drawer__section">
      <h3 className="drawer__section-title">{title}</h3>
      {children}
    </section>
  );
}

export function DrawerNote({ children }: { children: ReactNode }) {
  return <p className="drawer-note">{children}</p>;
}
