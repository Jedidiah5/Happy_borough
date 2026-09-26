import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { animate, tickTweens, easeOutCubic, prefersReducedMotion } from './tween.js';

const WORLD_SPAN = 46;
const HEIGHT_PER_POINT = 0.14;
const TOWER_WIDTH = 1.5;
const BACKGROUND = 0x05070d;
const LOW_COLOR = new THREE.Color('#3b4fd8');
const HIGH_COLOR = new THREE.Color('#34f5c5');
const AUTO_ROTATE_RESUME_MS = 6000;

function makeProjector(boroughs) {
    const lat0 = boroughs.reduce((s, b) => s + b.lat, 0) / boroughs.length;
    const lng0 = boroughs.reduce((s, b) => s + b.lng, 0) / boroughs.length;
    const lngScale = Math.cos((lat0 * Math.PI) / 180);
    const xs = boroughs.map((b) => (b.lng - lng0) * lngScale);
    const zs = boroughs.map((b) => -(b.lat - lat0));
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs)) || 0.1;
    const scale = WORLD_SPAN / span;
    return (b) => ({ x: (b.lng - lng0) * lngScale * scale, z: -(b.lat - lat0) * scale });
}

export function createCityScene(container) {
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    container.appendChild(renderer.domElement);

    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(container.clientWidth, container.clientHeight);
    labelRenderer.domElement.className = 'label-layer';
    container.appendChild(labelRenderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BACKGROUND);
    scene.fog = new THREE.Fog(BACKGROUND, 45, 130);

    const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 500);
    camera.position.set(0, 40, 64);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 4, 0);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 12;
    controls.maxDistance = 110;
    controls.maxPolarAngle = Math.PI * 0.44;
    controls.autoRotateSpeed = 0.35;
    controls.autoRotate = !prefersReducedMotion();

    let resumeTimer = null;
    controls.addEventListener('start', () => {
        controls.autoRotate = false;
        clearTimeout(resumeTimer);
    });
    controls.addEventListener('end', () => {
        clearTimeout(resumeTimer);
        resumeTimer = setTimeout(() => {
            controls.autoRotate = !prefersReducedMotion();
        }, AUTO_ROTATE_RESUME_MS);
    });

    scene.add(new THREE.HemisphereLight(0x8fb3ff, 0x05070d, 0.7));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(20, 40, 12);
    scene.add(sun);

    const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(400, 400),
        new THREE.MeshStandardMaterial({ color: 0x080d18, roughness: 1, metalness: 0 })
    );
    ground.rotation.x = -Math.PI / 2;
    scene.add(ground);

    const grid = new THREE.GridHelper(240, 120, 0x1e3a5f, 0x0f1b2d);
    grid.material.transparent = true;
    grid.material.opacity = 0.45;
    grid.position.y = 0.01;
    scene.add(grid);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(
        new THREE.Vector2(container.clientWidth, container.clientHeight),
        0.55,
        0.4,
        0.32
    );
    composer.addPass(bloom);
    composer.addPass(new OutputPass());

    const towerGeometry = new THREE.BoxGeometry(TOWER_WIDTH, 1, TOWER_WIDTH);
    towerGeometry.translate(0, 0.5, 0);
    const ringGeometry = new THREE.RingGeometry(TOWER_WIDTH * 0.85, TOWER_WIDTH * 1.25, 40);
    ringGeometry.rotateX(-Math.PI / 2);

    const towers = new Map();
    let projectorKey = '';

    const beam = createBeam();
    beam.visible = false;
    scene.add(beam);
    let beamOwner = null;
    let cancelBeamFade = null;

    function createBeam() {
        const canvas = document.createElement('canvas');
        canvas.width = 4;
        canvas.height = 128;
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, 0, 0, 128);
        gradient.addColorStop(0, 'rgba(0,0,0,1)');
        gradient.addColorStop(0.6, 'rgba(90,90,90,1)');
        gradient.addColorStop(1, 'rgba(255,255,255,1)');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, 4, 128);
        const geometry = new THREE.CylinderGeometry(0.55, 0.95, 70, 32, 1, true);
        geometry.translate(0, 35, 0);
        const material = new THREE.MeshBasicMaterial({
            color: HIGH_COLOR.clone(),
            alphaMap: new THREE.CanvasTexture(canvas),
            transparent: true,
            opacity: 0,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            side: THREE.DoubleSide,
            fog: false,
        });
        return new THREE.Mesh(geometry, material);
    }

    function moveBeamTo(name, delay = 0) {
        if (name === beamOwner) return;
        beamOwner = name;
        const tower = towers.get(name);
        if (!tower) return;
        if (cancelBeamFade) cancelBeamFade();
        beam.position.copy(tower.group.position);
        beam.visible = true;
        beam.material.opacity = 0;
        cancelBeamFade = animate({
            duration: 500,
            delay,
            onUpdate: (t) => {
                beam.material.opacity = 0.55 * t;
            },
        });
    }

    function createTower(borough, project) {
        const group = new THREE.Group();
        const { x, z } = project(borough);
        group.position.set(x, 0, z);

        const material = new THREE.MeshStandardMaterial({
            color: LOW_COLOR.clone(),
            emissive: LOW_COLOR.clone(),
            emissiveIntensity: 0.35,
            roughness: 0.35,
            metalness: 0.15,
        });
        const mesh = new THREE.Mesh(towerGeometry, material);
        mesh.scale.y = 0.001;
        mesh.userData.borough = borough.borough;
        group.add(mesh);

        const ring = new THREE.Mesh(
            ringGeometry,
            new THREE.MeshBasicMaterial({
                color: LOW_COLOR.clone(),
                transparent: true,
                opacity: 0.25,
                blending: THREE.AdditiveBlending,
                depthWrite: false,
            })
        );
        ring.position.y = 0.02;
        group.add(ring);

        const labelEl = document.createElement('div');
        labelEl.className = 'tower-label';
        labelEl.innerHTML = '<span class="tl-rank"></span><span class="tl-name"></span>';
        labelEl.querySelector('.tl-name').textContent = borough.borough;
        const label = new CSS2DObject(labelEl);
        label.position.set(0, 1, 0);
        group.add(label);

        scene.add(group);
        return { group, mesh, ring, label, labelEl, height: 0, cancel: null };
    }

    function syncTowers(boroughs) {
        const key = boroughs.map((b) => b.borough).sort().join('|');
        if (key === projectorKey) return;
        projectorKey = key;
        const project = makeProjector(boroughs);
        const names = new Set(boroughs.map((b) => b.borough));
        for (const [name, tower] of towers) {
            if (!names.has(name)) {
                scene.remove(tower.group);
                tower.mesh.material.dispose();
                tower.ring.material.dispose();
                tower.labelEl.remove();
                towers.delete(name);
            }
        }
        for (const b of boroughs) {
            const tower = towers.get(b.borough);
            if (tower) {
                const { x, z } = project(b);
                tower.group.position.set(x, 0, z);
            } else {
                towers.set(b.borough, createTower(b, project));
            }
        }
    }

    function setTowerHeight(tower, height) {
        tower.height = height;
        tower.mesh.scale.y = Math.max(height, 0.001);
        tower.label.position.y = height + 0.9;
    }

    // ranked: boroughs sorted by overall_score (descending).
    // stagger (ms): spreads start times west -> east, used for the load-in rise.
    function update(ranked, { animated = true, duration = 600, stagger = 0 } = {}) {
        syncTowers(ranked);
        const scores = ranked.map((b) => b.overall_score);
        const min = Math.min(...scores);
        const range = Math.max(...scores) - min || 1;
        const xs = [...towers.values()].map((t) => t.group.position.x);
        const minX = Math.min(...xs);
        const spanX = Math.max(...xs) - minX || 1;

        ranked.forEach((b, rank) => {
            const tower = towers.get(b.borough);
            const targetHeight = b.overall_score * HEIGHT_PER_POINT;
            const targetColor = LOW_COLOR.clone().lerp(HIGH_COLOR, (b.overall_score - min) / range);
            const targetGlow = rank === 0 ? 1.1 : rank < 3 ? 0.8 : 0.18;

            tower.labelEl.querySelector('.tl-rank').textContent = `#${rank + 1}`;
            tower.labelEl.classList.toggle('is-top', rank < 3);
            tower.ring.material.opacity = rank < 3 ? 0.6 : 0.2;

            if (tower.cancel) tower.cancel();
            const material = tower.mesh.material;
            if (!animated) {
                setTowerHeight(tower, targetHeight);
                material.color.copy(targetColor);
                material.emissive.copy(targetColor);
                material.emissiveIntensity = targetGlow;
                tower.ring.material.color.copy(targetColor);
                return;
            }
            const fromHeight = tower.height;
            const fromColor = material.color.clone();
            const fromGlow = material.emissiveIntensity;
            tower.cancel = animate({
                duration,
                delay: (stagger * (tower.group.position.x - minX)) / spanX,
                ease: easeOutCubic,
                onUpdate: (t) => {
                    setTowerHeight(tower, fromHeight + (targetHeight - fromHeight) * t);
                    material.color.copy(fromColor).lerp(targetColor, t);
                    material.emissive.copy(material.color);
                    material.emissiveIntensity = fromGlow + (targetGlow - fromGlow) * t;
                    tower.ring.material.color.copy(material.color);
                },
            });
        });
        updateBeam(ranked, animated ? stagger + duration * 0.6 : 0);
    }

    function updateBeam(ranked, delay) {
        if (ranked.length) moveBeamTo(ranked[0].borough, delay);
    }

    function resize() {
        const w = container.clientWidth;
        const h = container.clientHeight;
        if (!w || !h) return;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
        labelRenderer.setSize(w, h);
        composer.setSize(w, h);
    }
    new ResizeObserver(resize).observe(container);

    function frame(now) {
        tickTweens(now);
        controls.update();
        composer.render();
        labelRenderer.render(scene, camera);
        requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    return { update };
}
