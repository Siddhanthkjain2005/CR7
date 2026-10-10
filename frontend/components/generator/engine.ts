/**
 * Conceptual Marx-generator scene (three.js r170, vendored locally).
 *
 * The stack is a SCHEMATIC driven by a saved GeneratorModel: active versus
 * inactive stages, and counted front/tail resistor banks per stage. It is
 * not a surveyed geometric twin: dimensions, mounting, wiring, spark-gap
 * behaviour and pulse ratings are not represented. The "erection" sequence
 * and the output glow are illustrative only.
 *
 * Rendering is on demand: frames are produced only while the camera settles,
 * an illustrative sequence plays, or something changes.
 */
import {
  ACESFilmicToneMapping,
  AdditiveBlending,
  AmbientLight,
  BackSide,
  BoxGeometry,
  BufferGeometry,
  CatmullRomCurve3,
  Color,
  CylinderGeometry,
  DirectionalLight,
  DoubleSide,
  EdgesGeometry,
  Fog,
  GridHelper,
  Group,
  HemisphereLight,
  InstancedMesh,
  LatheGeometry,
  LineBasicMaterial,
  LineSegments,
  Material,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  Object3D,
  PCFSoftShadowMap,
  PerspectiveCamera,
  PlaneGeometry,
  PMREMGenerator,
  PointLight,
  Quaternion,
  Raycaster,
  Scene,
  SphereGeometry,
  SRGBColorSpace,
  Texture,
  TorusGeometry,
  TubeGeometry,
  Vector2,
  Vector3,
  WebGLRenderer,
} from '@/vendor/three/three.module.min.js';
import type {GeneratorModel, NetworkModel, PartDelta, StageState} from '@/lib/generator-model';
import {KEPT_COLOR, layoutTree, valueColor} from '@/lib/generator-model';

export type SceneView = 'overview' | 'stack' | 'front' | 'tail' | 'output';
export type Anchor = {x: number; y: number; visible: boolean};
export type AnchorMap = Partial<Record<'stack' | 'front' | 'tail' | 'gap' | 'output' | 'ghost' | 'selected', Anchor>>;

export interface EngineOptions {
  quality: 'high' | 'low';
  onHover: (stage: number | null, x: number, y: number) => void;
  onSelect: (stage: number | null) => void;
  onAnchors: (anchors: AnchorMap) => void;
  onContextLost: () => void;
  onSequence?: (playing: boolean) => void;
}

const C = {
  hall: '#0e161d',
  floor: '#111b23',
  grid: '#22313c',
  gridMajor: '#2f4250',
  metal: '#aeb9c0',
  metalDark: '#5c6a74',
  epoxy: '#3a444d',
  porcelain: '#7a3f2e',
  band: '#2cc6da',
  bandIdle: '#33404b',
  ghost: '#7e93a3',
  added: '#3fd29a',
  removed: '#ff6f5c',
  spark: '#b8a7ff',
  output: '#2cc6da',
  torus: '#d3dbe0',
};

const PITCH = 0.56;
const PLINTH = 0.42;
const DECK_W = 2.5;
const DECK_D = 1.6;
const DIVIDER_X = 4.2;

type StageParts = {
  group: Group;
  level: number; // current animated activation 0..1
  from: number;
  target: number;
  state: StageState;
  materials: MeshStandardMaterial[];
  ghostLines: LineBasicMaterial;
  band: MeshStandardMaterial;
  sphere: MeshStandardMaterial;
  arc: MeshBasicMaterial;
  halo: MeshBasicMaterial;
  pickables: Object3D[];
  flash: number;
  charge: number;
};

function damp(current: number, target: number, lambda: number, dt: number) {
  return current + (target - current) * (1 - Math.exp(-lambda * dt));
}

export class GeneratorEngine {
  private renderer: WebGLRenderer;
  private scene = new Scene();
  private camera = new PerspectiveCamera(30, 1, 0.1, 200);
  private root = new Group();
  private stages: StageParts[] = [];
  private model: GeneratorModel | null = null;
  private pmrem: PMREMGenerator | null = null;
  private envTexture: Texture | null = null;
  private outputMat = new MeshStandardMaterial({color: C.output, emissive: new Color(C.output), emissiveIntensity: 0.15, metalness: 0.2, roughness: 0.4});
  private torusMat = new MeshStandardMaterial({color: C.torus, metalness: 0.92, roughness: 0.22, emissive: new Color(C.spark), emissiveIntensity: 0});
  private outputLight = new PointLight(C.spark, 0, 9, 1.6);
  private raycaster = new Raycaster();
  private pointer = new Vector2();
  private pickables: Object3D[] = [];
  private hovered: number | null = null;
  private selected: number | null = null;
  private frame = 0;
  private lastTime = 0;
  private active = true;
  private quiet = false;
  private disposed = false;
  private width = 1;
  private height = 1;
  // Camera state (spherical around a target, damped)
  private target = new Vector3(0.8, 3, 0);
  private goalTarget = new Vector3(0.8, 3, 0);
  private theta = 0.62;
  private phi = 1.2;
  private radius = 14;
  private goal = {theta: 0.62, phi: 1.2, radius: 14};
  private fit = 14;
  private view: SceneView = 'overview';
  private dragging: {x: number; y: number; theta: number; phi: number; moved: boolean} | null = null;
  private pinch: {d: number; radius: number} | null = null;
  private pointers = new Map<number, {x: number; y: number}>();
  // Illustrative sequence
  private sequence: {start: number; duration: number} | null = null;
  // Time-based stage morph so slow devices settle as quickly as fast ones.
  private morph = {start: 0, duration: 650};
  private outputGlow = 0;
  private pulse: number | null = null;
  private stackHeight = 7;
  private listeners: [EventTarget, string, EventListener][] = [];

  constructor(private canvas: HTMLCanvasElement, private options: EngineOptions) {
    this.renderer = new WebGLRenderer({canvas, antialias: true, alpha: false, powerPreference: 'high-performance'});
    this.renderer.outputColorSpace = SRGBColorSpace;
    this.renderer.toneMapping = ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    const dpr = Math.min(window.devicePixelRatio || 1, options.quality === 'high' ? 2 : 1.5);
    this.renderer.setPixelRatio(dpr);
    this.renderer.setClearColor(new Color(C.hall), 1);
    if (options.quality === 'high') {
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = PCFSoftShadowMap;
    }
    this.scene.background = new Color(C.hall);
    this.scene.fog = new Fog(new Color(C.hall), 18, 40);
    this.scene.add(this.root);
    this.buildEnvironment();
    this.buildLights();
    this.buildFloor();
    this.bindEvents();
  }

  /* ---------------------------------------------------------------- */
  /* Public API                                                       */
  /* ---------------------------------------------------------------- */

  setModel(model: GeneratorModel | null) {
    const previous = new Map(this.stages.map((s, i) => [i, s.level]));
    this.model = model;
    this.clearStack();
    if (!model) {
      this.requestRender();
      return;
    }
    this.buildStack(model, previous);
    this.morph.start = performance.now();
    this.computeFit();
    this.applyView(this.view, previous.size === 0);
    this.requestRender();
  }

  setView(view: SceneView, immediate = false) {
    this.view = view;
    this.applyView(view, immediate || this.quiet);
    this.requestRender();
  }

  setSelected(stage: number | null) {
    this.selected = stage;
    this.updateStageVisuals();
    this.requestRender();
  }

  setPulse(fraction: number | null) {
    this.pulse = fraction === null ? null : Math.max(0, Math.min(1, fraction));
    this.requestRender();
  }

  setQuiet(quiet: boolean) {
    this.quiet = quiet;
  }

  setActive(active: boolean) {
    this.active = active;
    if (active) this.requestRender();
  }

  play() {
    if (!this.model || this.model.activeStages < 1) return;
    if (this.quiet) {
      // Quiet motion: show the end state without a timed sequence.
      this.stages.forEach((s, i) => (s.charge = i < (this.model?.activeStages || 0) ? 0.5 : 0));
      this.outputGlow = 0.5;
      this.requestRender();
      return;
    }
    const n = this.model.activeStages;
    this.sequence = {start: performance.now(), duration: 0.35 + n * 0.085 + 1.1};
    this.options.onSequence?.(true);
    this.requestRender();
  }

  orbit(dTheta: number, dPhi: number) {
    this.goal.theta += dTheta;
    this.goal.phi = Math.min(1.52, Math.max(0.42, this.goal.phi + dPhi));
    this.requestRender();
  }

  zoom(factor: number) {
    this.goal.radius = Math.min(this.fit * 1.9, Math.max(this.fit * 0.32, this.goal.radius * factor));
    this.requestRender();
  }

  reset() {
    this.selected = null;
    this.options.onSelect(null);
    this.updateStageVisuals();
    this.applyView(this.view, false);
    this.requestRender();
  }

  focusStage(stage: number | null) {
    this.selected = stage;
    this.updateStageVisuals();
    if (stage !== null && this.stages[stage]) {
      const y = PLINTH + (stage + 0.5) * PITCH;
      this.goalTarget.set(0, y, 0);
      this.goal.radius = this.fit * 0.42;
      this.goal.phi = 1.32;
    }
    this.requestRender();
  }

  resize(width: number, height: number) {
    this.width = Math.max(1, width);
    this.height = Math.max(1, height);
    this.renderer.setSize(this.width, this.height, false);
    this.camera.aspect = this.width / this.height;
    this.camera.updateProjectionMatrix();
    this.computeFit();
    this.applyView(this.view, true);
    this.requestRender();
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.listeners.forEach(([t, type, fn]) => t.removeEventListener(type, fn));
    this.clearStack();
    this.scene.traverse(obj => this.disposeObject(obj));
    this.outputMat.dispose();
    this.torusMat.dispose();
    this.envTexture?.dispose();
    this.pmrem?.dispose();
    this.renderer.dispose();
  }

  /* ---------------------------------------------------------------- */
  /* Scene construction                                               */
  /* ---------------------------------------------------------------- */

  private buildEnvironment() {
    // Procedural studio for metal reflections; no external HDR files.
    this.pmrem = new PMREMGenerator(this.renderer);
    const env = new Scene();
    const sky = new Mesh(new SphereGeometry(20, 32, 16), new MeshBasicMaterial({color: '#1b2833', side: BackSide}));
    env.add(sky);
    const panel = (color: string, intensity: number, pos: [number, number, number], size: [number, number]) => {
      const m = new Mesh(new PlaneGeometry(size[0], size[1]), new MeshBasicMaterial({color: new Color(color).multiplyScalar(intensity), side: DoubleSide}));
      m.position.set(...pos);
      m.lookAt(0, 0, 0);
      env.add(m);
    };
    panel('#ffffff', 3.2, [6, 10, 6], [10, 4]);
    panel('#9fe7f2', 1.6, [-10, 4, -4], [6, 10]);
    panel('#ffe1c4', 1.2, [8, 2, -8], [6, 4]);
    panel('#20303c', 1, [0, -10, 0], [30, 30]);
    this.envTexture = this.pmrem.fromScene(env, 0.035).texture;
    this.scene.environment = this.envTexture;
    env.traverse(o => this.disposeObject(o));
  }

  private buildLights() {
    const hemi = new HemisphereLight('#c8d6e0', '#1a2229', 0.75);
    this.scene.add(hemi);
    this.scene.add(new AmbientLight('#8ea2b2', 0.12));
    const key = new DirectionalLight('#fff2e2', 2.1);
    key.position.set(6, 12, 8);
    if (this.options.quality === 'high') {
      key.castShadow = true;
      key.shadow.mapSize.set(1024, 1024);
      key.shadow.camera.left = -7;
      key.shadow.camera.right = 7;
      key.shadow.camera.top = 10;
      key.shadow.camera.bottom = -2;
      key.shadow.camera.near = 1;
      key.shadow.camera.far = 40;
      key.shadow.bias = -0.0006;
      key.shadow.normalBias = 0.02;
    }
    this.scene.add(key);
    const rim = new DirectionalLight('#5fd3e6', 1.1);
    rim.position.set(-7, 6, -7);
    this.scene.add(rim);
    this.outputLight.position.set(DIVIDER_X - 1, 6, 1);
    this.scene.add(this.outputLight);
  }

  private buildFloor() {
    const floor = new Mesh(new PlaneGeometry(80, 80), new MeshStandardMaterial({color: C.floor, roughness: 0.92, metalness: 0.05}));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    this.scene.add(floor);
    const grid = new GridHelper(40, 80, new Color(C.gridMajor), new Color(C.grid));
    grid.position.y = 0.002;
    const gm = grid.material as LineBasicMaterial;
    gm.transparent = true;
    gm.opacity = 0.55;
    this.scene.add(grid);
  }

  private standard(color: string, metalness: number, roughness: number): MeshStandardMaterial {
    return new MeshStandardMaterial({color: new Color(color), metalness, roughness, transparent: true, opacity: 1});
  }

  private insulatorGeometry(height: number, radius: number, sheds: number): LatheGeometry {
    const pts: Vector2[] = [new Vector2(0.0001, 0), new Vector2(radius * 1.25, 0), new Vector2(radius * 1.25, height * 0.04)];
    const usable = height * 0.92;
    for (let k = 0; k < sheds; k++) {
      const y0 = height * 0.04 + (usable * k) / sheds;
      const step = usable / sheds;
      pts.push(new Vector2(radius, y0 + step * 0.12));
      pts.push(new Vector2(radius * 1.95, y0 + step * 0.32));
      pts.push(new Vector2(radius * 1.85, y0 + step * 0.42));
      pts.push(new Vector2(radius, y0 + step * 0.62));
    }
    pts.push(new Vector2(radius * 1.25, height * 0.96));
    pts.push(new Vector2(radius * 1.25, height));
    pts.push(new Vector2(0.0001, height));
    return new LatheGeometry(pts, 18);
  }

  private clearStack() {
    this.root.children.slice().forEach(child => {
      this.root.remove(child);
      child.traverse(obj => this.disposeObject(obj));
    });
    this.stages = [];
    this.pickables = [];
  }

  private disposeObject(obj: Object3D) {
    const anyObj = obj as Object3D & {geometry?: BufferGeometry; material?: Material | Material[]};
    anyObj.geometry?.dispose?.();
    const mats = Array.isArray(anyObj.material) ? anyObj.material : anyObj.material ? [anyObj.material] : [];
    mats.forEach(m => {
      if (m !== this.outputMat && m !== this.torusMat) m.dispose();
    });
  }

  private buildStack(model: GeneratorModel, previous: Map<number, number>) {
    const max = Math.max(1, model.maxStages);
    const shadows = this.options.quality === 'high';
    this.stackHeight = PLINTH + max * PITCH + 0.6;
    // Shared geometries (disposed with the first owner; others reference)
    const deckGeo = new BoxGeometry(DECK_W, 0.05, DECK_D);
    const deckEdges = new EdgesGeometry(deckGeo);
    const capGeo = new BoxGeometry(1.2, 0.27, 0.58);
    const bandGeo = new BoxGeometry(1.22, 0.05, 0.6);
    // Illustrative spark between the gap spheres (unlit, additive, invisible at rest).
    const arcGeo = new CylinderGeometry(0.016, 0.016, PITCH * 0.36 - 0.15, 8);
    const haloGeo = new SphereGeometry(0.16, 16, 12);
    const postGeo = this.insulatorGeometry(PITCH - 0.05, 0.034, 3);
    const sphereGeo = new SphereGeometry(0.075, 20, 14);
    const rodGeo = new CylinderGeometry(0.036, 0.036, 1, 12);
    rodGeo.translate(0, 0.5, 0);

    // Plinth
    const plinth = new Mesh(new BoxGeometry(DECK_W + 0.6, PLINTH, DECK_D + 0.6), this.standard('#2b3740', 0.55, 0.55));
    plinth.position.y = PLINTH / 2;
    plinth.receiveShadow = shadows;
    plinth.castShadow = shadows;
    this.root.add(plinth);

    for (let i = 0; i < max; i++) {
      const state = model.stages[i] || 'inactive';
      const target = state === 'active' || state === 'shared' || state === 'added' ? 1 : 0;
      const level = previous.has(i) ? (previous.get(i) as number) : target;
      const group = new Group();
      group.position.y = PLINTH + i * PITCH;
      group.userData.stage = i;
      const materials: MeshStandardMaterial[] = [];
      const mat = (m: MeshStandardMaterial) => (materials.push(m), m);

      const deck = new Mesh(deckGeo, mat(this.standard(C.metal, 0.82, 0.34)));
      deck.position.y = 0.025;
      deck.castShadow = shadows;
      deck.receiveShadow = shadows;
      deck.userData.stage = i;
      group.add(deck);

      const ghostLines = new LineBasicMaterial({color: new Color(C.ghost), transparent: true, opacity: 0});
      const edges = new LineSegments(deckEdges, ghostLines);
      edges.position.y = 0.025;
      group.add(edges);

      const cap = new Mesh(capGeo, mat(this.standard(C.epoxy, 0.25, 0.55)));
      cap.position.set(-0.12, 0.05 + 0.135, -0.3);
      cap.castShadow = shadows;
      cap.userData.stage = i;
      group.add(cap);
      const band = new MeshStandardMaterial({color: new Color(C.bandIdle), emissive: new Color(C.band), emissiveIntensity: 0, metalness: 0.3, roughness: 0.4, transparent: true, opacity: 1});
      materials.push(band);
      const bandMesh = new Mesh(bandGeo, band);
      bandMesh.position.set(-0.12, 0.05 + 0.2, -0.3);
      bandMesh.userData.stage = i;
      group.add(bandMesh);

      const porcelain = mat(this.standard(C.porcelain, 0.05, 0.3));
      for (const [x, z] of [[-DECK_W / 2 + 0.14, -DECK_D / 2 + 0.14], [DECK_W / 2 - 0.14, -DECK_D / 2 + 0.14], [-DECK_W / 2 + 0.14, DECK_D / 2 - 0.14], [DECK_W / 2 - 0.14, DECK_D / 2 - 0.14]]) {
        const post = new Mesh(postGeo, porcelain);
        post.position.set(x, 0.05, z);
        post.castShadow = shadows;
        group.add(post);
      }

      // Sphere gap between this stage and the next (illustrative position)
      const sphere = new MeshStandardMaterial({color: new Color('#cfd8de'), metalness: 1, roughness: 0.16, emissive: new Color(C.spark), emissiveIntensity: 0, transparent: true, opacity: 1});
      materials.push(sphere);
      for (const y of [PITCH * 0.36, PITCH * 0.72]) {
        const s = new Mesh(sphereGeo, sphere);
        s.position.set(DECK_W / 2 - 0.42, y, DECK_D / 2 - 0.1);
        s.castShadow = shadows;
        group.add(s);
      }
      const arc = new MeshBasicMaterial({color: new Color('#e2dbff'), transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false});
      const arcMesh = new Mesh(arcGeo, arc);
      arcMesh.position.set(DECK_W / 2 - 0.42, PITCH * 0.54, DECK_D / 2 - 0.1);
      group.add(arcMesh);
      const haloMat = new MeshBasicMaterial({color: new Color('#8f7cff'), transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false});
      const halo = new Mesh(haloGeo, haloMat);
      halo.position.copy(arcMesh.position);
      group.add(halo);

      // Counted resistor banks (schematic arrangement of the saved network)
      this.addBank(group, model.front, 'front', i, state, rodGeo, materials, model);
      this.addBank(group, model.tail, 'tail', i, state, rodGeo, materials, model);

      this.root.add(group);
      const parts: StageParts = {group, level, from: level, target, state, materials, ghostLines, band, sphere, arc, halo: haloMat, pickables: [deck, cap, bandMesh], flash: 0, charge: 0};
      this.stages.push(parts);
      this.pickables.push(deck, cap, bandMesh);
    }

    // Top cap and grading torus at the top of the full stack
    const top = PLINTH + max * PITCH;
    const capDeck = new Mesh(new BoxGeometry(DECK_W, 0.05, DECK_D), this.standard(C.metal, 0.85, 0.3));
    capDeck.position.y = top + 0.025;
    capDeck.castShadow = shadows;
    this.root.add(capDeck);
    const torus = new Mesh(new TorusGeometry(1.05, 0.12, 20, 72), this.torusMat);
    torus.rotation.x = Math.PI / 2;
    torus.position.y = top + 0.32;
    torus.castShadow = shadows;
    this.root.add(torus);

    // Output lead from the top of the active stages to the divider (schematic)
    const activeTop = PLINTH + Math.max(1, model.activeStages) * PITCH;
    const dividerH = Math.max(2.4, top * 0.72);
    const curve = new CatmullRomCurve3([
      new Vector3(DECK_W / 2 - 0.05, activeTop - 0.05, 0),
      new Vector3(DECK_W / 2 + 0.6, activeTop + 0.1, 0.1),
      new Vector3((DECK_W / 2 + DIVIDER_X) / 2 + 0.2, Math.max(activeTop, dividerH) + 0.25, 0.2),
      new Vector3(DIVIDER_X, dividerH + 0.18, 0.3),
    ]);
    const lead = new Mesh(new TubeGeometry(curve, 64, 0.03, 8, false), this.outputMat);
    this.root.add(lead);

    // Divider column + test object (schematic; their capacitances are request inputs)
    const divider = new Mesh(this.insulatorGeometry(dividerH, 0.07, Math.max(6, Math.round(dividerH / 0.32))), this.standard(C.porcelain, 0.05, 0.3));
    divider.position.set(DIVIDER_X, 0, 0.3);
    divider.castShadow = shadows;
    this.root.add(divider);
    const dividerTop = new Mesh(new TorusGeometry(0.28, 0.06, 14, 40), this.torusMat);
    dividerTop.rotation.x = Math.PI / 2;
    dividerTop.position.set(DIVIDER_X, dividerH + 0.08, 0.3);
    this.root.add(dividerTop);
    const object = new Mesh(new CylinderGeometry(0.34, 0.42, 1.25, 28), this.standard('#c9d0d4', 0.15, 0.6));
    object.position.set(DIVIDER_X + 0.15, 0.625, -1.25);
    object.castShadow = shadows;
    object.receiveShadow = shadows;
    this.root.add(object);
    const objectLead = new Mesh(
      new TubeGeometry(new CatmullRomCurve3([new Vector3(DIVIDER_X, dividerH + 0.12, 0.3), new Vector3(DIVIDER_X + 0.1, dividerH * 0.72, -0.6), new Vector3(DIVIDER_X + 0.15, 1.26, -1.25)]), 40, 0.022, 8, false),
      this.outputMat,
    );
    this.root.add(objectLead);

    this.outputLight.position.set(DIVIDER_X - 0.8, Math.max(activeTop, dividerH) + 0.4, 0.8);
    this.updateStageVisuals();
  }

  private addBank(group: Group, net: NetworkModel, role: 'front' | 'tail', stage: number, state: StageState, rodGeo: CylinderGeometry, materials: MeshStandardMaterial[], model: GeneratorModel) {
    type Rod = {ohm: number; a0: number; a1: number; c: number; kind: 'keep' | 'added' | 'removed'};
    let rods: Rod[] = [];
    let lanes = 1;
    const transition = model.transition;
    if (transition && model.mode === 'transition') {
      const deltas: PartDelta[] = role === 'front' ? transition.front : transition.tail;
      // Per-stage counted parts: shared stages show retained/added/removed,
      // newly active stages show the target plan, deactivated stages the baseline plan.
      const list: {ohm: number; kind: Rod['kind']}[] = [];
      deltas.forEach(d => {
        const keep = state === 'shared' ? d.retained : state === 'added' ? 0 : state === 'removed' ? 0 : 0;
        const added = state === 'shared' ? d.added : state === 'added' ? d.after : 0;
        const removed = state === 'shared' ? d.removed : state === 'removed' ? d.before : 0;
        for (let k = 0; k < keep; k++) list.push({ohm: d.ohm, kind: 'keep'});
        for (let k = 0; k < added; k++) list.push({ohm: d.ohm, kind: 'added'});
        for (let k = 0; k < removed; k++) list.push({ohm: d.ohm, kind: 'removed'});
      });
      if (state === 'inactive') return;
      lanes = Math.max(1, list.length);
      rods = list.map((r, k) => ({ohm: r.ohm, a0: 0, a1: 1, c: k + 0.5, kind: r.kind}));
    } else if (net.tree) {
      const layout = layoutTree(net.tree);
      lanes = layout.width;
      rods = layout.leaves.map(l => ({...l, kind: 'keep'}));
    } else {
      // Topology text could not be verified: show the counted parts side by side, no wiring claim.
      const list = net.parts.flatMap(p => Array.from({length: p.perStage}, () => p.ohm));
      lanes = Math.max(1, list.length);
      rods = list.map((ohm, k) => ({ohm, a0: 0, a1: 1, c: k + 0.5, kind: 'keep'}));
    }
    if (!rods.length) return;
    const zSpan = Math.min(1.05, 0.16 * lanes + 0.06);
    const yBottom = 0.12, yTop = PITCH - 0.06;
    const x = role === 'front' ? -DECK_W / 2 + 0.36 : DECK_W / 2 - 0.36;
    const zCenter = role === 'front' ? 0.08 : -0.05;
    const material = new MeshStandardMaterial({color: '#ffffff', metalness: 0.25, roughness: 0.45, transparent: true, opacity: 1});
    materials.push(material);
    const mesh = new InstancedMesh(rodGeo, material, rods.length);
    const m = new Matrix4();
    const q = new Quaternion();
    const scale = new Vector3();
    const pos = new Vector3();
    rods.forEach((rod, k) => {
      const z = zCenter - zSpan / 2 + (rod.c / lanes) * zSpan;
      const y0 = yBottom + rod.a0 * (yTop - yBottom) + 0.012;
      const len = Math.max(0.03, (rod.a1 - rod.a0) * (yTop - yBottom) - 0.024);
      pos.set(x, y0, z);
      scale.set(rod.kind === 'removed' ? 0.8 : 1, len, rod.kind === 'removed' ? 0.8 : 1);
      m.compose(pos, q, scale);
      mesh.setMatrixAt(k, m);
      const color = rod.kind === 'added' ? new Color(C.added) : rod.kind === 'removed' ? new Color(C.removed) : new Color(model.mode === 'transition' ? KEPT_COLOR : valueColor(rod.ohm, net));
      mesh.setColorAt(k, color);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.castShadow = this.options.quality === 'high';
    mesh.userData.stage = stage;
    group.add(mesh);
    // Bus bars that tie the bank to the decks (schematic)
    const bus = new Mesh(new BoxGeometry(0.05, 0.02, zSpan + 0.06), this.standard(C.metalDark, 0.8, 0.35));
    bus.position.set(x, yBottom, zCenter);
    group.add(bus);
    const busTop = bus.clone();
    busTop.position.y = yTop;
    group.add(busTop);
    materials.push(bus.material as MeshStandardMaterial);
  }

  /* ---------------------------------------------------------------- */
  /* Camera                                                           */
  /* ---------------------------------------------------------------- */

  private computeFit() {
    const h = this.stackHeight + 0.6;
    const vFov = (this.camera.fov * Math.PI) / 180;
    const fitH = h / 2 / Math.tan(vFov / 2);
    const width = DIVIDER_X + DECK_W / 2 + 1.4;
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * this.camera.aspect);
    const fitW = width / 2 / Math.tan(hFov / 2);
    // Leave room for the overlay header and the control bar.
    this.fit = Math.max(fitH * 1.3, fitW * 1.08);
  }

  private applyView(view: SceneView, immediate: boolean) {
    const model = this.model;
    const active = model ? Math.max(1, model.activeStages) : 1;
    const activeTop = PLINTH + active * PITCH;
    const mid = PLINTH + (active * PITCH) / 2;
    const presets: Record<SceneView, {t: [number, number, number]; theta: number; phi: number; r: number}> = {
      overview: {t: [DIVIDER_X / 2 - 0.4, this.stackHeight * 0.46, 0], theta: 0.62, phi: 1.3, r: 1},
      stack: {t: [0, activeTop * 0.52, 0], theta: 0.42, phi: 1.3, r: 0.86},
      front: {t: [-DECK_W / 2, mid, 0.05], theta: -0.85, phi: 1.33, r: 0.5},
      tail: {t: [DECK_W / 2, mid, -0.05], theta: 1.45, phi: 1.33, r: 0.5},
      output: {t: [DIVIDER_X - 0.9, this.stackHeight * 0.5, 0], theta: 0.3, phi: 1.28, r: 0.8},
    };
    const p = presets[view];
    this.goalTarget.set(...p.t);
    this.goal = {theta: p.theta, phi: p.phi, radius: this.fit * p.r};
    if (immediate) {
      this.target.copy(this.goalTarget);
      this.theta = this.goal.theta;
      this.phi = this.goal.phi;
      this.radius = this.goal.radius;
    }
  }

  private updateCamera(dt: number): boolean {
    const lambda = this.quiet ? 1e6 : 5.5;
    this.theta = damp(this.theta, this.goal.theta, lambda, dt);
    this.phi = damp(this.phi, this.goal.phi, lambda, dt);
    this.radius = damp(this.radius, this.goal.radius, lambda, dt);
    this.target.x = damp(this.target.x, this.goalTarget.x, lambda, dt);
    this.target.y = damp(this.target.y, this.goalTarget.y, lambda, dt);
    this.target.z = damp(this.target.z, this.goalTarget.z, lambda, dt);
    const sp = Math.sin(this.phi);
    this.camera.position.set(this.target.x + this.radius * sp * Math.sin(this.theta), this.target.y + this.radius * Math.cos(this.phi), this.target.z + this.radius * sp * Math.cos(this.theta));
    this.camera.lookAt(this.target);
    const moving =
      Math.abs(this.theta - this.goal.theta) > 1e-4 ||
      Math.abs(this.phi - this.goal.phi) > 1e-4 ||
      Math.abs(this.radius - this.goal.radius) > 1e-3 ||
      this.target.distanceTo(this.goalTarget) > 1e-3;
    return moving;
  }

  /* ---------------------------------------------------------------- */
  /* Stage visuals & animation                                        */
  /* ---------------------------------------------------------------- */

  private updateStageVisuals() {
    this.stages.forEach((s, i) => {
      const lit = s.level;
      const ghost = 1 - lit;
      const highlight = i === this.selected ? 1 : i === this.hovered ? 0.6 : 0;
      s.materials.forEach(m => {
        m.opacity = 0.14 + 0.86 * lit;
        // Opaque when fully active avoids transparency sorting artefacts.
        const transparent = lit < 0.995;
        if (m.transparent !== transparent) {
          m.transparent = transparent;
          m.needsUpdate = true;
        }
        m.depthWrite = lit > 0.5;
      });
      s.ghostLines.opacity = 0.18 + ghost * 0.5 + highlight * 0.6;
      const stateColor = s.state === 'added' ? C.added : s.state === 'removed' ? C.removed : highlight ? '#ffffff' : C.ghost;
      s.ghostLines.color.set(stateColor);
      if (s.state === 'added' || s.state === 'removed') s.ghostLines.opacity = 0.95;
      const base = s.state === 'removed' ? C.removed : s.state === 'added' ? C.added : C.band;
      s.band.emissive.set(base);
      s.band.color.set(lit > 0.5 ? '#1b3a40' : C.bandIdle);
      s.band.emissiveIntensity = lit * (0.55 + highlight * 0.7) + s.charge * 2.2 + s.flash * 2.6;
      s.sphere.emissiveIntensity = s.flash * 4;
      s.arc.opacity = Math.min(1, s.flash * 0.9);
      s.halo.opacity = s.flash * 0.22;
    });
    const glow = this.pulse !== null ? this.pulse : this.outputGlow;
    this.outputMat.emissiveIntensity = 0.12 + glow * 1.6;
    this.torusMat.emissiveIntensity = glow * 0.55;
    this.outputLight.intensity = glow * 14;
  }

  private stepAnimation(now: number, dt: number): boolean {
    let animating = false;
    // Stage activation morph between candidates
    const k = this.quiet ? 1 : Math.min(1, (now - this.morph.start) / this.morph.duration);
    const eased = 1 - Math.pow(1 - k, 3);
    this.stages.forEach(s => {
      s.level = s.from + (s.target - s.from) * eased;
      if (k < 1 && s.from !== s.target) animating = true;
    });
    // Illustrative erection sequence
    if (this.sequence && this.model) {
      const t = (now - this.sequence.start) / 1000;
      const n = this.model.activeStages;
      this.stages.forEach((s, i) => {
        if (i >= n) {
          s.flash = 0;
          s.charge = 0;
          return;
        }
        const charge = Math.min(1, t / 0.35);
        const fire = 0.35 + i * 0.085;
        const since = t - fire;
        s.charge = since < 0 ? charge * 0.55 : Math.max(0, 0.55 * Math.exp(-since * 2.2));
        s.flash = since < 0 ? 0 : since < 0.06 ? since / 0.06 : Math.exp(-(since - 0.06) * 9);
      });
      const end = 0.35 + n * 0.085;
      const since = t - end;
      this.outputGlow = since < 0 ? 0 : since < 0.15 ? since / 0.15 : Math.max(0, Math.exp(-(since - 0.15) * 2.6));
      if (t > this.sequence.duration) {
        this.sequence = null;
        this.stages.forEach(s => ((s.flash = 0), (s.charge = 0)));
        this.outputGlow = 0;
        this.options.onSequence?.(false);
      } else animating = true;
    }
    this.updateStageVisuals();
    return animating;
  }

  /* ---------------------------------------------------------------- */
  /* Render loop (on demand)                                          */
  /* ---------------------------------------------------------------- */

  requestRender() {
    if (this.disposed || this.frame) return;
    this.frame = requestAnimationFrame(t => this.tick(t));
  }

  private tick(now: number) {
    this.frame = 0;
    if (this.disposed) return;
    if (!this.active || document.hidden) {
      this.lastTime = 0;
      return;
    }
    const dt = this.lastTime ? Math.min(0.12, (now - this.lastTime) / 1000) : 1 / 60;
    this.lastTime = now;
    const moving = this.updateCamera(dt);
    const animating = this.stepAnimation(now, dt);
    this.renderer.render(this.scene, this.camera);
    this.emitAnchors();
    if (moving || animating || this.dragging) this.requestRender();
    else this.lastTime = 0;
  }

  private project(v: Vector3): Anchor {
    const p = v.clone().project(this.camera);
    return {x: ((p.x + 1) / 2) * this.width, y: ((1 - p.y) / 2) * this.height, visible: p.z < 1 && p.x > -1.05 && p.x < 1.05 && p.y > -1.05 && p.y < 1.05};
  }

  private emitAnchors() {
    const model = this.model;
    if (!model) {
      this.options.onAnchors({});
      return;
    }
    const n = Math.max(1, model.activeStages);
    const rep = Math.max(0, Math.min(n - 1, Math.floor(n / 2)));
    const repY = PLINTH + rep * PITCH;
    const anchors: AnchorMap = {
      stack: this.project(new Vector3(-DECK_W / 2 - 0.1, PLINTH + n * PITCH, 0)),
      front: this.project(new Vector3(-DECK_W / 2 + 0.36, repY + PITCH * 0.5, 0.08)),
      tail: this.project(new Vector3(DECK_W / 2 - 0.36, repY + PITCH * 0.5, -0.05)),
      gap: this.project(new Vector3(DECK_W / 2 - 0.42, repY + PITCH * 0.54, DECK_D / 2 - 0.1)),
      output: this.project(new Vector3(DIVIDER_X, Math.max(2.4, (PLINTH + model.maxStages * PITCH) * 0.72) + 0.2, 0.3)),
    };
    if (model.activeStages < model.maxStages) anchors.ghost = this.project(new Vector3(-DECK_W / 2, PLINTH + (model.activeStages + 0.5) * PITCH, DECK_D / 2));
    if (this.selected !== null) anchors.selected = this.project(new Vector3(0, PLINTH + (this.selected + 0.5) * PITCH, DECK_D / 2));
    this.options.onAnchors(anchors);
  }

  /* ---------------------------------------------------------------- */
  /* Pointer interaction                                              */
  /* ---------------------------------------------------------------- */

  private on(target: EventTarget, type: string, fn: EventListener, opts?: AddEventListenerOptions) {
    target.addEventListener(type, fn, opts);
    this.listeners.push([target, type, fn]);
  }

  private bindEvents() {
    const el = this.canvas;
    this.on(el, 'webglcontextlost', e => {
      e.preventDefault();
      cancelAnimationFrame(this.frame);
      this.frame = 0;
      this.options.onContextLost();
    });
    this.on(el, 'pointerdown', e => {
      const ev = e as PointerEvent;
      el.setPointerCapture?.(ev.pointerId);
      this.pointers.set(ev.pointerId, {x: ev.clientX, y: ev.clientY});
      if (this.pointers.size === 1) this.dragging = {x: ev.clientX, y: ev.clientY, theta: this.goal.theta, phi: this.goal.phi, moved: false};
      if (this.pointers.size === 2) {
        const [a, b] = [...this.pointers.values()];
        this.pinch = {d: Math.hypot(a.x - b.x, a.y - b.y), radius: this.goal.radius};
        this.dragging = null;
      }
    });
    this.on(el, 'pointermove', e => {
      const ev = e as PointerEvent;
      if (this.pointers.has(ev.pointerId)) this.pointers.set(ev.pointerId, {x: ev.clientX, y: ev.clientY});
      if (this.pinch && this.pointers.size === 2) {
        const [a, b] = [...this.pointers.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        this.goal.radius = Math.min(this.fit * 1.9, Math.max(this.fit * 0.32, (this.pinch.radius * this.pinch.d) / Math.max(20, d)));
        this.requestRender();
        return;
      }
      if (this.dragging) {
        const dx = ev.clientX - this.dragging.x, dy = ev.clientY - this.dragging.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) this.dragging.moved = true;
        this.goal.theta = this.dragging.theta - dx * 0.008;
        this.goal.phi = Math.min(1.52, Math.max(0.42, this.dragging.phi - dy * 0.006));
        if (this.quiet) {
          this.theta = this.goal.theta;
          this.phi = this.goal.phi;
        }
        this.requestRender();
        return;
      }
      this.pick(ev, false);
    });
    const end = (e: Event) => {
      const ev = e as PointerEvent;
      const wasClick = this.dragging && !this.dragging.moved && this.pointers.size === 1;
      this.pointers.delete(ev.pointerId);
      if (this.pointers.size < 2) this.pinch = null;
      if (wasClick && e.type === 'pointerup') this.pick(ev, true);
      if (!this.pointers.size) this.dragging = null;
      this.requestRender();
    };
    this.on(el, 'pointerup', end);
    this.on(el, 'pointercancel', end);
    this.on(el, 'pointerleave', () => {
      if (this.hovered !== null) {
        this.hovered = null;
        this.options.onHover(null, 0, 0);
        this.updateStageVisuals();
        this.requestRender();
      }
    });
    this.on(
      el,
      'wheel',
      e => {
        const ev = e as WheelEvent;
        // Only zoom when the scene is focused or the modifier is held, so the page still scrolls.
        if (document.activeElement !== el && !ev.ctrlKey && !ev.metaKey) return;
        ev.preventDefault();
        this.zoom(Math.exp(ev.deltaY * 0.0012));
      },
      {passive: false},
    );
    this.on(el, 'dblclick', () => this.reset());
    this.on(document, 'visibilitychange', () => {
      if (!document.hidden) this.requestRender();
    });
  }

  private pick(ev: PointerEvent, select: boolean) {
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.set(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects(this.pickables, false)[0];
    const stage = hit ? (hit.object.userData.stage as number) : null;
    if (select) {
      this.selected = stage;
      this.options.onSelect(stage);
      this.updateStageVisuals();
      this.requestRender();
      return;
    }
    if (stage !== this.hovered) {
      this.hovered = stage;
      this.canvas.style.cursor = stage === null ? 'grab' : 'pointer';
      this.updateStageVisuals();
      this.requestRender();
    }
    this.options.onHover(stage, ev.clientX - rect.left, ev.clientY - rect.top);
  }
}
