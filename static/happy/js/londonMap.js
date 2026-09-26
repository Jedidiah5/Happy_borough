import * as THREE from 'three';

const BOARD_TOP_DEPTH = 0.5;
const BOARD_BASE_DEPTH = 1.6;
const OUTLINE_MARGIN = 4.5;
const CELL_GAP = 0.16;
const RIVER_WIDTH = 1.25;
const TREE_COUNT = 110;

const CELL_COLORS = ['#fbf1dc', '#f6e8cc', '#fdf5e6', '#f3e4c4', '#f9ecd3'];
const BASE_COLOR = '#8cc63f';
const BASE_SIDE_COLOR = '#5c9a2a';
const RIVER_COLOR = '#4fb8ea';
const WATER_COLOR = '#a8e0f5';
const INK = '#3b2a20';

// Simplified course of the Thames (lat, lng), west to east.
const THAMES = [
    [51.405, -0.345], [51.412, -0.305], [51.435, -0.31], [51.455, -0.305], [51.468, -0.29],
    [51.483, -0.285], [51.49, -0.255], [51.487, -0.23], [51.47, -0.215], [51.466, -0.2],
    [51.478, -0.18], [51.483, -0.16], [51.486, -0.13], [51.495, -0.122], [51.506, -0.121],
    [51.509, -0.105], [51.508, -0.085], [51.505, -0.072], [51.502, -0.055], [51.508, -0.035],
    [51.494, -0.027], [51.485, -0.012], [51.494, 0.0], [51.507, 0.004], [51.498, 0.018],
    [51.5, 0.045], [51.496, 0.07], [51.505, 0.1], [51.498, 0.13], [51.49, 0.16],
    [51.48, 0.19], [51.47, 0.22], [51.46, 0.25],
];

function mulberry32(seed) {
    return () => {
        seed |= 0;
        seed = (seed + 0x6d2b79f5) | 0;
        let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

function hashString(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
    return h >>> 0;
}

function convexHull(points) {
    const pts = [...points].sort((a, b) => a.x - b.x || a.z - b.z);
    const cross = (o, a, b) => (a.x - o.x) * (b.z - o.z) - (a.z - o.z) * (b.x - o.x);
    const lower = [];
    for (const p of pts) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
        lower.push(p);
    }
    const upper = [];
    for (const p of pts.reverse()) {
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
        upper.push(p);
    }
    return lower.slice(0, -1).concat(upper.slice(0, -1));
}

function chaikin(poly, iterations) {
    let out = poly;
    for (let n = 0; n < iterations; n++) {
        const next = [];
        for (let i = 0; i < out.length; i++) {
            const p = out[i];
            const q = out[(i + 1) % out.length];
            next.push({ x: p.x * 0.75 + q.x * 0.25, z: p.z * 0.75 + q.z * 0.25 });
            next.push({ x: p.x * 0.25 + q.x * 0.75, z: p.z * 0.25 + q.z * 0.75 });
        }
        out = next;
    }
    return out;
}

// Keeps the part of `poly` where a*x + b*z <= c (Sutherland-Hodgman against one half-plane).
function clipHalfPlane(poly, a, b, c) {
    const out = [];
    for (let i = 0; i < poly.length; i++) {
        const p = poly[i];
        const q = poly[(i + 1) % poly.length];
        const fp = a * p.x + b * p.z - c;
        const fq = a * q.x + b * q.z - c;
        if (fp <= 0) out.push(p);
        if ((fp <= 0) !== (fq <= 0)) {
            const t = fp / (fp - fq);
            out.push({ x: p.x + (q.x - p.x) * t, z: p.z + (q.z - p.z) * t });
        }
    }
    return out;
}

function polygonCentroid(poly) {
    let x = 0, z = 0;
    for (const p of poly) { x += p.x; z += p.z; }
    return { x: x / poly.length, z: z / poly.length };
}

function insetPolygon(poly, amount) {
    const c = polygonCentroid(poly);
    return poly.map((p) => {
        const dx = p.x - c.x, dz = p.z - c.z;
        const len = Math.hypot(dx, dz) || 1;
        const k = Math.max(len - amount, 0) / len;
        return { x: c.x + dx * k, z: c.z + dz * k };
    });
}

function pointInPolygon(pt, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const a = poly[i], b = poly[j];
        if ((a.z > pt.z) !== (b.z > pt.z) && pt.x < ((b.x - a.x) * (pt.z - a.z)) / (b.z - a.z) + a.x) inside = !inside;
    }
    return inside;
}

// Shape points use (x, -z) so that after rotateX(-PI/2) the extrusion runs up +y.
function extrudePolygon(poly, depth, top) {
    const shape = new THREE.Shape(poly.map((p) => new THREE.Vector2(p.x, -p.z)));
    const geometry = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false });
    geometry.rotateX(-Math.PI / 2);
    geometry.translate(0, top - depth, 0);
    return geometry;
}

function outlineLoop(poly, y, material) {
    const points = poly.map((p) => new THREE.Vector3(p.x, y, p.z));
    return new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(points), material);
}

function buildRiver(project, outline) {
    const inner = insetPolygon(outline, 0.6);
    const curve = new THREE.CatmullRomCurve3(
        THAMES.map(([lat, lng]) => {
            const { x, z } = project({ lat, lng });
            return new THREE.Vector3(x, 0, z);
        })
    );
    const samples = curve.getSpacedPoints(400).filter((p) => pointInPolygon({ x: p.x, z: p.z }, inner));
    if (samples.length < 2) return { mesh: null, samples: [] };

    const positions = [];
    const indices = [];
    for (let i = 0; i < samples.length; i++) {
        const prev = samples[Math.max(i - 1, 0)];
        const next = samples[Math.min(i + 1, samples.length - 1)];
        const tx = next.x - prev.x, tz = next.z - prev.z;
        const len = Math.hypot(tx, tz) || 1;
        const nx = -tz / len, nz = tx / len;
        const half = RIVER_WIDTH / 2;
        positions.push(samples[i].x + nx * half, 0.04, samples[i].z + nz * half);
        positions.push(samples[i].x - nx * half, 0.04, samples[i].z - nz * half);
        if (i > 0) {
            const a = (i - 1) * 2;
            indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
        }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(
        geometry,
        new THREE.MeshStandardMaterial({ color: RIVER_COLOR, roughness: 0.25, metalness: 0, side: THREE.DoubleSide, emissive: RIVER_COLOR, emissiveIntensity: 0.15 })
    );
    mesh.receiveShadow = true;
    return { mesh, samples };
}

function buildTrees(outline, sites, riverSamples, seed) {
    const rand = mulberry32(seed);
    const inner = insetPolygon(outline, 1.4);
    const xs = inner.map((p) => p.x), zs = inner.map((p) => p.z);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minZ = Math.min(...zs), maxZ = Math.max(...zs);
    const spots = [];
    for (let attempt = 0; attempt < TREE_COUNT * 20 && spots.length < TREE_COUNT; attempt++) {
        const p = { x: minX + rand() * (maxX - minX), z: minZ + rand() * (maxZ - minZ) };
        if (!pointInPolygon(p, inner)) continue;
        if (sites.some((s) => Math.hypot(s.x - p.x, s.z - p.z) < 2.1)) continue;
        if (riverSamples.some((s) => Math.hypot(s.x - p.x, s.z - p.z) < RIVER_WIDTH)) continue;
        if (spots.some((s) => Math.hypot(s.x - p.x, s.z - p.z) < 0.9)) continue;
        spots.push({ ...p, scale: 0.7 + rand() * 0.6, shade: rand() });
    }

    const group = new THREE.Group();
    const trunkGeo = new THREE.CylinderGeometry(0.08, 0.11, 0.45, 6);
    trunkGeo.translate(0, 0.22, 0);
    const leafGeo = new THREE.IcosahedronGeometry(0.42, 0);
    leafGeo.translate(0, 0.75, 0);
    const trunks = new THREE.InstancedMesh(trunkGeo, new THREE.MeshStandardMaterial({ color: '#8a5a3b', roughness: 0.9 }), spots.length);
    const leaves = new THREE.InstancedMesh(leafGeo, new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.8, flatShading: true }), spots.length);
    const light = new THREE.Color('#9ed65a');
    const dark = new THREE.Color('#5fa82e');
    const matrix = new THREE.Matrix4();
    spots.forEach((s, i) => {
        matrix.makeScale(s.scale, s.scale, s.scale).setPosition(s.x, 0, s.z);
        trunks.setMatrixAt(i, matrix);
        leaves.setMatrixAt(i, matrix);
        leaves.setColorAt(i, light.clone().lerp(dark, s.shade));
    });
    trunks.castShadow = leaves.castShadow = true;
    group.add(trunks, leaves);
    return group;
}

// Borough patchwork (Voronoi cells around each borough centre), clipped to a
// rounded London outline, with the Thames and little trees on top. The board's
// top surface sits at y = 0 so towers stand on it.
export function buildLondonMap(boroughs, project) {
    const group = new THREE.Group();
    const sites = boroughs.map((b) => ({ ...project(b), name: b.borough }));

    const hull = convexHull(sites);
    const centre = polygonCentroid(hull);
    const expanded = hull.map((p) => {
        const dx = p.x - centre.x, dz = p.z - centre.z;
        const len = Math.hypot(dx, dz) || 1;
        return { x: p.x + (dx / len) * OUTLINE_MARGIN, z: p.z + (dz / len) * OUTLINE_MARGIN };
    });
    const outline = chaikin(expanded, 3);

    const base = new THREE.Mesh(
        extrudePolygon(outline, BOARD_BASE_DEPTH, -0.06),
        [
            new THREE.MeshStandardMaterial({ color: BASE_COLOR, roughness: 0.9 }),
            new THREE.MeshStandardMaterial({ color: BASE_SIDE_COLOR, roughness: 0.9 }),
        ]
    );
    base.receiveShadow = true;
    group.add(base);

    const ink = new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.35 });
    group.add(outlineLoop(outline, -0.06, new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.6 })));

    sites.forEach((site, i) => {
        let cell = outline;
        for (let j = 0; j < sites.length && cell.length >= 3; j++) {
            if (j === i) continue;
            const other = sites[j];
            const a = other.x - site.x, b = other.z - site.z;
            const c = a * (site.x + other.x) / 2 + b * (site.z + other.z) / 2;
            cell = clipHalfPlane(cell, a, b, c);
        }
        if (cell.length < 3) return;
        const inset = insetPolygon(cell, CELL_GAP);
        const color = CELL_COLORS[hashString(site.name) % CELL_COLORS.length];
        const mesh = new THREE.Mesh(
            extrudePolygon(inset, BOARD_TOP_DEPTH, 0),
            new THREE.MeshStandardMaterial({ color, roughness: 0.95 })
        );
        mesh.receiveShadow = true;
        group.add(mesh);
        group.add(outlineLoop(inset, 0.01, ink));
    });

    const river = buildRiver(project, outline);
    if (river.mesh) group.add(river.mesh);
    group.add(buildTrees(outline, sites, river.samples, hashString(sites.map((s) => s.name).join('|'))));

    const water = new THREE.Mesh(
        new THREE.CircleGeometry(260, 64),
        new THREE.MeshStandardMaterial({ color: WATER_COLOR, roughness: 0.6 })
    );
    water.rotation.x = -Math.PI / 2;
    water.position.y = -BOARD_BASE_DEPTH - 0.4;
    water.receiveShadow = true;
    group.add(water);

    return group;
}

export function createClouds(count = 7) {
    const rand = mulberry32(7);
    const material = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 1, emissive: '#ffffff', emissiveIntensity: 0.25, flatShading: true });
    const puff = new THREE.IcosahedronGeometry(1, 1);
    const clouds = [];
    for (let i = 0; i < count; i++) {
        const cloud = new THREE.Group();
        const puffs = 3 + Math.floor(rand() * 3);
        for (let p = 0; p < puffs; p++) {
            const mesh = new THREE.Mesh(puff, material);
            const s = 1.2 + rand() * 1.4;
            mesh.scale.set(s * 1.3, s, s);
            mesh.position.set((p - puffs / 2) * 1.8, rand() * 0.8, rand() * 1.2);
            cloud.add(mesh);
        }
        const angle = (i / count) * Math.PI * 2 + rand();
        const radius = 34 + rand() * 22;
        cloud.position.set(Math.cos(angle) * radius, 15 + rand() * 9, Math.sin(angle) * radius);
        cloud.userData.speed = 0.4 + rand() * 0.6;
        clouds.push(cloud);
    }
    return clouds;
}
