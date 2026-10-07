// HZN-1 landing page: one 3D scene whose state is driven by scroll position.
// Each chapter (<section data-key>) has a keyframe; the scene holds a chapter's keyframe for most of its
// height and blends into the next one over its last stretch, then eases toward that target every frame.
import * as THREE from 'three';

const $ = id => document.getElementById(id);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = t => t * t * (3 - 2 * t);
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const coarse = matchMedia('(pointer: coarse)').matches;
const fmt = n => n.toLocaleString('en-US');
function rng(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const rand = rng(1090);

// ------------------------------------------------------------ chip data (same model as the chip explorer)
const D = 8, P = 12, GAP = 0.95, IN = 3.75;
const LAYERS = [
  { id: 'balls', name: 'Solder balls', real: '0.3 mm', h: .3, color: '#c9ced6', foot: P },
  { id: 'pkg', name: 'Package base', real: '0.4 mm', h: .45, color: '#12221e', foot: P },
  { id: 'sub', name: 'Silicon base', real: '300 µm', h: .55, color: '#4a5566', foot: D },
  { id: 'fe', name: 'Transistors', real: '0.15 µm', h: .07, color: '#d25a5a', foot: D },
  { id: 'li1', name: 'Local wiring', real: '0.1 µm', h: .035, color: '#a184ec', foot: D },
  { id: 'met1', name: 'Metal 1', real: '0.36 µm', h: .045, color: '#4f8df5', foot: D },
  { id: 'met2', name: 'Metal 2', real: '0.36 µm', h: .045, color: '#e070c8', foot: D },
  { id: 'met3', name: 'Metal 3', real: '0.85 µm', h: .06, color: '#3ccfb0', foot: D },
  { id: 'met4', name: 'Metal 4', real: '0.85 µm', h: .06, color: '#f0a24a', foot: D },
  { id: 'met5', name: 'Metal 5', real: '1.26 µm', h: .1, color: '#e8cf6a', foot: D },
  { id: 'lid', name: 'Lid', real: '0.3 mm', h: .28, color: '#9aa3ad', foot: P * .84 },
];
const BLOCKS = [
  { id: 'radio', name: 'Antenna input', x: [-3.55, -2.55], z: [-3.55, .6], color: '#a78bfa' },
  { id: 'dec', name: 'Message decoder', x: [-2.4, .4], z: [-3.55, -.4], color: '#7cc4ff' },
  { id: 'pos', name: 'Location calculator', x: [.55, 3.55], z: [-3.55, -1.6], color: '#4fd1c5' },
  { id: 'track', name: 'Aircraft memory', x: [.55, 3.55], z: [-1.45, 1], color: '#94a3b8' },
  { id: 'fuel', name: 'Fuel calculator', x: [-2.4, .4], z: [-.25, 3.55], color: '#f5b041' },
  { id: 'area', name: 'Area filter', x: [.55, 2.3], z: [1.15, 3.55], color: '#f472b6' },
  { id: 'out', name: 'Output', x: [2.45, 3.55], z: [1.15, 3.55], color: '#34d399' },
  { id: 'clk', name: 'Clock & control', x: [-3.55, -2.55], z: [.75, 3.55], color: '#cbd5e1' },
];
const WP = { padIn: [-4.35, -1.5], radio: [-3.05, -1.5], dec: [-1, -2], track: [2.05, -.2], fuel: [-1, 1.6], area: [1.42, 2.35], out: [3, 2.35], padOut: [4.35, 2.35] };
const PATH = ['padIn', 'radio', 'dec', 'track', 'fuel', 'area', 'out', 'padOut'];
// the example message: an identification broadcast from aircraft 4840D6, flight KLM1023
const STEPS = [
  { block: 'radio', wp: 1, title: 'A plane broadcasts', text: 'KLM1023 sends a 112-digit radio message on 1090 MHz. The antenna input samples it 2 million times a second.', hex: [0, 28] },
  { block: 'dec', wp: 2, title: 'Spotting the start', text: 'The decoder waits for the four-burst pattern every message starts with, then reads each burst as a 1 or a 0.', hex: [0, 2] },
  { block: 'dec', wp: 2, title: 'Checking for mistakes', text: 'The last 24 digits are a check code. The chip redoes the math; if it matches, the message arrived intact.', hex: [22, 28] },
  { block: 'track', wp: 3, title: 'Remembering the plane', text: 'Plane 4840D6 gets a row in the aircraft memory, one of 1,024. Its position and speed fill in as more messages arrive.', hex: [2, 8] },
  { block: 'fuel', wp: 4, title: 'Estimating fuel', text: 'Once a second the fuel calculator adds up what this aircraft type has burned so far, and what a battery twin would have left.', hex: [8, 22] },
  { block: 'out', wp: 7, title: 'Sending it out', text: 'If the plane is inside the area you picked, the output sends one line of text to Fuel Horizon, which draws it on the globe.', hex: null },
];
const HEX = '8D4840D6202CC371C32CE0576098';

// ------------------------------------------------------------ chapter keyframes
// cam/tgt: camera position and look-at point. lid: lid lifted away. ex: layers pulled apart. top: layers above the
// transistors fly off. blk: floorplan rooms. route: signal path. chip/globe: which object is on stage. sway: idle motion.
// bl / ll: room labels and layer labels.
const BASE = { cam: [17, 11.5, 19], tgt: [0, 1.1, 0], fov: 34, lid: 0, ex: 0, top: 0, blk: 0, route: 0, chip: 1, globe: 0, sway: 1, bl: 0, ll: 0, gspin: 0, shift: .2 };
const KEYS = {
  hero: {},
  lid: { cam: [11, 14, 13.5], tgt: [0, .9, 0], lid: 1, sway: .3 },
  floor: { cam: [.01, 20.5, 9.5], tgt: [0, 1.4, .35], lid: 1, blk: 1, sway: 0, bl: 1 },
  msg: { cam: [.01, 20.5, 10], tgt: [0, 1.4, .35], lid: 1, blk: 1, route: 1, sway: 0 },
  layers: { cam: [24, 12, 24], tgt: [0, 5, 0], ex: 1, sway: .25, ll: 1, shift: .1 },
  fe: { cam: [-8.2, 6.9, 3.4], tgt: [-1.6, 4.15, .3], fov: 30, ex: 1, top: 1, sway: 0 },
  globe: { cam: [0, 1.5, 25], tgt: [0, 0, 0], chip: 0, globe: 1, sway: 0, gspin: 1 },
  acc: { cam: [0, 1.5, 28], tgt: [0, 0, 0], chip: 0, globe: 1, sway: 0, gspin: 1 },
  outro: { cam: [0, 3, 32], tgt: [0, -2, 0], chip: 0, globe: .55, sway: 0, gspin: 1 },
};
for (const k in KEYS) KEYS[k] = { ...BASE, ...KEYS[k] };
const NUM = Object.keys(BASE);

// ------------------------------------------------------------ renderer + scene
const canvas = $('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = .95;
renderer.setClearColor('#04070b');
const scene = new THREE.Scene();
scene.fog = new THREE.Fog('#04070b', 40, 90);
const camera = new THREE.PerspectiveCamera(34, 1, .1, 300);
scene.add(new THREE.HemisphereLight(0xc4dcff, 0x0a0f16, 1.35));
const key = new THREE.DirectionalLight(0xffffff, 3.1); key.position.set(6, 14, 8); scene.add(key);
const fill = new THREE.DirectionalLight(0x9fc2ff, 1.6); fill.position.set(-9, 6, -5); scene.add(fill);
const rim = new THREE.DirectionalLight(0xffe2c0, 1.1); rim.position.set(2, -4, -10); scene.add(rim);

// soft floor glow under the chip
const glowTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d');
  const g = x.createRadialGradient(64, 64, 0, 64, 64, 64); g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(.3, 'rgba(255,255,255,.45)'); g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g; x.fillRect(0, 0, 128, 128); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
})();

// ------------------------------------------------------------ chip
const chip = new THREE.Group(); scene.add(chip);
const halo = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.MeshBasicMaterial({ map: glowTex, color: '#1d4a78', transparent: true, opacity: .55, depthWrite: false, blending: THREE.AdditiveBlending }));
halo.rotation.x = -Math.PI / 2; halo.position.y = -.05; chip.add(halo);

const unitBox = new THREE.BoxGeometry(1, 1, 1);
const m4 = new THREE.Matrix4(), q0 = new THREE.Quaternion(), v3 = new THREE.Vector3(), s3 = new THREE.Vector3();
function boxes(list, material) {
  const mesh = new THREE.InstancedMesh(unitBox, material, list.length);
  list.forEach((b, i) => { m4.compose(v3.set(b[0], b[1], b[2]), q0, s3.set(b[3], b[4], b[5])); mesh.setMatrixAt(i, m4); });
  mesh.instanceMatrix.needsUpdate = true; return mesh;
}
const atY = (mesh, y) => { mesh.position.y = y; return mesh; };
const metal = (c, r = .38, m = .45) => new THREE.MeshStandardMaterial({ color: c, metalness: Math.min(m, .5), roughness: Math.max(r, .3) });
function segs(dir, count, minL, maxL, width, h, pitch) {
  const out = []; const tracks = Math.floor(2 * IN / pitch);
  for (let t = 0; t < tracks; t++) {
    const c = -IN + pitch * (t + .5); let s = -IN + rand() * .6;
    while (s < IN && out.length < count) {
      const L = Math.min(lerp(minL, maxL, rand()), IN - s);
      if (L > .05) out.push(dir === 'x' ? [s + L / 2, h / 2, c, L, h, width] : [c, h / 2, s + L / 2, width, h, L]);
      s += L + lerp(.05, .5, rand());
    }
  }
  return out;
}
const layerObjs = [];
LAYERS.forEach(L => {
  const g = new THREE.Group(); const h = L.h;
  if (L.id === 'balls') {
    const n = 12, sp = .9; const mesh = new THREE.InstancedMesh(new THREE.SphereGeometry(.17, 18, 12), metal(L.color, .22, 1), n * n); let i = 0;
    for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) { m4.makeTranslation((a - (n - 1) / 2) * sp, h / 2, (b - (n - 1) / 2) * sp); mesh.setMatrixAt(i++, m4); } g.add(mesh);
  }
  if (L.id === 'pkg') {
    g.add(atY(new THREE.Mesh(new THREE.BoxGeometry(P, h, P), new THREE.MeshStandardMaterial({ color: L.color, roughness: .75, metalness: .1 })), h / 2));
    const pads = [], gold = metal('#d4a94c', .25, 1);
    for (let i = 0; i < 14; i++) { const t = -4.2 + i * .65; pads.push([t, h + .01, -5, .28, .02, .16], [t, h + .01, 5, .28, .02, .16], [-5, h + .01, t, .16, .02, .28], [5, h + .01, t, .16, .02, .28]); }
    g.add(boxes(pads, gold));
  }
  if (L.id === 'sub') g.add(atY(new THREE.Mesh(new THREE.BoxGeometry(D, h, D), new THREE.MeshStandardMaterial({ color: L.color, roughness: .4, metalness: .4 })), h / 2));
  if (L.id === 'fe') {
    g.add(atY(new THREE.Mesh(new THREE.BoxGeometry(D - .1, .012, D - .1), new THREE.MeshStandardMaterial({ color: '#1b2028', roughness: .6 })), .006));
    const diff = [], poly = [], rowH = .16;
    for (let z = -IN + rowH / 2; z < IN; z += rowH) {
      let x = -IN;
      while (x < IN) {
        const w = lerp(.25, .9, rand()); diff.push([x + w / 2, .02, z - .035, w, .02, .03], [x + w / 2, .02, z + .035, w, .02, .03]);
        for (let px = x + .04; px < x + w - .02; px += lerp(.06, .11, rand())) poly.push([px, .045, z, .018, .025, .12]);
        x += w + .04;
      }
    }
    g.add(boxes(diff, new THREE.MeshStandardMaterial({ color: '#3f9c66', roughness: .5, metalness: .2 }))); g.add(boxes(poly, metal(L.color, .4, .3)));
  }
  if (L.id === 'li1') {
    const list = [];
    for (let i = 0; i < 900; i++) { const along = rand() < .5, l = lerp(.05, .16, rand()); const x = lerp(-IN, IN, rand()), z = lerp(-IN, IN, rand()); list.push(along ? [x, h / 2, z, l, h, .025] : [x, h / 2, z, .025, h, l]); }
    g.add(boxes(list, metal(L.color, .35, .6)));
  }
  if (L.id === 'met1') g.add(boxes(segs('x', 1100, .2, 1.1, .03, h, .055), metal(L.color)));
  if (L.id === 'met2') g.add(boxes(segs('z', 900, .3, 1.8, .03, h, .07), metal(L.color)));
  if (L.id === 'met3') g.add(boxes(segs('x', 260, .8, 3.6, .06, h, .2), metal(L.color)));
  if (L.id === 'met4') { const l = segs('z', 140, 1.4, 6, .07, h, .32); for (let x = -IN + .5; x < IN; x += 1) l.push([x, h / 2, 0, .16, h, 2 * IN]); g.add(boxes(l, metal(L.color))); }
  if (L.id === 'met5') {
    const l = []; for (let z = -IN + .45; z < IN; z += .9) l.push([0, h / 2, z, 2 * IN, h, .3]);
    for (let i = 0; i < 12; i++) { const t = -3.5 + i * (7 / 11); l.push([t, h / 2, -3.88, .3, h, .22], [t, h / 2, 3.88, .3, h, .22], [-3.88, h / 2, t, .22, h, .3], [3.88, h / 2, t, .22, h, .3]); }
    g.add(boxes(l, metal(L.color, .28, .9)));
  }
  if (L.id === 'lid') {
    const c = document.createElement('canvas'); c.width = c.height = 1024; const x = c.getContext('2d');
    x.fillStyle = '#9aa3ad'; x.fillRect(0, 0, 1024, 1024);
    for (let i = 0; i < 4000; i++) { x.fillStyle = 'rgba(255,255,255,' + (rand() * .05) + ')'; x.fillRect(rand() * 1024, rand() * 1024, rand() * 80, 1); }
    x.fillStyle = '#5d6670'; x.textAlign = 'center'; x.font = '600 150px Geist, Helvetica, sans-serif'; x.fillText('HZN-1', 512, 470);
    x.font = '500 46px Geist Mono, Menlo, monospace'; x.fillText('FUEL HORIZON · SKY130', 512, 570); x.fillText('ADS-B EDGE PROCESSOR', 512, 630);
    x.beginPath(); x.arc(120, 120, 34, 0, 7); x.fill();
    const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
    const side = new THREE.MeshStandardMaterial({ color: L.color, metalness: .45, roughness: .42, transparent: true });
    const topM = new THREE.MeshStandardMaterial({ map: tex, metalness: .4, roughness: .5, transparent: true });
    g.add(atY(new THREE.Mesh(new THREE.BoxGeometry(L.foot, h, L.foot), [side, side, topM, side, side, side]), h / 2));
    // side walls down to the package, so the closed chip reads as one sealed part
    const wall = .965, t = .22, f = L.foot;
    for (const [x, z, w, d] of [[0, f / 2 - t / 2, f, t], [0, -f / 2 + t / 2, f, t], [f / 2 - t / 2, 0, t, f - 2 * t], [-f / 2 + t / 2, 0, t, f - 2 * t]]) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, wall, d), side); m.position.set(x, -wall / 2, z); g.add(m);
    }
    L.mats = [side, topM];
    // repaint once the web font has loaded so the engraving uses it
    document.fonts?.ready.then(() => { x.fillStyle = '#9aa3ad'; x.fillRect(200, 330, 624, 330); x.fillStyle = '#5d6670'; x.font = '600 150px Geist, Helvetica, sans-serif'; x.fillText('HZN-1', 512, 470);
      x.font = '500 46px Geist Mono, Menlo, monospace'; x.fillText('FUEL HORIZON · SKY130', 512, 570); x.fillText('ADS-B EDGE PROCESSOR', 512, 630); tex.needsUpdate = true; });
  }
  chip.add(g); layerObjs.push({ L, g });
});
let acc = 0; LAYERS.forEach(L => { L.base = acc; acc += L.h; });
const idx = id => LAYERS.findIndex(L => L.id === id);
const FE = idx('fe'), LID = idx('lid'), MET5 = idx('met5');
const DIE_TOP = LAYERS[MET5].base + LAYERS[MET5].h;

const viaGaps = [];
['fe', 'li1', 'met1', 'met2', 'met3', 'met4'].forEach(id => {
  const n = 110, mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1).translate(0, .5, 0), metal('#b7bec8', .3, 1), n);
  for (let i = 0; i < n; i++) { m4.compose(v3.set(lerp(-IN, IN, rand()), 0, lerp(-IN, IN, rand())), q0, s3.set(.03, 1, .03)); mesh.setMatrixAt(i, m4); }
  chip.add(mesh); viaGaps.push({ lower: idx(id), mesh });
});

const wires = new THREE.Group(); chip.add(wires);
{
  const gold = metal('#e0b65a', .25, 1);
  const drop = (LAYERS[idx('pkg')].base + LAYERS[idx('pkg')].h) - DIE_TOP;
  for (let i = 0; i < 12; i++) {
    const t = -3.5 + i * (7 / 11);
    [[t, -3.88, t * 1.18, -5], [t, 3.88, t * 1.18, 5], [-3.88, t, -5, t * 1.18], [3.88, t, 5, t * 1.18]].forEach(([x0, z0, x1, z1]) => {
      const c = new THREE.CubicBezierCurve3(new THREE.Vector3(x0, 0, z0), new THREE.Vector3(x0 + (x1 - x0) * .2, .9, z0 + (z1 - z0) * .2), new THREE.Vector3(x1 - (x1 - x0) * .2, .6, z1 - (z1 - z0) * .2), new THREE.Vector3(x1, drop + .02, z1));
      wires.add(new THREE.Mesh(new THREE.TubeGeometry(c, 24, .012, 5, false), gold));
    });
  }
  wires.position.y = DIE_TOP;
}

// floorplan rooms
const blockGroup = new THREE.Group(); blockGroup.position.y = DIE_TOP + .01; chip.add(blockGroup);
const blockObjs = BLOCKS.map(B => {
  const w = B.x[1] - B.x[0], d = B.z[1] - B.z[0], cx = (B.x[0] + B.x[1]) / 2, cz = (B.z[0] + B.z[1]) / 2;
  const mat = new THREE.MeshBasicMaterial({ color: B.color, transparent: true, opacity: 0, toneMapped: false });
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w - .06, .14, d - .06), mat); mesh.position.set(cx, .07, cz);
  const edge = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry), new THREE.LineBasicMaterial({ color: B.color, transparent: true, opacity: 0 })); edge.position.copy(mesh.position);
  blockGroup.add(mesh, edge);
  return { B, mesh, mat, edge, center: new THREE.Vector3(cx, 0, cz) };
});

// signal path and the travelling pulse
const routeGroup = new THREE.Group(); routeGroup.position.y = DIE_TOP + .34; chip.add(routeGroup);
const routePts = [];
for (let i = 0; i < PATH.length; i++) {
  const p = WP[PATH[i]];
  if (i) { const a = WP[PATH[i - 1]]; if (a[0] !== p[0] && a[1] !== p[1]) routePts.push([p[0], a[1]]); }
  routePts.push(p);
}
const wpIndex = PATH.map(k => routePts.findIndex(p => p === WP[k]));
const cum = [0]; for (let i = 1; i < routePts.length; i++) cum.push(cum[i - 1] + Math.hypot(routePts[i][0] - routePts[i - 1][0], routePts[i][1] - routePts[i - 1][1]));
const routeMat = new THREE.LineBasicMaterial({ color: '#7cc4ff', transparent: true, opacity: 0 });
routeGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(routePts.map(p => new THREE.Vector3(p[0], 0, p[1]))), routeMat));
const pulseMat = new THREE.SpriteMaterial({ map: glowTex, color: '#9fd4ff', transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending });
const pulse = new THREE.Sprite(pulseMat); pulse.scale.set(1.3, 1.3, 1.3); routeGroup.add(pulse);
const TRAIL = 40, trailPos = new Float32Array(TRAIL * 3), trailCol = new Float32Array(TRAIL * 3);
for (let i = 0; i < TRAIL; i++) { const k = Math.pow(1 - i / TRAIL, 1.5); trailCol.set([.49 * k, .77 * k, k], i * 3); }
const trailGeo = new THREE.BufferGeometry(); trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPos, 3)); trailGeo.setAttribute('color', new THREE.BufferAttribute(trailCol, 3));
const trailMat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
routeGroup.add(new THREE.Line(trailGeo, trailMat));
function pathAt(dist, out) {
  dist = clamp(dist, 0, cum[cum.length - 1]); let i = 1; while (i < cum.length - 1 && cum[i] < dist) i++;
  const t = (dist - cum[i - 1]) / Math.max(cum[i] - cum[i - 1], 1e-6);
  out[0] = lerp(routePts[i - 1][0], routePts[i][0], t); out[1] = lerp(routePts[i - 1][1], routePts[i][1], t); return out;
}

// ------------------------------------------------------------ globe of recorded flights
const R = 4.6;
const globe = new THREE.Group(); globe.rotation.set(.5, 1.25, 0); scene.add(globe); globe.visible = false;
const globeMats = [];
const core = new THREE.Mesh(new THREE.SphereGeometry(R * .995, 64, 48), new THREE.MeshBasicMaterial({ color: '#07111c', transparent: true }));
globe.add(core); globeMats.push([core.material, 1]);
const atmo = new THREE.Mesh(new THREE.SphereGeometry(R * 1.18, 64, 48), new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, side: THREE.BackSide, blending: THREE.AdditiveBlending,
  uniforms: { uOpacity: { value: 0 }, uColor: { value: new THREE.Color('#3f8fd6') } },
  vertexShader: 'varying vec3 vN;varying vec3 vP;void main(){vN=normalize(normalMatrix*normal);vec4 p=modelViewMatrix*vec4(position,1.);vP=p.xyz;gl_Position=projectionMatrix*p;}',
  fragmentShader: 'uniform float uOpacity;uniform vec3 uColor;varying vec3 vN;varying vec3 vP;void main(){float f=pow(clamp(1.0-abs(dot(normalize(-vP),vN)),0.,1.),2.2);float k=smoothstep(0.0,1.0,f)*(1.0-smoothstep(.55,1.,f));gl_FragColor=vec4(uColor,k*uOpacity*1.4);}',
}));
scene.add(atmo); atmo.visible = false;
const ll2v = (lat, lon, r, out, i) => { const a = lat * Math.PI / 180, b = lon * Math.PI / 180; out[i] = r * Math.cos(a) * Math.sin(b); out[i + 1] = r * Math.sin(a); out[i + 2] = r * Math.cos(a) * Math.cos(b); };
const dotTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'); x.fillStyle = '#fff'; x.beginPath(); x.arc(32, 32, 26, 0, 7); x.fill(); return new THREE.CanvasTexture(c); })();
let flightCount = 0;
// dots keep a fixed on-screen size that scales with the window, so they never shrink below a pixel
const pointMats = {};
function sizePoints() {
  const k = clamp(Math.min(innerWidth, innerHeight * 1.4) / 900, .7, 1.5);
  if (pointMats.land) pointMats.land.size = 2.1 * k;
  if (pointMats.flights) pointMats.flights.size = 3.2 * k;
}
fetch('assets/globe-points.json').then(r => r.json()).then(G => {
  const land = new Float32Array(G.land.length / 2 * 3);
  for (let i = 0, j = 0; i < G.land.length; i += 2, j += 3) ll2v(G.land[i], G.land[i + 1], R, land, j);
  const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.BufferAttribute(land, 3));
  const lm = new THREE.PointsMaterial({ size: 2, color: '#4f7aa8', map: dotTex, alphaTest: .4, transparent: true, sizeAttenuation: false, toneMapped: false });
  pointMats.land = lm;
  globe.add(new THREE.Points(lg, lm)); globeMats.push([lm, 1]);
  const n = G.flights.length / 3, fp = new Float32Array(n * 3), fc = new Float32Array(n * 3);
  const LO = [1, .42, .42], MID = [.96, .69, .25], HI = [.31, .82, .77], DIM = [.55, .62, .72];
  for (let i = 0; i < n; i++) {
    const lat = G.flights[i * 3], lon = G.flights[i * 3 + 1], f = G.flights[i * 3 + 2];
    ll2v(lat, lon, R * 1.012, fp, i * 3);
    let c = DIM; if (f >= 0) { const t = clamp(f, 0, 1); const [a, b, k] = t < .5 ? [LO, MID, t / .5] : [MID, HI, (t - .5) / .5]; c = [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)]; }
    fc.set(f >= 0 ? c : c.map(v => v * .55), i * 3);
  }
  const fg = new THREE.BufferGeometry(); fg.setAttribute('position', new THREE.BufferAttribute(fp, 3)); fg.setAttribute('color', new THREE.BufferAttribute(fc, 3));
  const fm = new THREE.PointsMaterial({ size: 3, vertexColors: true, map: dotTex, alphaTest: .3, transparent: true, sizeAttenuation: false, toneMapped: false });
  pointMats.flights = fm; sizePoints();
  globe.add(new THREE.Points(fg, fm)); globeMats.push([fm, 1]);
  flightCount = G.n;
  const when = new Date(G.t * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' });
  const mins = Math.max(0, Math.round((Date.now() / 1000 - G.t) / 60));
  const ago = mins < 2 ? 'just now' : mins < 90 ? mins + ' min ago' : mins < 48 * 60 ? Math.round(mins / 60) + ' h ago' : 'on ' + when;
  $('globeStats').innerHTML = '<div class="stat" title="' + when + '"><b>' + fmt(G.n) + '</b><span>Flights in the air, recorded ' + ago + '</span></div>' +
    '<div class="stat"><b>' + fmt(G.modelled) + '</b><span>Modelled by exact aircraft type</span></div>';
}).catch(() => { $('globeStats').innerHTML = ''; });

// ------------------------------------------------------------ HTML overlays: room labels, layer labels, legend, steps
const labelsEl = $('labels');
const mkLabel = (html, cls) => { const d = document.createElement('div'); d.className = 'lbl ' + (cls || ''); d.innerHTML = html; labelsEl.appendChild(d); return d; };
blockObjs.forEach(o => { o.label = mkLabel('<i style="background:' + o.B.color + '"></i>' + o.B.name); });
layerObjs.forEach(o => { o.label = mkLabel('<span style="color:var(--ink)">' + o.L.name + '</span><span>' + o.L.real + '</span>', 'layer'); });
$('legend').innerHTML = BLOCKS.map(B => '<li><i style="background:' + B.color + '"></i>' + B.name + '</li>').join('');
$('steps').innerHTML = STEPS.map(s => '<li><b>' + s.title + '</b><span>' + s.text + '</span></li>').join('');
const stepEls = [...$('steps').children];
let shownStep = -1;
function showStep(i) {
  if (i === shownStep) return; shownStep = i;
  stepEls.forEach((el, j) => el.classList.toggle('on', j === i));
  const h = i >= 0 ? STEPS[i].hex : null; let s = '';
  for (let k = 0; k < HEX.length; k++) { const on = h && k >= h[0] && k < h[1]; if (k === 2 || k === 8 || k === 22) s += ' '; s += on ? '<b>' + HEX[k] + '</b>' : HEX[k]; }
  $('hex').innerHTML = s;
}
showStep(0);

// ------------------------------------------------------------ chapters, rail, progress
const sections = [...document.querySelectorAll('section[data-key]')];
const rail = $('rail');
rail.innerHTML = sections.map((s, i) => '<button type="button" data-i="' + i + '" aria-label="Go to ' + s.dataset.name + '"><span>' + s.dataset.name + '</span><i></i></button>').join('');
const railBtns = [...rail.children];
railBtns.forEach(b => b.addEventListener('click', () => sections[+b.dataset.i].scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' })));
// on touch screens, tapping empty space moves on to the next reveal
// drag anywhere outside the copy to spin the chip (or the globe); a flick keeps it turning for a moment
const mainEl = document.querySelector('main');
const NO_DRAG = 'a,button,input,.copy,.cards,footer';
const TURN = Math.PI * 2;
let dragging = false, dragX = 0, dragT = 0, dragMoved = 0, yawVel = 0, spinDelta = 0, userYaw = 0, idle = 0;
mainEl.addEventListener('pointerdown', e => {
  if (e.button !== 0 || e.target.closest(NO_DRAG)) return;
  dragging = true; dragMoved = 0; dragX = e.clientX; dragT = performance.now(); yawVel = 0;
  document.body.classList.add('dragging');
});
addEventListener('pointermove', e => {
  if (!dragging) return;
  const now = performance.now(), dx = e.clientX - dragX, a = dx * 7 / Math.max(innerWidth, 400);
  dragMoved += Math.abs(dx); spinDelta += a; idle = 0;
  const v = a / Math.max((now - dragT) / 1000, 1 / 240);
  yawVel = lerp(yawVel, v, .5); dragX = e.clientX; dragT = now;
});
const endDrag = () => {
  if (!dragging) return; dragging = false; document.body.classList.remove('dragging');
  if (reduce || performance.now() - dragT > 90) yawVel = 0; // a drag that stopped before release doesn't fling
  yawVel = clamp(yawVel, -9, 9);
};
addEventListener('pointerup', endDrag); addEventListener('pointercancel', endDrag);
// a sideways two-finger trackpad swipe spins it too (and doesn't trigger the browser's back gesture)
addEventListener('wheel', e => {
  if (Math.abs(e.deltaX) <= Math.abs(e.deltaY) * 1.2 || e.target.closest?.('.table-wrap')) return;
  e.preventDefault();
  spinDelta -= e.deltaX * 3.5 / Math.max(innerWidth, 400); yawVel = 0; idle = 0;
}, { passive: false });
function spin(dt) {
  if (!dragging) { spinDelta += yawVel * dt; yawVel *= Math.exp(-dt * 2.4); if (Math.abs(yawVel) < .02) yawVel = 0; }
  userYaw += spinDelta; globe.rotation.y += spinDelta; spinDelta = 0;
  // after a pause, drift back to the nearest whole turn so each chapter's view lines up again
  if (!dragging && !yawVel && (idle += dt) > 2.5) userYaw = lerp(userYaw, Math.round(userYaw / TURN) * TURN, reduce ? 1 : 1 - Math.exp(-dt * 1.4));
}

if (coarse) mainEl.addEventListener('click', e => {
  if (dragMoved > 8 || e.target.closest('a,button,.copy,.cards,footer')) return;
  scrollBy({ top: innerHeight * .8, behavior: reduce ? 'auto' : 'smooth' });
});

function target() {
  const vh = innerHeight, mid = scrollY + vh * .5;
  let i = 0; while (i < sections.length - 1 && sections[i + 1].offsetTop <= mid) i++;
  const s = sections[i], frac = clamp((mid - s.offsetTop) / s.offsetHeight, 0, 1);
  const A = KEYS[s.dataset.key], B = KEYS[(sections[i + 1] || s).dataset.key];
  const blend = smooth(clamp((frac - .62) / .38, 0, 1));
  const t = {};
  for (const k of NUM) t[k] = Array.isArray(A[k]) ? A[k].map((v, j) => lerp(v, B[k][j], blend)) : lerp(A[k], B[k], blend);
  // message chapter: scroll scrubs the pulse along the path
  const mi = sections.findIndex(x => x.dataset.key === 'msg');
  t.msg = i < mi ? 0 : i > mi ? 1 : clamp((frac - .06) / .8, 0, 1);
  t.chapter = i;
  const max = document.documentElement.scrollHeight - vh;
  t.progress = max > 0 ? scrollY / max : 0;
  return t;
}

// ------------------------------------------------------------ frame loop
const cur = target();
const camPos = new THREE.Vector3(), camTgt = new THREE.Vector3(), tmp = new THREE.Vector3(), p2 = [0, 0];
let last = performance.now(), time = 0, curChapter = -1, msgEased = cur.msg;
function layout() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h;
  applyShift(true); sizePoints();
}
// move the subject out from under the copy: right of it on wide screens, above it on phones
let shiftNow = -1;
function applyShift(force) {
  const w = innerWidth, h = innerHeight, narrow = w <= 760 || w / h < .8, s = narrow ? .17 : (cur?.shift ?? .2);
  if (!force && Math.abs(s - shiftNow) < .001) return; shiftNow = s;
  if (narrow) camera.setViewOffset(w, h, 0, h * s, w, h); else camera.setViewOffset(w, h, -w * s, 0, w, h);
  camera.updateProjectionMatrix();
}
layout(); addEventListener('resize', layout);
const fitScale = () => { const a = innerWidth / innerHeight; return a < 1 ? Math.min(2.2, 1.05 / a) : a < 1.3 ? 1.15 : 1; };
const labelPos = (v, el, alpha) => {
  if (alpha < .02) { if (el.style.opacity !== '0') el.style.opacity = '0'; return; }
  v.project(camera);
  if (v.z > 1) { el.style.opacity = '0'; return; }
  const x = (v.x * .5 + .5) * innerWidth, y = (-v.y * .5 + .5) * innerHeight;
  el.style.transform = 'translate(' + Math.round(x) + 'px,' + Math.round(y) + 'px) translate(-50%,-50%)';
  el.style.opacity = alpha.toFixed(2);
};

function frame(now) {
  requestAnimationFrame(frame);
  if (document.hidden) { last = now; return; }
  tick(now);
}
function tick(now) {
  const dt = Math.min(.05, (now - last) / 1000); last = now; time += dt;
  const t = target(), k = reduce ? 1 : 1 - Math.exp(-dt * 5.5);
  for (const n of NUM) cur[n] = Array.isArray(t[n]) ? cur[n].map((v, j) => lerp(v, t[n][j], k)) : lerp(cur[n], t[n], k);
  msgEased = lerp(msgEased, t.msg, reduce ? 1 : 1 - Math.exp(-dt * 7));
  $('bar').style.transform = 'scaleX(' + t.progress.toFixed(4) + ')';
  if (t.chapter !== curChapter) { curChapter = t.chapter; railBtns.forEach((b, i) => b.setAttribute('aria-current', i === curChapter)); }

  // chip
  chip.visible = cur.chip > .01;
  const cs = .0001 + smooth(clamp(cur.chip, 0, 1)) * .9999; chip.scale.setScalar(cs);
  spin(dt);
  chip.rotation.y = Math.sin(time * .32) * .45 * cur.sway + userYaw;
  chip.position.y = Math.sin(time * .8) * .08 * cur.sway;
  const ys = LAYERS.map((L, i) => L.base + i * GAP * cur.ex + (i > FE ? cur.top * (6 + (i - FE) * 1.6) : 0) + (i === LID ? cur.lid * 5 : 0));
  layerObjs.forEach((o, i) => { o.g.position.y = ys[i]; });
  const lidA = 1 - smooth(clamp(cur.lid * 1.4, 0, 1));
  LAYERS[LID].mats.forEach(m => { m.opacity = lidA; m.depthWrite = lidA > .98; });
  layerObjs[LID].g.visible = lidA > .01;
  viaGaps.forEach(v => {
    const L = LAYERS[v.lower], bottom = ys[v.lower] + L.h, top = ys[v.lower + 1], gap = top - bottom;
    v.mesh.visible = gap > .03 && !(v.lower >= FE && cur.top > .05);
    v.mesh.position.y = bottom; v.mesh.scale.y = Math.max(gap, .001);
  });
  wires.visible = cur.ex < .04 && cur.lid > .12; wires.position.y = ys[MET5] + LAYERS[MET5].h;
  halo.material.opacity = .5 * (1 - cur.top);

  // rooms: during the message chapter the room the pulse is in lights up and the rest dim
  const step = cur.route > .5 ? Math.min(STEPS.length - 1, Math.floor(msgEased * STEPS.length * .9999)) : -1;
  if (sections[curChapter]?.dataset.key === 'msg' || cur.route > .5) showStep(Math.max(step, 0));
  blockObjs.forEach(o => {
    const focus = step < 0 ? 1 : (STEPS[step].block === o.B.id ? 1 : .32);
    o.mat.opacity = .9 * cur.blk * focus; o.edge.material.opacity = cur.blk * (step < 0 ? 1 : focus * .9 + .1);
    o.mesh.scale.y = .05 + .95 * cur.blk; o.mesh.position.y = .07 * cur.blk;
    o.mesh.visible = o.edge.visible = cur.blk > .01;
  });
  // pulse position along the path, moving between waypoints in the first part of each step
  routeMat.opacity = .45 * cur.route; pulseMat.opacity = cur.route; trailMat.opacity = cur.route;
  if (cur.route > .01) {
    const sIdx = Math.min(STEPS.length - 1, Math.floor(msgEased * STEPS.length)), within = clamp(msgEased * STEPS.length - sIdx, 0, 1);
    const from = sIdx ? cum[wpIndex[STEPS[sIdx - 1].wp]] : 0, to = cum[wpIndex[STEPS[sIdx].wp]];
    const head = lerp(from, to, smooth(clamp(within / .55, 0, 1)));
    pathAt(head, p2); pulse.position.set(p2[0], 0, p2[1]);
    pulse.scale.setScalar(1.1 + Math.sin(time * 6) * .15);
    for (let i = 0; i < TRAIL; i++) { pathAt(head - i * .08, p2); trailPos.set([p2[0], 0, p2[1]], i * 3); }
    trailGeo.attributes.position.needsUpdate = true;
  }

  // globe
  const g = smooth(clamp(cur.globe, 0, 1));
  globe.visible = atmo.visible = g > .01;
  if (globe.visible) {
    globe.scale.setScalar(.55 + .45 * g); atmo.scale.setScalar(.55 + .45 * g);
    globe.rotation.y += dt * .05 * cur.gspin * (reduce ? 0 : 1);
    globeMats.forEach(([m, a]) => { m.opacity = a * g; });
    atmo.material.uniforms.uOpacity.value = g;
  }

  // camera
  applyShift();
  const fs = fitScale();
  camTgt.fromArray(cur.tgt); camPos.fromArray(cur.cam).sub(camTgt).multiplyScalar(fs).add(camTgt);
  camera.position.copy(camPos); camera.lookAt(camTgt);
  if (Math.abs(camera.fov - cur.fov) > .01) { camera.fov = cur.fov; camera.updateProjectionMatrix(); }
  camera.updateMatrixWorld();
  chip.updateMatrixWorld();

  // labels
  const narrow = innerWidth <= 760;
  blockObjs.forEach(o => { tmp.copy(o.center).setY(.3); blockGroup.localToWorld(tmp); labelPos(tmp, o.label, narrow ? 0 : cur.bl); }); // phones use the colour key in the card instead
  layerObjs.forEach((o, i) => {
    const L = o.L, a = cur.ll * (1 - cur.top) * (narrow && (L.id === 'li1' || L.id === 'met2' || L.id === 'met4') ? 0 : 1);
    tmp.set(L.foot / 2, ys[i] + L.h / 2, -L.foot / 2); chip.localToWorld(tmp);
    labelPos(tmp, o.label, a);
    if (a > .02) o.label.style.transform += ' translate(calc(50% + 14px),0)';
  });

  renderer.render(scene, camera);
}
requestAnimationFrame(frame);
// ?debug: lets automated checks advance frames while the tab is in the background
if (location.search.includes('debug')) window.__hzn = { globe, pointMats, camera, scene, renderer };
if (location.search.includes('debug')) window.__tick = (n = 60) => { for (let i = 0; i < n; i++) { const t = last + 16.7; tick(t); last = t; } };
