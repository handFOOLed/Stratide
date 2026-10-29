import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Icon } from '../../icons';
import type { IconName } from '../../icons';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link';
type Size = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  iconRight?: IconName;
  loading?: boolean;
  block?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  iconRight,
  loading = false,
  block = false,
  className = '',
  disabled,
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={[
        'btn',
        `btn--${variant}`,
        size === 'sm' ? 'btn--sm' : size === 'lg' ? 'btn--lg' : '',
        block ? 'btn--block' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-loading={loading || undefined}
    >
      {loading ? <span className="spinner" aria-hidden="true" /> : icon ? <Icon name={icon} /> : null}
      {children}
      {iconRight ? <Icon name={iconRight} /> : null}
    </button>
  );
}

export function IconButton({
  label,
  icon,
  size = 18,
  className = '',
  variant,
  ...rest
}: {
  label: string;
  icon: IconName;
  size?: number;
  className?: string;
  variant?: 'danger';
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'children'>) {
  return (
    <button
      {...rest}
      type={rest.type ?? 'button'}
      className={['icon-btn', variant === 'danger' ? 'icon-btn--danger' : '', className]
        .filter(Boolean)
        .join(' ')}
      aria-label={label}
      title={label}
    >
      <Icon name={icon} size={size} />
    </button>
  );
}
