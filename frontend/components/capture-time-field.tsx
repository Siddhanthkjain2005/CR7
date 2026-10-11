'use client';
import {useId} from 'react';
import {captureTimeNow} from '@/lib/capture-time';

export default function CaptureTimeField({value, onChange}: {value: string; onChange: (value: string) => void}) {
  const id = useId();
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>Captured at (ISO 8601)</label>
      <input id={id} type="text" value={value} autoComplete="off" spellCheck={false}
        placeholder="YYYY-MM-DDTHH:mm:ss±HH:mm" aria-describedby={`${id}-help`}
        onChange={e => onChange(e.target.value)} />
      <small id={`${id}-help`}>Autofilled from this device’s clock, including the time zone. Change to the actual capture time, or clear if unknown.</small>
      <div className="page-actions">
        <button type="button" className="button small" onClick={() => onChange(captureTimeNow())}>Use current time</button>
        <button type="button" className="button small" onClick={() => onChange('')}>Clear time</button>
      </div>
    </div>
  );
}
