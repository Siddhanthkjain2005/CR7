/**
 * Minimal type declarations for the vendored three.js r170 module
 * (three.module.min.js, MIT, see LICENSE). Only the API surface used by
 * components/generator/engine.ts is declared. The engine was also checked
 * against the full @types/three r170 declarations during the redesign.
 */
export type ColorRepresentation = Color | string | number;

export declare const ACESFilmicToneMapping: number;
export declare const AdditiveBlending: number;
export declare const PCFSoftShadowMap: number;
export declare const SRGBColorSpace: string;
export declare const BackSide: number;
export declare const DoubleSide: number;

export declare class Vector2 {
  constructor(x?: number, y?: number);
  x: number;
  y: number;
  set(x: number, y: number): this;
}

export declare class Vector3 {
  constructor(x?: number, y?: number, z?: number);
  x: number;
  y: number;
  z: number;
  set(x: number, y: number, z: number): this;
  copy(v: Vector3): this;
  clone(): Vector3;
  project(camera: Camera): this;
  distanceTo(v: Vector3): number;
}

export declare class Quaternion {
  constructor(x?: number, y?: number, z?: number, w?: number);
}

export declare class Euler {
  x: number;
  y: number;
  z: number;
}

export declare class Matrix4 {
  compose(position: Vector3, quaternion: Quaternion, scale: Vector3): this;
}

export declare class Color {
  constructor(color?: ColorRepresentation);
  set(color: ColorRepresentation): this;
  multiplyScalar(s: number): this;
}

export declare class Object3D {
  position: Vector3;
  rotation: Euler;
  userData: Record<string, any>;
  children: Object3D[];
  castShadow: boolean;
  receiveShadow: boolean;
  visible: boolean;
  add(...objects: Object3D[]): this;
  remove(...objects: Object3D[]): this;
  traverse(callback: (object: Object3D) => void): void;
  lookAt(x: number, y: number, z: number): void;
  lookAt(v: Vector3): void;
  clone(recursive?: boolean): this;
}

export declare class Group extends Object3D {}

export declare class Texture {
  dispose(): void;
}

export declare class BufferGeometry {
  dispose(): void;
  translate(x: number, y: number, z: number): this;
}
export declare class BoxGeometry extends BufferGeometry {
  constructor(width?: number, height?: number, depth?: number);
}
export declare class PlaneGeometry extends BufferGeometry {
  constructor(width?: number, height?: number);
}
export declare class SphereGeometry extends BufferGeometry {
  constructor(radius?: number, widthSegments?: number, heightSegments?: number);
}
export declare class CylinderGeometry extends BufferGeometry {
  constructor(radiusTop?: number, radiusBottom?: number, height?: number, radialSegments?: number);
}
export declare class TorusGeometry extends BufferGeometry {
  constructor(radius?: number, tube?: number, radialSegments?: number, tubularSegments?: number);
}
export declare class LatheGeometry extends BufferGeometry {
  constructor(points?: Vector2[], segments?: number);
}
export declare class EdgesGeometry extends BufferGeometry {
  constructor(geometry?: BufferGeometry);
}
export declare class Curve3 {}
export declare class CatmullRomCurve3 extends Curve3 {
  constructor(points?: Vector3[]);
}
export declare class TubeGeometry extends BufferGeometry {
  constructor(path?: Curve3, tubularSegments?: number, radius?: number, radialSegments?: number, closed?: boolean);
}

export interface MaterialParameters {
  color?: ColorRepresentation;
  blending?: number;
  transparent?: boolean;
  opacity?: number;
  side?: number;
  depthWrite?: boolean;
}
export declare class Material {
  opacity: number;
  transparent: boolean;
  depthWrite: boolean;
  set needsUpdate(value: boolean);
  dispose(): void;
}
export declare class MeshBasicMaterial extends Material {
  constructor(parameters?: MaterialParameters);
  color: Color;
}
export interface MeshStandardMaterialParameters extends MaterialParameters {
  metalness?: number;
  roughness?: number;
  emissive?: ColorRepresentation;
  emissiveIntensity?: number;
}
export declare class MeshStandardMaterial extends Material {
  constructor(parameters?: MeshStandardMaterialParameters);
  color: Color;
  emissive: Color;
  emissiveIntensity: number;
  metalness: number;
  roughness: number;
}
export declare class LineBasicMaterial extends Material {
  constructor(parameters?: MaterialParameters);
  color: Color;
}

export declare class Mesh<G extends BufferGeometry = BufferGeometry, M extends Material | Material[] = Material | Material[]> extends Object3D {
  constructor(geometry?: G, material?: M);
  geometry: G;
  material: M;
}
export declare class LineSegments<G extends BufferGeometry = BufferGeometry, M extends Material = Material> extends Object3D {
  constructor(geometry?: G, material?: M);
  geometry: G;
  material: M;
}
export declare class GridHelper extends LineSegments<BufferGeometry, LineBasicMaterial> {
  constructor(size?: number, divisions?: number, color1?: ColorRepresentation, color2?: ColorRepresentation);
}
export declare class BufferAttribute {
  needsUpdate: boolean;
}
export declare class InstancedMesh<G extends BufferGeometry = BufferGeometry, M extends Material = Material> extends Mesh<G, M> {
  constructor(geometry: G, material: M, count: number);
  instanceMatrix: BufferAttribute;
  instanceColor: BufferAttribute | null;
  setMatrixAt(index: number, matrix: Matrix4): void;
  setColorAt(index: number, color: Color): void;
}

export declare class Fog {
  constructor(color: ColorRepresentation, near?: number, far?: number);
}
export declare class Scene extends Object3D {
  background: Color | Texture | null;
  environment: Texture | null;
  fog: Fog | null;
}

export declare class Camera extends Object3D {}
export declare class PerspectiveCamera extends Camera {
  constructor(fov?: number, aspect?: number, near?: number, far?: number);
  fov: number;
  aspect: number;
  updateProjectionMatrix(): void;
}

export declare class Light extends Object3D {
  constructor(color?: ColorRepresentation, intensity?: number);
  intensity: number;
}
export declare class AmbientLight extends Light {}
export declare class HemisphereLight extends Light {
  constructor(skyColor?: ColorRepresentation, groundColor?: ColorRepresentation, intensity?: number);
}
export declare class PointLight extends Light {
  constructor(color?: ColorRepresentation, intensity?: number, distance?: number, decay?: number);
}
export declare class OrthographicCamera extends Camera {
  left: number;
  right: number;
  top: number;
  bottom: number;
  near: number;
  far: number;
}
export declare class DirectionalLightShadow {
  mapSize: Vector2;
  camera: OrthographicCamera;
  bias: number;
  normalBias: number;
}
export declare class DirectionalLight extends Light {
  shadow: DirectionalLightShadow;
}

export interface Intersection {
  distance: number;
  object: Object3D;
}
export declare class Raycaster {
  setFromCamera(coords: Vector2, camera: Camera): void;
  intersectObjects(objects: Object3D[], recursive?: boolean): Intersection[];
}

export interface WebGLRendererParameters {
  canvas?: HTMLCanvasElement;
  antialias?: boolean;
  alpha?: boolean;
  powerPreference?: 'high-performance' | 'low-power' | 'default';
}
export declare class WebGLRenderer {
  constructor(parameters?: WebGLRendererParameters);
  outputColorSpace: string;
  toneMapping: number;
  toneMappingExposure: number;
  shadowMap: {enabled: boolean; type: number};
  setPixelRatio(value: number): void;
  setClearColor(color: ColorRepresentation, alpha?: number): void;
  setSize(width: number, height: number, updateStyle?: boolean): void;
  render(scene: Object3D, camera: Camera): void;
  dispose(): void;
}
export declare class WebGLRenderTarget {
  texture: Texture;
  dispose(): void;
}
export declare class PMREMGenerator {
  constructor(renderer: WebGLRenderer);
  fromScene(scene: Scene, sigma?: number): WebGLRenderTarget;
  dispose(): void;
}
