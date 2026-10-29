import type { ReactNode, Ref } from 'react';

export function PageHeader({
  eyebrow,
  title,
  description,
  side,
  titleRef,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  side?: ReactNode;
  titleRef?: Ref<HTMLHeadingElement>;
}) {
  return (
    <header className="page-header">
      <div className="page-header__main">
        {eyebrow ? <div className="page-eyebrow">{eyebrow}</div> : null}
        <h1 className="page-title" ref={titleRef} tabIndex={-1}>
          {title}
        </h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {side ? <div className="page-header__side">{side}</div> : null}
    </header>
  );
}

export function PageMeta({ children }: { children: ReactNode }) {
  return <div className="page-meta">{children}</div>;
}

export function MetaSep() {
  return <span className="page-meta__sep" aria-hidden="true">·</span>;
}
