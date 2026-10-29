import type { IconName } from '../../icons';
import { Icon } from '../../icons';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: IconName;
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  compact = false,
  disabled = false,
}: {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  compact?: boolean;
  disabled?: boolean;
}) {
  return (
    <div
      className={`segmented${compact ? ' segmented--compact' : ''}`}
      role="group"
      aria-label={label}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="segmented__item"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          disabled={disabled}
        >
          {option.icon ? <Icon name={option.icon} size={13} /> : null}
          {option.label}
        </button>
      ))}
    </div>
  );
}
