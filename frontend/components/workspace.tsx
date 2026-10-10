'use client';
import {createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, ReactNode} from 'react';
import Link from 'next/link';
import {usePathname, useRouter} from 'next/navigation';
import {
  ArrowDownToLine,
  ArrowUpRight,
  Blocks,
  ChartNoAxesCombined,
  CircleHelp,
  Command,
  FileText,
  FlaskConical,
  GitCompareArrows,
  History,
  Menu,
  Microscope,
  Presentation,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Timer,
  Unplug,
  Waves,
  X,
} from 'lucide-react';
import {api, apiUrl, Data, fmt, initialInputs, post, requestKey, shortId, stamp} from '@/lib/api';

export {Badge, Status, Panel, PageHeading, Empty} from './ui';

type Store = {
  profiles: Data[];
  run: Data | null;
  candidate: Data | null;
  selected: number;
  setSelected: (v: number) => void;
  inputs: Data;
  setInputs: (v: Data) => void;
  busy: boolean;
  error: string;
  setError: (v: string) => void;
  optimize: (values?: Data) => Promise<Data | null>;
  loadRun: (id: string) => Promise<void>;
  online: boolean | null;
  reconnect: () => void;
  source: Data | null;
  trial: Data | null;
  setTrial: (v: Data | null) => void;
  calibration: Data | null;
  setCalibration: (v: Data | null) => void;
  /** Increments each time a new saved run is accepted; drives one-time presentation motion. */
  runSerial: number;
  draftEdited: boolean;
  /** Request fields edited locally by a form (e.g. the stock table) and not yet in `inputs`. */
  setDraftOverride: (v: Data | null) => void;
  motion: 'full' | 'quiet';
  setMotion: (m: 'full' | 'quiet') => void;
};
const Context = createContext<Store | null>(null);
export const useWorkspace = () => useContext(Context)!;

type NavItem = {href: string; name: string; icon: typeof Waves; hint: string};
export const NAV_GROUPS: {id: string; name: string; home: string; items: NavItem[]}[] = [
  {
    id: 'workflow',
    name: 'Test setup',
    home: '/',
    items: [
      {href: '/', name: 'Configure & recommend', icon: SlidersHorizontal, hint: 'Configure the test, recommend settings, inspect the waveform'},
      {href: '/trial-calibrator/', name: 'Compare measurement', icon: FlaskConical, hint: 'Import a measured waveform and compare it with the prediction'},
    ],
  },
  {
    id: 'evidence',
    name: 'Evidence',
    home: '/model-lab/',
    items: [
      {href: '/model-lab/', name: 'Model lab', icon: ChartNoAxesCombined, hint: 'Evaluation pack, surrogate study, saved model comparisons'},
      {href: '/laboratory-evidence/', name: 'Laboratory evidence', icon: Microscope, hint: 'Capture provenance and admission'},
      {href: '/hardware-verification/', name: 'Hardware verification', icon: ShieldCheck, hint: 'Known, assumed and unknown hardware facts'},
      {href: '/experiment-timeline/', name: 'Experiment timeline', icon: Timer, hint: 'Studies, promotions and rejections'},
      {href: '/search-quality/', name: 'Search quality', icon: Search, hint: 'Bounded versus exhaustive search'},
    ],
  },
  {
    id: 'more',
    name: 'More',
    home: '/judge/',
    items: [
      {href: '/judge/', name: 'Guided walkthrough', icon: Presentation, hint: 'Seven-step presentation of a saved run'},
      {href: '/compare/', name: 'Compare alternatives', icon: GitCompareArrows, hint: 'Alternatives and changes from a saved setup'},
      {href: '/runs/', name: 'Run history', icon: History, hint: 'Find, restore and export saved runs'},
      {href: '/profiles/', name: 'Generator profiles', icon: Blocks, hint: 'Source identity, ratings, stock values'},
    ],
  },
];

const ALL_PAGES = NAV_GROUPS.flatMap(g => g.items.map(i => ({...i, group: g.name})));
const norm = (p: string) => (p || '/').replace(/\/$/, '') || '/';

export function Workspace({children}: {children: ReactNode}) {
  const [profiles, setProfiles] = useState<Data[]>([]),
    [run, setRun] = useState<Data | null>(null),
    [selected, setSelected] = useState(0),
    [inputs, setInputs] = useState<Data>(initialInputs),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [online, setOnline] = useState<boolean | null>(null),
    [source, setSource] = useState<Data | null>(null),
    [trial, setTrial] = useState<Data | null>(null),
    [calibration, setCalibration] = useState<Data | null>(null),
    [runSerial, setRunSerial] = useState(0),
    [connectSerial, setConnectSerial] = useState(0),
    [motion, setMotionState] = useState<'full' | 'quiet'>('full'),
    [draftOverride, setDraftOverride] = useState<Data | null>(null);
  const ticket = useRef(0);
  const inFlight = useRef(false);
  const runRef = useRef<Data | null>(null);
  useEffect(() => {
    runRef.current = run;
  }, [run]);

  const inputsRef = useRef<Data>(initialInputs);
  useEffect(() => {
    inputsRef.current = inputs;
  }, [inputs]);

  // keepEdits: the request form was edited while this run was being solved, so the
  // form keeps those edits (and shows them as unsolved) instead of snapping back.
  const accept = useCallback((r: Data, fresh = false, keepEdits = false) => {
    runRef.current = r;
    setRun(r);
    setSelected(0);
    if (!keepEdits) setInputs(r.inputs);
    if (fresh) setRunSerial(n => n + 1);
    try {
      localStorage.setItem('impulsetwin-last-run', r.id);
    } catch {
      /* storage unavailable: the run remains in memory */
    }
  }, []);

  const loadRun = useCallback(
    async (id: string) => {
      const mine = ++ticket.current;
      setBusy(true);
      setError('');
      try {
        const r = await api(`/api/runs/${id}`);
        if (mine === ticket.current) accept(r);
      } catch (e) {
        if (mine === ticket.current) setError((e as Error).message);
      } finally {
        if (mine === ticket.current) setBusy(false);
      }
    },
    [accept],
  );

  const optimize = useCallback(
    async (values?: Data) => {
      // One optimization at a time: a second click while solving is ignored, and a
      // response that is no longer the latest request never replaces the selection.
      if (inFlight.current) return null;
      inFlight.current = true;
      const mine = ++ticket.current;
      const formAtSubmit = requestKey(inputsRef.current);
      setBusy(true);
      setError('');
      try {
        const r = await post('/api/optimize', values || inputs);
        if (mine !== ticket.current) return null;
        accept(r, true, requestKey(inputsRef.current) !== formAtSubmit);
        return r;
      } catch (e) {
        if (mine === ticket.current) setError((e as Error).message);
        return null;
      } finally {
        inFlight.current = false;
        if (mine === ticket.current) setBusy(false);
      }
    },
    [inputs, accept],
  );

  useEffect(() => {
    let alive = true;
    setOnline(null);
    Promise.allSettled([api('/api/health'), api('/api/generator-profiles'), api('/api/source-status')]).then(async results => {
      if (!alive) return;
      setOnline(results[0].status === 'fulfilled');
      if (results[1].status === 'fulfilled') setProfiles(results[1].value);
      if (results[2].status === 'fulfilled') setSource(results[2].value);
      if (results[0].status !== 'fulfilled') {
        setError('The local engineering service is unavailable. Start the backend, then reconnect.');
        return;
      }
      setError(e => (e.startsWith('The local engineering service is unavailable') ? '' : e));
      let id: string | null = null;
      try {
        id = localStorage.getItem('impulsetwin-last-run');
      } catch {
        id = null;
      }
      if (id) {
        try {
          const saved = await api(`/api/runs/${id}`);
          // Never replace a run the operator produced or opened while this was loading.
          if (alive && !runRef.current) accept(saved);
        } catch {
          try {
            localStorage.removeItem('impulsetwin-last-run');
          } catch {
            /* ignore */
          }
        }
      }
    });
    return () => {
      alive = false;
    };
  }, [accept, connectSerial]);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem('impulsetwin-motion');
    } catch {
      stored = null;
    }
    if (stored === 'quiet') setMotionState('quiet');
  }, []);
  useEffect(() => {
    document.documentElement.dataset.motion = motion;
  }, [motion]);
  const setMotion = useCallback((m: 'full' | 'quiet') => {
    setMotionState(m);
    try {
      localStorage.setItem('impulsetwin-motion', m);
    } catch {
      /* ignore */
    }
  }, []);

  const draftEdited = !!run && requestKey(run.inputs) !== requestKey(draftOverride ? {...inputs, ...draftOverride} : inputs);
  const value = useMemo<Store>(
    () => ({
      profiles,
      run,
      candidate: run?.candidates?.[selected] || null,
      selected,
      setSelected,
      inputs,
      setInputs,
      busy,
      error,
      setError,
      optimize,
      loadRun,
      online,
      reconnect: () => setConnectSerial(n => n + 1),
      source,
      trial,
      setTrial,
      calibration,
      setCalibration,
      runSerial,
      draftEdited,
      setDraftOverride,
      motion,
      setMotion,
    }),
    [profiles, run, selected, inputs, busy, error, optimize, loadRun, online, source, trial, calibration, runSerial, draftEdited, motion, setMotion],
  );
  return (
    <Context.Provider value={value}>
      <Shell>{children}</Shell>
    </Context.Provider>
  );
}

function BrandMark() {
  // A lightning-impulse trace (fast front, slow tail) inside a stage frame.
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" width="30" height="30" aria-hidden>
      <rect x="1" y="1" width="30" height="30" rx="7" className="brand-mark-bg" />
      <path d="M5 24 H8 C9 24 9.5 7 11.5 7 C15 7 18 16 27 21" className="brand-mark-trace" />
      <path d="M5 24 H27" className="brand-mark-base" />
    </svg>
  );
}

function Shell({children}: {children: ReactNode}) {
  const w = useWorkspace();
  const path = norm(usePathname());
  const group = NAV_GROUPS.find(g => g.items.some(i => norm(i.href) === path)) || NAV_GROUPS[0];
  const [menu, setMenu] = useState(false);
  const [palette, setPalette] = useState(false);
  useEffect(() => setMenu(false), [path]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPalette(p => !p);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const isJudge = norm(path) === '/judge';
  return (
    <div className={`shell ${isJudge ? 'shell-judge' : ''}`}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-row">
          <Link className="brand" href="/" aria-label="ImpulseTwin AI · Optimizer">
            <BrandMark />
            <span className="brand-name">
              ImpulseTwin <span>AI</span>
            </span>
          </Link>
          <nav className="sections" aria-label="Sections">
            {NAV_GROUPS.map(g => (
              <Link key={g.id} href={g.home} className={g.id === group.id ? 'active' : ''} aria-current={g.id === group.id ? 'true' : undefined}>
                {g.name}
              </Link>
            ))}
          </nav>
          <div className="topbar-tools">
            <RunChip />
            <button className="palette-trigger" onClick={() => setPalette(true)} aria-label="Search pages and actions" aria-keyshortcuts="Control+K Meta+K">
              <Search size={15} aria-hidden />
              <span>Find</span>
              <kbd>
                <Command size={11} aria-hidden />K
              </kbd>
            </button>
            <EngineStatus />
            <button className="menu-trigger" aria-label="Open navigation" aria-expanded={menu} onClick={() => setMenu(m => !m)}>
              {menu ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
        {!isJudge && (
          <nav className="subnav" aria-label={`${group.name} pages`}>
            {group.items.map(item => {
              const active = norm(item.href) === path;
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}>
                  <Icon size={15} aria-hidden />
                  {item.name}
                </Link>
              );
            })}
          </nav>
        )}
        {menu && (
          <nav className="mobile-menu" aria-label="All pages">
            {NAV_GROUPS.map(g => (
              <div key={g.id}>
                <p>{g.name}</p>
                {g.items.map(item => (
                  <Link key={item.href} href={item.href} aria-current={norm(item.href) === path ? 'page' : undefined}>
                    <item.icon size={16} aria-hidden /> {item.name}
                  </Link>
                ))}
              </div>
            ))}
          </nav>
        )}
      </header>
      {w.online === false && (
        <div className="offline-banner" role="alert">
          <Unplug size={16} aria-hidden />
          <span>The local engineering service is not responding. Start it with <code>python scripts/dev.py</code>, then reconnect. Nothing below is a new result.</span>
          <button className="button small" onClick={w.reconnect}>
            <RefreshCw size={14} aria-hidden /> Reconnect
          </button>
        </div>
      )}
      <main id="main" tabIndex={-1}>
        {children}
      </main>
      <footer className="footer">
        <span>
          <ShieldCheck size={14} aria-hidden /> Decision support only. Engineer verification and laboratory procedures remain required; nothing here controls hardware.
        </span>
        <span className="footer-links">
          <a href={apiUrl('/api/documents/source_reconciliation')} target="_blank" rel="noreferrer">
            <CircleHelp size={14} aria-hidden /> Source reconciliation <ArrowUpRight size={12} aria-hidden />
          </a>
          <button className="text-toggle" onClick={() => w.setMotion(w.motion === 'quiet' ? 'full' : 'quiet')} aria-pressed={w.motion === 'quiet'}>
            Quiet motion {w.motion === 'quiet' ? 'on' : 'off'}
          </button>
        </span>
      </footer>
      {palette && <CommandPalette onClose={() => setPalette(false)} />}
    </div>
  );
}

function RunChip() {
  const {run, candidate, busy, draftEdited} = useWorkspace();
  if (busy)
    return (
      <span className="run-chip run-chip-busy" role="status">
        <span className="pulse-dot" aria-hidden /> Solving request…
      </span>
    );
  if (!run) return <span className="run-chip run-chip-empty">No saved run loaded</span>;
  return (
    <Link href="/" className={`run-chip ${draftEdited ? 'run-chip-draft' : ''}`} title={`Saved run ${run.id} · ${stamp(run.created_at)}`}>
      <span className="run-chip-id">Run {shortId(run.id)}</span>
      <span className="run-chip-meta">
        {run.inputs?.impulse_type} {fmt(run.inputs?.test_kv, 0)} kV · rank {candidate?.rank ?? '—'}
      </span>
      {draftEdited && <span className="run-chip-flag">Request edited</span>}
    </Link>
  );
}

function EngineStatus() {
  const {online, reconnect} = useWorkspace();
  if (online === false)
    return (
      <button className="engine engine-off" onClick={reconnect} aria-label="Engine offline. Reconnect">
        <Unplug size={14} aria-hidden /> <span>Offline · retry</span>
      </button>
    );
  return (
    <span className={`engine ${online ? 'engine-on' : 'engine-wait'}`} role="status">
      <span className="engine-dot" aria-hidden />
      <span>{online ? 'Local engine' : 'Connecting'}</span>
    </span>
  );
}

function CommandPalette({onClose}: {onClose: () => void}) {
  const w = useWorkspace();
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const previous = useRef<Element | null>(null);
  useEffect(() => {
    previous.current = document.activeElement;
    input.current?.focus();
    return () => (previous.current as HTMLElement | null)?.focus?.();
  }, []);
  type Item = {id: string; label: string; hint: string; group: string; icon: typeof Waves; run: () => void};
  const items: Item[] = [
    ...ALL_PAGES.map(p => ({id: p.href, label: p.name, hint: p.hint, group: p.group, icon: p.icon, run: () => router.push(p.href)})),
    ...(w.run
      ? [
          {id: 'report', label: 'Open engineering report', hint: `Saved run ${shortId(w.run.id)}`, group: 'Saved run', icon: FileText, run: () => window.open(apiUrl(`/api/runs/${w.run!.id}/report`), '_blank', 'noopener')},
          {id: 'json', label: 'Download run audit JSON', hint: `Saved run ${shortId(w.run.id)}`, group: 'Saved run', icon: ArrowDownToLine, run: () => window.location.assign(apiUrl(`/api/runs/${w.run!.id}/json`))},
        ]
      : []),
    {
      id: 'motion',
      label: w.motion === 'quiet' ? 'Turn quiet motion off' : 'Turn quiet motion on',
      hint: 'Presentation motion and the illustrative 3D sequence',
      group: 'Preferences',
      icon: Waves,
      run: () => w.setMotion(w.motion === 'quiet' ? 'full' : 'quiet'),
    },
  ];
  const q = query.trim().toLowerCase();
  const shown = q ? items.filter(i => `${i.label} ${i.hint} ${i.group}`.toLowerCase().includes(q)) : items;
  const choose = (item?: Item) => {
    if (!item) return;
    onClose();
    item.run();
  };
  return (
    <div className="palette-backdrop" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Find pages and actions">
        <div className="palette-input">
          <Search size={17} aria-hidden />
          <input
            ref={input}
            value={query}
            placeholder="Go to a page or run an action"
            aria-label="Search pages and actions"
            aria-controls="palette-list"
            aria-activedescendant={shown[index] ? `palette-${shown[index].id}` : undefined}
            onChange={e => {
              setQuery(e.target.value);
              setIndex(0);
            }}
            onKeyDown={e => {
              if (e.key === 'Escape') onClose();
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setIndex(i => Math.min(shown.length - 1, i + 1));
              }
              if (e.key === 'ArrowUp') {
                e.preventDefault();
                setIndex(i => Math.max(0, i - 1));
              }
              if (e.key === 'Enter') choose(shown[index]);
              if (e.key === 'Tab') e.preventDefault();
            }}
          />
          <kbd>Esc</kbd>
        </div>
        <ul id="palette-list" role="listbox" className="palette-list">
          {shown.map((item, i) => (
            <li
              key={item.id}
              id={`palette-${item.id}`}
              role="option"
              aria-selected={i === index}
              className={i === index ? 'active' : ''}
              onMouseEnter={() => setIndex(i)}
              onClick={() => choose(item)}
            >
              <item.icon size={16} aria-hidden />
              <span className="palette-label">{item.label}</span>
              <span className="palette-hint">{item.hint}</span>
              <span className="palette-group">{item.group}</span>
            </li>
          ))}
          {!shown.length && <li className="palette-none">No page or action matches “{query}”.</li>}
        </ul>
      </div>
    </div>
  );
}
