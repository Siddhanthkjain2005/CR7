'use client';
import {useState} from 'react';
import Link from 'next/link';
import {ArrowRight, ArrowUpRight, FileCheck2} from 'lucide-react';
import {apiUrl, Data, fmt, human, isNum, profileInputs} from '@/lib/api';
import {Badge, Empty, KindTag, Notice, PageHeading, Panel, Skeleton} from './ui';
import {useWorkspace} from './workspace';

const kindTag = (p: Data) => (p.kind === 'specified_hardware' ? <KindTag kind="simulation">Specified hardware</KindTag> : p.kind === 'synthetic_reference' ? <KindTag kind="synthetic">Synthetic reference</KindTag> : <KindTag kind="unknown">Incomplete</KindTag>);
const val = (v: unknown, digits: number, unit: string) => (isNum(v) ? `${fmt(v, digits)} ${unit}` : null);

export function Profiles() {
  const {profiles, inputs, setInputs} = useWorkspace();
  const [active, setActive] = useState('cpri_problem_brief_profile');
  const p = profiles.find(x => x.id === active);
  const specs = (x: Data): [string, string | null][] => [
    ['Voltage envelope', isNum(x.voltage_max_kv) ? (isNum(x.voltage_min_kv) ? `${fmt(x.voltage_min_kv, 0)}–${fmt(x.voltage_max_kv, 0)} kV` : `up to ${fmt(x.voltage_max_kv, 0)} kV · minimum unknown`) : null],
    ['Stages', x.min_stages != null ? `${x.min_stages}–${x.max_stages}` : `up to ${x.max_stages} · minimum unknown`],
    ['Stage voltage', val(x.stage_kv, 0, 'kV')],
    ['Stage capacitance', val(x.stage_c_uf, 3, 'µF')],
    ['Energy per stage', val(x.energy_stage_kj, 1, 'kJ')],
    ['Total energy rating', val(x.energy_total_kj, 0, 'kJ')],
    ['Base capacitance', val(x.base_c_pf, 0, 'pF')],
    ['Charging resistor', val(x.charging_r_ohm, 0, 'Ω')],
    ['Pulse repetition', x.pulses_per_min ? `${x.pulses_per_min} / min` : null],
    ['Stock per value per stage', isNum(x.units_per_value_per_stage) ? String(x.units_per_value_per_stage) : null],
  ];
  return (
    <>
      <PageHeading tag="Engineering" title="Generator profiles" description="Each source stays separate. CPRI physical parameters lead the engineering path; the synthetic workbook remains a reference and ML benchmark; the incomplete briefing profile is inspect-only." />
      {!profiles.length ? (
        <Panel>
          <Skeleton lines={4} />
        </Panel>
      ) : (
        <>
          <div className="nameplates" role="tablist" aria-label="Generator profiles">
            {profiles.map(x => (
              <button key={x.id} role="tab" aria-selected={active === x.id} onClick={() => setActive(x.id)} className={`nameplate ${active === x.id ? 'selected' : ''} nameplate-${x.kind}`}>
                {kindTag(x)}
                <h3>{x.name}</h3>
                <div className="nameplate-figure">
                  <strong>{fmt(x.voltage_max_kv, 0)}</strong>
                  <small>kV max</small>
                </div>
                <dl>
                  <div>
                    <dt>Stages</dt>
                    <dd>{x.max_stages}</dd>
                  </div>
                  <div>
                    <dt>kV / stage</dt>
                    <dd>{fmt(x.stage_kv, 0)}</dd>
                  </div>
                  <div>
                    <dt>µF / stage</dt>
                    <dd>{isNum(x.stage_c_uf) ? fmt(x.stage_c_uf, 3) : <span className="unrecorded">Unknown</span>}</dd>
                  </div>
                </dl>
                <span className="nameplate-cta">
                  {active === x.id ? 'Inspecting' : 'Inspect provenance'} <ArrowRight size={13} aria-hidden />
                </span>
              </button>
            ))}
          </div>

          <Panel title="Side by side, never merged" eyebrow="Values exactly as each source states them; blank cells are unknown, not zero.">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Parameter</th>
                    {profiles.map(x => (
                      <th key={x.id}>{x.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {specs(profiles[0]).map(([label], row) => (
                    <tr key={label}>
                      <td>{label}</td>
                      {profiles.map(x => {
                        const v = specs(x)[row][1];
                        return <td key={x.id}>{v ?? <span className="unrecorded">Unknown</span>}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {p && (
            <>
              <Panel
                title={p.name}
                eyebrow={`Version ${p.version} · ${human(p.kind)}`}
                action={
                  p.enabled ? (
                    <Link className="button small primary" href="/" onClick={() => setInputs(profileInputs(inputs, p.id))}>
                      Use profile <ArrowRight size={14} aria-hidden />
                    </Link>
                  ) : (
                    <span className="button small disabled" aria-disabled="true">
                      Inspect only
                    </span>
                  )
                }
              >
                <div className="source-block">
                  <FileCheck2 size={19} aria-hidden />
                  <div>
                    <strong>Source</strong>
                    <p>{p.source}</p>
                  </div>
                </div>
                <div className="spec-grid">
                  {specs(p).map(([k, v]) => (
                    <div key={k}>
                      <span>{k}</span>
                      <strong>{v ?? <span className="unrecorded">Unknown</span>}</strong>
                    </div>
                  ))}
                </div>
                <p className="panel-note">Energy provenance: {p.energy_provenance}. Missing values remain unknown.</p>
              </Panel>
              <div className="bottom-grid">
                <Panel title="Resistor values in the source" action={<Badge tone={p.units_per_value_per_stage ? 'cyan' : 'amber'}>{p.units_per_value_per_stage ? `${p.units_per_value_per_stage} units / value / stage` : 'Counts not supplied'}</Badge>}>
                  <div className="inventory-list">
                    {[
                      ['Front', p.front_values],
                      ['Lightning tail', p.lightning_tail_values],
                      ['Switching tail', p.switching_tail_values],
                    ].map(([name, values]) => (
                      <div key={String(name)}>
                        <span>{String(name)}</span>
                        <div>{(values as number[]).length ? (values as number[]).map(v => <Badge key={v}>{v.toLocaleString('en-US')} Ω</Badge>) : <span className="unrecorded">Unknown</span>}</div>
                      </div>
                    ))}
                  </div>
                  <p className="panel-note">Inventory overrides are entered in the optimizer with explicit quantities and provenance. Source profiles remain versioned.</p>
                </Panel>
                <Panel title="Unresolved assumptions">
                  <ul className="notes-list">
                    {p.notes.map((note: string) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                  {!p.enabled && <Notice tone="red">Optimization is disabled until missing specifications are verified.</Notice>}
                  <a className="button text-button" href={apiUrl('/api/documents/source_reconciliation')} target="_blank" rel="noreferrer">
                    View every source contradiction <ArrowUpRight size={14} aria-hidden />
                  </a>
                </Panel>
              </div>
            </>
          )}
          {!p && <Empty title="Choose a profile to inspect" />}
        </>
      )}
    </>
  );
}

