import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { animate, tickTweens, easeOutCubic, easeInOutCubic, prefersReducedMotion } from './tween.js';
import { buildLondonMap, createClouds } from './londonMap.js';

const WORLD_SPAN = 46;
// Heights count from HEIGHT_BASELINE so the 60-85 score band reads as clear differences.
const HEIGHT_PER_POINT = 0.26;
const HEIGHT_BASELINE = 45;
const MIN_HEIGHT = 0.4;
const TOWER_WIDTH = 1.5;
const FOG_COLOR = 0xe4f3f1;
const LOW_COLOR = new THREE.Color('#5bc8f0');
const HIGH_COLOR = new THREE.Color('#8cc63f');
const INK = 0x3b2a20;

function skyTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 4;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 256);
    gradient.addColorStop(0, '#7fd0f5');
    gradient.addColorStop(0.55, '#c9ecfa');
    gradient.addColorStop(1, '#fff4e0');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 4, 256);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
}
const AUTO_ROTATE_RESUME_MS = 6000;
// Below this canvas width all 33 labels overlap into an unreadable pile, so
// only the top few (plus the selected tower) keep theirs.
const COMPACT_LABELS_BELOW_PX = 700;
const COMPACT_LABEL_COUNT = 5;

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

export function createCityScene(container, { onSelect } = {}) {
    const isPhone = window.matchMedia('(pointer: coarse) and (max-width: 820px), (pointer: coarse) and (max-height: 560px)').matches;
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, isPhone ? 1.5 : 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(container.clientWidth, container.clientHeight);
    labelRenderer.domElement.className = 'label-layer';
    container.appendChild(labelRenderer.domElement);

    const scene = new THREE.Scene();
    scene.background = skyTexture();
    scene.fog = new THREE.Fog(FOG_COLOR, 70, 170);

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

    scene.add(new THREE.HemisphereLight(0xdff4ff, 0xd8ecb8, 2.3));
    const sun = new THREE.DirectionalLight(0xfff1d6, 2.2);
    sun.position.set(22, 42, 16);
    sun.castShadow = true;
    sun.shadow.mapSize.setScalar(isPhone ? 1024 : 2048);
    Object.assign(sun.shadow.camera, { left: -40, right: 40, top: 40, bottom: -40, near: 1, far: 120 });
    sun.shadow.bias = -0.0005;
    sun.shadow.normalBias = 0.02;
    scene.add(sun);

    let londonMap = null;
    const clouds = createClouds();
    scene.add(...clouds);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(
        new THREE.Vector2(container.clientWidth, container.clientHeight),
        0.22,
        0.35,
        0.88
    );
    composer.addPass(bloom);
    composer.addPass(new OutputPass());

    const towerGeometry = new THREE.BoxGeometry(TOWER_WIDTH, 1, TOWER_WIDTH);
    towerGeometry.translate(0, 0.5, 0);
    const towerEdges = new THREE.EdgesGeometry(towerGeometry);
    const towerEdgeMaterial = new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.75 });
    const ringGeometry = new THREE.RingGeometry(TOWER_WIDTH * 0.85, TOWER_WIDTH * 1.25, 40);
    ringGeometry.rotateX(-Math.PI / 2);

    const towers = new Map();
    let projectorKey = '';

    let visibleNames = null;
    let labelsOn = true;
    let compactLabels = container.clientWidth < COMPACT_LABELS_BELOW_PX;
    let selected = null;

    function applyVisibility() {
        for (const [name, tower] of towers) {
            const shown = !visibleNames || visibleNames.has(name);
            const labelled = !compactLabels || tower.rank < COMPACT_LABEL_COUNT || name === selected;
            tower.group.visible = shown;
            tower.label.visible = shown && labelsOn && labelled;
        }
    }

    // names: Set of boroughs to show, or null for all.
    function setVisible(names) {
        visibleNames = names;
        applyVisibility();
    }

    function setLabelsVisible(on) {
        labelsOn = on;
        applyVisibility();
    }

    function createTower(borough, project) {
        const group = new THREE.Group();
        const { x, z } = project(borough);
        group.position.set(x, 0, z);

        const material = new THREE.MeshStandardMaterial({
            color: LOW_COLOR.clone(),
            emissive: LOW_COLOR.clone(),
            emissiveIntensity: 0.35,
            roughness: 0.55,
            metalness: 0,
        });
        const mesh = new THREE.Mesh(towerGeometry, material);
        mesh.scale.y = 0.001;
        mesh.userData.borough = borough.borough;
        mesh.castShadow = true;
        const edges = new THREE.LineSegments(towerEdges, towerEdgeMaterial);
        edges.raycast = () => {};
        mesh.add(edges);
        group.add(mesh);

        const ring = new THREE.Mesh(
            ringGeometry,
            new THREE.MeshBasicMaterial({
                color: LOW_COLOR.clone(),
                transparent: true,
                opacity: 0.25,
                depthWrite: false,
            })
        );
        ring.position.y = 0.05;
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
        if (londonMap) scene.remove(londonMap);
        londonMap = buildLondonMap(boroughs, project);
        scene.add(londonMap);
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
            const targetHeight = Math.max((b.overall_score - HEIGHT_BASELINE) * HEIGHT_PER_POINT, MIN_HEIGHT);
            const targetColor = LOW_COLOR.clone().lerp(HIGH_COLOR, (b.overall_score - min) / range);
            const targetGlow = rank === 0 ? 0.6 : rank < 3 ? 0.4 : 0.18;

            tower.score = b.overall_score;
            tower.rank = rank;
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
        applyVisibility();
    }

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let pointerDown = null;

    function pickTower(event) {
        const rect = renderer.domElement.getBoundingClientRect();
        pointer.set(
            ((event.clientX - rect.left) / rect.width) * 2 - 1,
            -((event.clientY - rect.top) / rect.height) * 2 + 1
        );
        raycaster.setFromCamera(pointer, camera);
        const pickable = [...towers.values()].filter((t) => t.group.visible).map((t) => t.mesh);
        const hit = raycaster.intersectObjects(pickable)[0];
        return hit ? hit.object.userData.borough : null;
    }

    renderer.domElement.addEventListener('pointerdown', (e) => {
        pointerDown = { x: e.clientX, y: e.clientY };
    });
    renderer.domElement.addEventListener('pointerup', (e) => {
        if (!pointerDown) return;
        const moved = Math.hypot(e.clientX - pointerDown.x, e.clientY - pointerDown.y);
        pointerDown = null;
        if (moved > 5) return;
        const name = pickTower(e);
        if (name && onSelect) onSelect(name);
    });

    const tooltip = document.createElement('div');
    tooltip.className = 'tower-tooltip';
    tooltip.hidden = true;
    tooltip.innerHTML = '<strong></strong><span></span>';
    document.body.appendChild(tooltip);
    let hoverEvent = null;
    let hovered = null;

    renderer.domElement.addEventListener('pointermove', (e) => {
        hoverEvent = e;
    });
    renderer.domElement.addEventListener('pointerleave', () => {
        hoverEvent = null;
        setHovered(null);
    });

    function setHovered(name, event) {
        if (hovered !== name) {
            if (hovered && towers.has(hovered)) {
                const prev = towers.get(hovered).mesh;
                prev.scale.x = prev.scale.z = 1;
            }
            hovered = name;
            if (name && towers.has(name)) {
                const mesh = towers.get(name).mesh;
                mesh.scale.x = mesh.scale.z = 1.18;
            }
        }
        if (!name || !towers.has(name)) {
            tooltip.hidden = true;
            renderer.domElement.style.cursor = '';
            return;
        }
        const tower = towers.get(name);
        tooltip.querySelector('strong').textContent = `#${tower.rank + 1} ${name}`;
        tooltip.querySelector('span').textContent = `${tower.score.toFixed(1)} / 100`;
        tooltip.style.transform = `translate(${event.clientX + 14}px, ${event.clientY + 14}px)`;
        tooltip.hidden = false;
        renderer.domElement.style.cursor = 'pointer';
    }

    function processHover() {
        if (!hoverEvent) return;
        const event = hoverEvent;
        hoverEvent = null;
        setHovered(pointerDown ? null : pickTower(event), event);
    }

    const HOME_POSITION = camera.position.clone();
    const HOME_TARGET = controls.target.clone();
    let cancelCameraTween = null;

    function flyCamera(toPosition, toTarget, duration = 1100) {
        if (cancelCameraTween) cancelCameraTween();
        setHovered(null);
        controls.autoRotate = false;
        clearTimeout(resumeTimer);
        const fromPosition = camera.position.clone();
        const fromTarget = controls.target.clone();
        cancelCameraTween = animate({
            duration,
            ease: easeInOutCubic,
            onUpdate: (t) => {
                camera.position.lerpVectors(fromPosition, toPosition, t);
                controls.target.lerpVectors(fromTarget, toTarget, t);
            },
            onComplete: () => {
                cancelCameraTween = null;
            },
        });
    }

    function setSelected(name) {
        if (selected && towers.has(selected)) towers.get(selected).ring.scale.setScalar(1);
        selected = name;
        if (name && towers.has(name)) towers.get(name).ring.scale.setScalar(1.6);
        applyVisibility();
    }

    function focusOn(name) {
        const tower = towers.get(name);
        if (!tower) return;
        setSelected(name);
        const target = tower.group.position.clone();
        target.y = tower.height * 0.5;
        const direction = camera.position.clone().sub(controls.target).setY(0).normalize();
        const position = target.clone().addScaledVector(direction, 22);
        position.y = target.y + 14;
        flyCamera(position, target);
    }

    function resetView() {
        setSelected(null);
        flyCamera(HOME_POSITION.clone(), HOME_TARGET.clone());
        resumeTimer = setTimeout(() => {
            controls.autoRotate = !prefersReducedMotion();
        }, 1200);
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
        if (compactLabels !== w < COMPACT_LABELS_BELOW_PX) {
            compactLabels = w < COMPACT_LABELS_BELOW_PX;
            applyVisibility();
        }
    }
    new ResizeObserver(resize).observe(container);

    const driftClouds = !prefersReducedMotion();
    let lastFrame = performance.now();

    function frame(now) {
        const dt = Math.min((now - lastFrame) / 1000, 0.1);
        lastFrame = now;
        if (driftClouds) {
            for (const cloud of clouds) {
                cloud.position.x += cloud.userData.speed * dt;
                if (cloud.position.x > 70) cloud.position.x = -70;
            }
        }
        tickTweens(now);
        processHover();
        controls.update();
        composer.render();
        labelRenderer.render(scene, camera);
        requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    return { update, focusOn, resetView, setVisible, setLabelsVisible };
}
