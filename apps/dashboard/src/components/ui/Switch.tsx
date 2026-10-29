import { Icon } from '../../icons';

export function Switch({
  checked,
  onChange,
  disabled = false,
  busy = false,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  busy?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className="switch"
      data-checked={checked}
      disabled={disabled || busy}
      onClick={() => onChange(!checked)}
    >
      <span className="switch__track" aria-hidden="true">
        <span className="switch__thumb" />
        {busy ? <span className="switch__busy" /> : null}
      </span>
      {busy ? <Icon name="refresh" size={12} className="switch__spin" /> : null}
    </button>
  );
}
