'use client';
import {useEffect, useState} from 'react';
import {ClipboardCheck, LoaderCircle} from 'lucide-react';
import {api, Data, post, stamp} from '@/lib/api';
import {Badge, Notice} from './ui';

const USES: [string, string][] = [
  ['local_correction', 'One-shot offset'],
  ['parameter_fit', 'Generator parameter fit'],
  ['evaluation', 'Independent evaluation'],
];

/** Live shared admission of a saved capture, with append-only reviewer decisions. */
export default function CaptureAdmission({trialId, onChange}: {trialId: string; onChange?: (a: Data) => void}) {
  const [admission, setAdmission] = useState<Data | null>(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState<Data>({decision: 'accept_flags', codes: [], reviewer: '', reason: ''});
  const [busy, setBusy] = useState(false);
  async function load() {
    try {
      const a = await api(`/api/trials/${trialId}/admission`);
      setAdmission(a);
      onChange?.(a);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    setAdmission(null);
    setError('');
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trialId]);
  if (error) return <Notice tone="red">{error}</Notice>;
  if (!admission) return <p className="field-help"><LoaderCircle size={13} className="spin" aria-hidden /> Checking admission…</p>;
  const open: Data[] = Object.values(admission.uses as Record<string, Data>).flatMap(u => u.awaiting_review);
  const reviewable: Data[] = Array.from(new Map(open.map((i: Data) => [i.code, i])).values());
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await post(`/api/trials/${trialId}/reviews`, {...form, codes: form.decision === 'accept_flags' ? form.codes : []});
      setForm({...form, codes: [], reason: ''});
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="admission">
      <h3>Can this capture be used?</h3>
      <ul className="admission-uses">
        {USES.map(([key, label]) => {
          const u = admission.uses[key];
          const tone = u.admitted ? 'green' : u.blocking.length ? 'red' : 'amber';
          return (
            <li key={key}>
              <Badge tone={tone}>{u.admitted ? 'Admitted' : u.blocking.length ? 'Blocked' : 'Awaiting review'}</Badge> <b>{label}</b>
              {[...u.blocking, ...u.awaiting_review].length > 0 && (
                <ul>{[...u.blocking, ...u.awaiting_review].map((i: Data, n: number) => <li key={n}>{i.message}</li>)}</ul>
              )}
              {u.accepted_by_review.length > 0 && <small className="block">Accepted by review: {u.accepted_by_review.map((i: Data) => i.code.replaceAll('_', ' ')).join(', ')}</small>}
            </li>
          );
        })}
      </ul>
      <details className="disclosure">
        <summary>Record a review decision<small>{admission.review.history.length ? `${admission.review.history.length} recorded` : 'Qualified reviewer only'}</small></summary>
        <form className="disclosure-body review-form" onSubmit={submit}>
          <p className="field-help">Decisions are added to the record; the capture, its samples and its metrics are never changed. Blocking issues (polarity mismatch, disconnected rise, changed file, validation purpose) cannot be accepted.</p>
          <div className="segmented segmented-small" role="radiogroup" aria-label="Decision">
            {[['accept_flags', 'Accept review flags'], ['exclude', 'Exclude capture'], ['reinstate', 'Reinstate']].map(([id, label]) => (
              <button key={id} type="button" role="radio" aria-checked={form.decision === id} className={form.decision === id ? 'active' : ''} onClick={() => setForm({...form, decision: id})}>{label}</button>
            ))}
          </div>
          {form.decision === 'accept_flags' && (
            reviewable.length ? (
              <div className="review-codes">
                {reviewable.map(i => (
                  <label key={i.code} className="radio">
                    <input type="checkbox" checked={form.codes.includes(i.code)} onChange={() => setForm({...form, codes: form.codes.includes(i.code) ? form.codes.filter((c: string) => c !== i.code) : [...form.codes, i.code]})} />
                    <span>{i.code.replaceAll('_', ' ')}<small>{i.message}</small></span>
                  </label>
                ))}
              </div>
            ) : <p className="field-help">No reviewable flags are open on this capture.</p>
          )}
          <div className="two-fields">
            <label className="field"><span>Reviewer</span><input required minLength={2} value={form.reviewer} onChange={e => setForm({...form, reviewer: e.target.value})} /></label>
            <label className="field"><span>Reason</span><input required minLength={10} value={form.reason} placeholder="What was checked, and why it is acceptable" onChange={e => setForm({...form, reason: e.target.value})} /></label>
          </div>
          <button className="button small" type="submit" disabled={busy || (form.decision === 'accept_flags' && !form.codes.length)}>
            {busy ? <LoaderCircle size={14} className="spin" aria-hidden /> : <ClipboardCheck size={14} aria-hidden />} Record decision
          </button>
          {admission.review.history.length > 0 && (
            <ul className="review-history">
              {admission.review.history.map((h: Data) => <li key={h.id}><b>{h.decision.replaceAll('_', ' ')}</b>{h.codes?.length ? ` (${h.codes.join(', ')})` : ''} · {h.reviewer} · {stamp(h.created_at)} — {h.reason}</li>)}
            </ul>
          )}
        </form>
      </details>
    </div>
  );
}
