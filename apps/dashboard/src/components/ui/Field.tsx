import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
  labelHint,
  className = '',
}: {
  label: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  labelHint?: ReactNode;
  className?: string;
}) {
  return (
    <div className={['field', className].filter(Boolean).join(' ')}>
      <label className="field__label" htmlFor={htmlFor}>
        <span>{label}</span>
        {labelHint ? <span className="field__label-hint">{labelHint}</span> : null}
      </label>
      {children}
      {hint ? <p className="field__hint">{hint}</p> : null}
      {error ? <p className="field__error" role="alert">{error}</p> : null}
    </div>
  );
}

export function TextInput({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={['input', className].filter(Boolean).join(' ')} />;
}

export function TextArea({ className = '', ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={['textarea', className].filter(Boolean).join(' ')} />;
}

export function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={['select', className].filter(Boolean).join(' ')}>
      {children}
    </select>
  );
}