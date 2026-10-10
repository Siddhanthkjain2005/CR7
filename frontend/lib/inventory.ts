import {Data} from './api';

/**
 * Pure helpers for the structured stock editor. They emit exactly the existing
 * `inventory_override` payload: {front:[{ohm,count_per_stage}], tail:[...], provenance}.
 * Bounds are validated by the backend schema, not duplicated here.
 */
export type StockRow = {ohm: string; count: string};
export type InventoryDraft = {front: StockRow[]; tail: StockRow[]; provenance: string};

export const emptyDraft = (): InventoryDraft => ({front: [{ohm: '', count: ''}], tail: [{ohm: '', count: ''}], provenance: ''});

export function draftFromOverride(o: Data | null | undefined): InventoryDraft {
  if (!o) return emptyDraft();
  const rows = (list: unknown): StockRow[] =>
    Array.isArray(list) && list.length ? list.map((r: Data) => ({ohm: r?.ohm == null ? '' : String(r.ohm), count: r?.count_per_stage == null ? '' : String(r.count_per_stage)})) : [{ohm: '', count: ''}];
  return {front: rows(o.front), tail: rows(o.tail), provenance: typeof o.provenance === 'string' ? o.provenance : ''};
}

export function overrideFromDraft(d: InventoryDraft): {value: Data} | {error: string} {
  const rows = (list: StockRow[], name: string) => {
    const used = list.filter(r => r.ohm.trim() !== '' || r.count.trim() !== '');
    for (const r of used) {
      if (r.ohm.trim() === '' || !Number.isFinite(Number(r.ohm))) return {error: `${name}: every row needs a resistance in ohms.`};
      if (r.count.trim() === '' || !Number.isInteger(Number(r.count))) return {error: `${name}: every row needs a whole number of units per stage.`};
    }
    return {value: used.map(r => ({ohm: Number(r.ohm), count_per_stage: Number(r.count)}))};
  };
  const front = rows(d.front, 'Front stock');
  if ('error' in front) return front;
  const tail = rows(d.tail, 'Tail stock');
  if ('error' in tail) return tail;
  if (!front.value.length || !tail.value.length) return {error: 'Enter at least one front and one tail stock value with its count per stage.'};
  if (d.provenance.trim().length < 3) return {error: 'Describe where these counts come from (provenance), for example “Engineer counted rack B, 7 Oct”.'};
  return {value: {front: front.value, tail: tail.value, provenance: d.provenance.trim()}};
}
