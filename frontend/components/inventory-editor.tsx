'use client';
import {useState} from 'react';
import {Braces, ListPlus, Plus, Trash2} from 'lucide-react';
import {Data} from '@/lib/api';
import {InventoryDraft, StockRow, draftFromOverride} from '@/lib/inventory';


/**
 * Structured editor for the existing `inventory_override` payload:
 * {front:[{ohm,count_per_stage}], tail:[{ohm,count_per_stage}], provenance}.
 * It emits exactly that shape; bounds are validated by the backend schema.
 */
export default function InventoryEditor({
  draft,
  onChange,
  profile,
  impulse,
  idPrefix,
}: {
  draft: InventoryDraft;
  onChange: (d: InventoryDraft) => void;
  profile?: Data | null;
  impulse: string;
  idPrefix: string;
}) {
  const [json, setJson] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState('');
  const sourceTail: number[] = (impulse === 'Switching' ? profile?.switching_tail_values : profile?.lightning_tail_values) || [];
  const sourceFront: number[] = profile?.front_values || [];
  const update = (side: 'front' | 'tail', i: number, key: keyof StockRow, value: string) => {
    const next = draft[side].map((r, j) => (j === i ? {...r, [key]: value} : r));
    onChange({...draft, [side]: next});
  };
  const loadSourceValues = () =>
    onChange({
      ...draft,
      front: sourceFront.length ? sourceFront.map(v => ({ohm: String(v), count: ''})) : draft.front,
      tail: sourceTail.length ? sourceTail.map(v => ({ohm: String(v), count: ''})) : draft.tail,
    });
  if (json !== null) {
    return (
      <div className="inventory">
        <label className="field">
          <span>Inventory override JSON</span>
          <textarea
            id={`${idPrefix}-json`}
            rows={8}
            value={json}
            spellCheck={false}
            onChange={e => {
              setJson(e.target.value);
              setJsonError('');
            }}
          />
          <small>Same payload the API receives: front and tail arrays of {'{ohm, count_per_stage}'} plus a provenance note.</small>
        </label>
        {jsonError && <p className="field-error" role="alert">{jsonError}</p>}
        <div className="inventory-actions">
          <button
            type="button"
            className="button small"
            onClick={() => {
              try {
                const parsed = JSON.parse(json);
                if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.front) || !Array.isArray(parsed.tail)) throw new Error('Expected an object with front and tail arrays.');
                onChange(draftFromOverride(parsed));
                setJson(null);
              } catch (e) {
                setJsonError(`Not applied: ${(e as Error).message}`);
              }
            }}
          >
            Apply JSON
          </button>
          <button type="button" className="button small ghost" onClick={() => setJson(null)}>
            Back to table
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="inventory">
      {(['front', 'tail'] as const).map(side => (
        <fieldset key={side} className="inventory-side">
          <legend>{side === 'front' ? 'Front resistors' : `${impulse} tail resistors`} · units per stage</legend>
          <div className="inventory-rows">
            {draft[side].map((row, i) => (
              <div className="inventory-row" key={i}>
                <label>
                  <span className="sr-only">
                    {side} value {i + 1} resistance
                  </span>
                  <span className="number-input">
                    <input type="number" inputMode="decimal" min={0} step="any" placeholder="Resistance" value={row.ohm} onChange={e => update(side, i, 'ohm', e.target.value)} />
                    <span>Ω</span>
                  </span>
                </label>
                <label>
                  <span className="sr-only">
                    {side} value {i + 1} count per stage
                  </span>
                  <span className="number-input">
                    <input type="number" inputMode="numeric" min={0} step={1} placeholder="Count" value={row.count} onChange={e => update(side, i, 'count', e.target.value)} />
                    <span>/stage</span>
                  </span>
                </label>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Remove ${side} row ${i + 1}`}
                  disabled={draft[side].length === 1}
                  onClick={() => onChange({...draft, [side]: draft[side].filter((_, j) => j !== i)})}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="button small ghost" onClick={() => onChange({...draft, [side]: [...draft[side], {ohm: '', count: ''}]})}>
            <Plus size={14} aria-hidden /> Add value
          </button>
        </fieldset>
      ))}
      <label className="field">
        <span>Provenance of these counts</span>
        <textarea
          className="plain"
          rows={2}
          value={draft.provenance}
          placeholder="Who counted, where, when — or label it clearly as an assumption"
          onChange={e => onChange({...draft, provenance: e.target.value})}
        />
        <small>Counts are per stage. Unverified counts must be labelled as an assumption; they are never treated as laboratory inventory.</small>
      </label>
      <div className="inventory-actions">
        {(sourceFront.length > 0 || sourceTail.length > 0) && (
          <button type="button" className="button small" onClick={loadSourceValues}>
            <ListPlus size={14} aria-hidden /> Fill source values (counts left blank)
          </button>
        )}
        <button
          type="button"
          className="button small ghost"
          onClick={() => {
            const value = (s: string) => (s.trim() !== '' && Number.isFinite(Number(s)) ? Number(s) : s);
            const rows = (list: StockRow[]) => list.filter(r => r.ohm.trim() || r.count.trim()).map(r => ({ohm: value(r.ohm), count_per_stage: value(r.count)}));
            setJson(JSON.stringify({front: rows(draft.front), tail: rows(draft.tail), provenance: draft.provenance}, null, 2));
          }}
        >
          <Braces size={14} aria-hidden /> Edit as JSON
        </button>
      </div>
    </div>
  );
}
