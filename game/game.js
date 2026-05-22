// ─── SCENE SETUP ────────────────────────────────────────────────────────────
const canvas = document.getElementById('canvas');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.setSize(window.innerWidth, window.innerHeight);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);
scene.fog = new THREE.Fog(0x1a1a2e, 30, 120);

const camera = new THREE.PerspectiveCamera(70, window.innerWidth / window.innerHeight, 0.1, 200);

window.addEventListener('resize', () => {
  renderer.setSize(window.innerWidth, window.innerHeight);
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
});

// ─── LIGHTING ────────────────────────────────────────────────────────────────
const ambient = new THREE.AmbientLight(0x404060, 0.6);
scene.add(ambient);

const sun = new THREE.DirectionalLight(0xffeedd, 1.2);
sun.position.set(20, 40, 20);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 0.5;
sun.shadow.camera.far = 150;
sun.shadow.camera.left = -60;
sun.shadow.camera.right = 60;
sun.shadow.camera.top = 60;
sun.shadow.camera.bottom = -60;
scene.add(sun);

const fillLight = new THREE.PointLight(0x4466ff, 0.5, 80);
fillLight.position.set(-20, 10, -20);
scene.add(fillLight);

// ─── ARENA ───────────────────────────────────────────────────────────────────
function buildArena() {
  const ARENA = 50;

  // Floor
  const floorGeo = new THREE.PlaneGeometry(ARENA * 2, ARENA * 2, 20, 20);
  const floorMat = new THREE.MeshLambertMaterial({ color: 0x2c3e50 });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  // Grid lines on floor
  const grid = new THREE.GridHelper(ARENA * 2, 40, 0x3a4a5a, 0x3a4a5a);
  grid.position.y = 0.01;
  scene.add(grid);

  // Boundary walls
  const wallMat = new THREE.MeshLambertMaterial({ color: 0x1a252f });
  const wallConfigs = [
    { w: ARENA * 2, h: 10, d: 1, x: 0, z: -ARENA },
    { w: ARENA * 2, h: 10, d: 1, x: 0, z:  ARENA },
    { w: 1, h: 10, d: ARENA * 2, x: -ARENA, z: 0 },
    { w: 1, h: 10, d: ARENA * 2, x:  ARENA, z: 0 },
  ];
  wallConfigs.forEach(({ w, h, d, x, z }) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wallMat);
    mesh.position.set(x, h / 2, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    scene.add(mesh);
  });

  // Cover objects (boxes / pillars)
  const coverMat = new THREE.MeshLambertMaterial({ color: 0x34495e });
  const covers = [
    { x: 10, z: 10, w: 3, h: 2, d: 3 },
    { x: -10, z: -10, w: 3, h: 2, d: 3 },
    { x: 20, z: -15, w: 2, h: 4, d: 2 },
    { x: -20, z: 15, w: 2, h: 4, d: 2 },
    { x: 5, z: -25, w: 6, h: 1.5, d: 2 },
    { x: -5, z: 25, w: 6, h: 1.5, d: 2 },
    { x: -30, z: 5, w: 2, h: 3, d: 5 },
    { x: 30, z: -5, w: 2, h: 3, d: 5 },
    { x: 15, z: 30, w: 4, h: 2, d: 2 },
    { x: -15, z: -30, w: 4, h: 2, d: 2 },
  ];
  covers.forEach(({ x, z, w, h, d }) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), coverMat);
    mesh.position.set(x, h / 2, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    scene.add(mesh);
  });

  // Ambient particles (floating dust)
  const partGeo = new THREE.BufferGeometry();
  const positions = [];
  for (let i = 0; i < 300; i++) {
    positions.push(
      (Math.random() - 0.5) * ARENA * 2,
      Math.random() * 8 + 0.5,
      (Math.random() - 0.5) * ARENA * 2
    );
  }
  partGeo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  const partMat = new THREE.PointsMaterial({ color: 0x88aaff, size: 0.08, transparent: true, opacity: 0.4 });
  scene.add(new THREE.Points(partGeo, partMat));
}

buildArena();

// ─── PLAYER ───────────────────────────────────────────────────────────────────
function makePlayer() {
  const group = new THREE.Group();

  // Body
  const bodyMesh = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.35, 0.9, 4, 8),
    new THREE.MeshLambertMaterial({ color: 0x2980b9 })
  );
  bodyMesh.position.y = 0.95;
  bodyMesh.castShadow = true;
  group.add(bodyMesh);

  // Head
  const headMesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.28, 8, 8),
    new THREE.MeshLambertMaterial({ color: 0xf0c080 })
  );
  headMesh.position.y = 1.95;
  headMesh.castShadow = true;
  group.add(headMesh);

  // Gun
  const gunGroup = new THREE.Group();
  const gunBarrel = new THREE.Mesh(
    new THREE.BoxGeometry(0.08, 0.08, 0.6),
    new THREE.MeshLambertMaterial({ color: 0x222 })
  );
  gunBarrel.position.z = -0.3;
  gunGroup.add(gunBarrel);
  const gunBody = new THREE.Mesh(
    new THREE.BoxGeometry(0.15, 0.2, 0.35),
    new THREE.MeshLambertMaterial({ color: 0x333 })
  );
  gunGroup.add(gunBody);
  gunGroup.position.set(0.35, 1.5, -0.2);
  group.add(gunGroup);

  scene.add(group);
  return { group, gunGroup, bodyMesh, headMesh };
}

const player = makePlayer();

// ─── GAME STATE ───────────────────────────────────────────────────────────────
const state = {
  hp: 100,
  maxHp: 100,
  score: 0,
  wave: 1,
  ammo: 30,
  maxAmmo: 30,
  reserve: 90,
  reloading: false,
  reloadTime: 0,
  running: false,
  gameOver: false,
  shootCooldown: 0,
  damageFlash: 0,
};

const keys = {};
let yaw = 0;   // horizontal look (radians)
let pitch = 0; // not used for camera tilt, kept for future

document.addEventListener('keydown', e => { keys[e.code] = true; onKey(e); });
document.addEventListener('keyup',   e => { keys[e.code] = false; });

function onKey(e) {
  if (e.code === 'KeyR' && state.running && !state.reloading && state.reserve > 0 && state.ammo < state.maxAmmo) startReload();
}

canvas.addEventListener('click', () => {
  if (!state.running || state.gameOver) return;
  shoot();
});

// Pointer lock for mouse look
canvas.addEventListener('click', () => {
  if (state.running && !state.gameOver) canvas.requestPointerLock();
});

document.addEventListener('mousemove', e => {
  if (document.pointerLockElement !== canvas) return;
  yaw   -= e.movementX * 0.002;
  pitch -= e.movementY * 0.002;
  pitch = Math.max(-0.4, Math.min(0.5, pitch));
});

// ─── BULLETS ─────────────────────────────────────────────────────────────────
const bullets = [];
const bulletGeo = new THREE.SphereGeometry(0.06, 4, 4);
const bulletMat = new THREE.MeshBasicMaterial({ color: 0xffee44 });

function shoot() {
  if (state.ammo <= 0 || state.reloading || state.shootCooldown > 0) return;
  state.ammo--;
  state.shootCooldown = 0.12;
  updateAmmoHUD();

  const dir = new THREE.Vector3(0, 0, -1).applyEuler(new THREE.Euler(0, yaw, 0));
  const origin = player.group.position.clone().add(new THREE.Vector3(0.35, 1.5, 0));

  const b = new THREE.Mesh(bulletGeo, bulletMat);
  b.position.copy(origin);
  scene.add(b);

  const light = new THREE.PointLight(0xffee44, 1.5, 4);
  light.position.copy(origin);
  scene.add(light);
  setTimeout(() => scene.remove(light), 80);

  bullets.push({ mesh: b, dir: dir.clone(), life: 1.8 });

  if (state.ammo === 0 && state.reserve > 0) startReload();
}

function startReload() {
  state.reloading = true;
  state.reloadTime = 2.0;
  document.getElementById('reload-indicator').style.display = 'block';
}

function finishReload() {
  const needed = state.maxAmmo - state.ammo;
  const take = Math.min(needed, state.reserve);
  state.ammo += take;
  state.reserve -= take;
  state.reloading = false;
  document.getElementById('reload-indicator').style.display = 'none';
  updateAmmoHUD();
}

// ─── ENEMIES ─────────────────────────────────────────────────────────────────
const enemies = [];
let spawnTimer = 0;
let waveTimer  = 0;

function makeEnemy(px, pz) {
  const group = new THREE.Group();

  const colors = [0xe74c3c, 0x8e44ad, 0xd35400, 0x16a085];
  const col = colors[Math.floor(Math.random() * colors.length)];

  const body = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.35, 0.8, 4, 8),
    new THREE.MeshLambertMaterial({ color: col })
  );
  body.position.y = 0.9;
  body.castShadow = true;
  group.add(body);

  const head = new THREE.Mesh(
    new THREE.SphereGeometry(0.28, 8, 8),
    new THREE.MeshLambertMaterial({ color: 0xcc8855 })
  );
  head.position.y = 1.85;
  head.castShadow = true;
  group.add(head);

  // Health bar sprite
  const hbBg = new THREE.Mesh(
    new THREE.PlaneGeometry(0.8, 0.1),
    new THREE.MeshBasicMaterial({ color: 0x333333, side: THREE.DoubleSide })
  );
  hbBg.position.y = 2.4;
  group.add(hbBg);

  const hbFill = new THREE.Mesh(
    new THREE.PlaneGeometry(0.78, 0.08),
    new THREE.MeshBasicMaterial({ color: 0x2ecc71, side: THREE.DoubleSide })
  );
  hbFill.position.y = 2.4;
  hbFill.position.z = 0.01;
  group.add(hbFill);

  group.position.set(px, 0, pz);
  scene.add(group);

  const maxHp = 30 + state.wave * 10;
  return { group, hbFill, hp: maxHp, maxHp, speed: 2.5 + state.wave * 0.4, attackTimer: 0 };
}

function spawnEnemyRing() {
  const count = 3 + state.wave * 2;
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2;
    const dist = 35 + Math.random() * 10;
    spawnEnemy(Math.cos(angle) * dist, Math.sin(angle) * dist);
  }
}

function spawnEnemy(x, z) {
  enemies.push(makeEnemy(x, z));
}

// ─── HUD HELPERS ─────────────────────────────────────────────────────────────
function updateHpHUD() {
  const pct = Math.max(0, state.hp / state.maxHp);
  document.getElementById('health-bar').style.width = (pct * 100) + '%';
  const hue = Math.round(pct * 120);
  document.getElementById('health-bar').style.background =
    `linear-gradient(90deg, hsl(${hue},80%,40%), hsl(${hue},80%,60%))`;
  document.getElementById('hp-val').textContent = Math.max(0, state.hp);
}

function updateAmmoHUD() {
  document.getElementById('ammo-val').textContent = state.ammo;
  document.getElementById('reserve-val').textContent = state.reserve;
}

function updateScoreHUD() {
  document.getElementById('score-val').textContent = state.score;
  document.getElementById('wave-val').textContent = state.wave;
}

function addKillMsg() {
  const feed = document.getElementById('kill-feed');
  const div = document.createElement('div');
  div.className = 'kill-msg';
  div.textContent = '+ ENEMY DOWN';
  feed.appendChild(div);
  setTimeout(() => div.remove(), 2100);
}

function flashDamage() {
  const v = document.getElementById('damage-vignette');
  v.style.background = 'radial-gradient(ellipse at center, transparent 50%, rgba(220,30,30,0.55) 100%)';
  setTimeout(() => {
    v.style.background = 'radial-gradient(ellipse at center, transparent 60%, rgba(220,30,30,0) 100%)';
  }, 200);
}

// ─── CAMERA ──────────────────────────────────────────────────────────────────
const CAM_OFFSET = new THREE.Vector3(0.6, 2.8, 5);

function updateCamera() {
  const offset = CAM_OFFSET.clone();
  offset.applyEuler(new THREE.Euler(0, yaw, 0));
  camera.position.copy(player.group.position).add(offset);

  const lookAt = player.group.position.clone().add(new THREE.Vector3(0, 1.5, 0));
  camera.lookAt(lookAt);
}

// ─── PLAYER MOVEMENT ─────────────────────────────────────────────────────────
const SPEED_WALK = 5;
const SPEED_SPRINT = 9;
const ARENA_LIMIT = 48;

function movePlayer(dt) {
  const speed = keys['ShiftLeft'] ? SPEED_SPRINT : SPEED_WALK;
  const move = new THREE.Vector3();

  if (keys['KeyW'] || keys['ArrowUp'])    move.z -= 1;
  if (keys['KeyS'] || keys['ArrowDown'])  move.z += 1;
  if (keys['KeyA'] || keys['ArrowLeft'])  move.x -= 1;
  if (keys['KeyD'] || keys['ArrowRight']) move.x += 1;

  if (move.length() > 0) {
    move.normalize().multiplyScalar(speed * dt);
    move.applyEuler(new THREE.Euler(0, yaw, 0));
    player.group.position.add(move);
  }

  player.group.position.x = Math.max(-ARENA_LIMIT, Math.min(ARENA_LIMIT, player.group.position.x));
  player.group.position.z = Math.max(-ARENA_LIMIT, Math.min(ARENA_LIMIT, player.group.position.z));

  player.group.rotation.y = yaw;

  // Bob gun
  const t = performance.now() * 0.003;
  player.gunGroup.position.y = 1.5 + Math.sin(t * 5) * (move.length() > 0 ? 0.03 : 0.008);
}

// ─── UPDATE BULLETS ───────────────────────────────────────────────────────────
const BULLET_SPEED = 40;

function updateBullets(dt) {
  for (let i = bullets.length - 1; i >= 0; i--) {
    const b = bullets[i];
    b.life -= dt;
    b.mesh.position.addScaledVector(b.dir, BULLET_SPEED * dt);

    if (b.life <= 0) {
      scene.remove(b.mesh);
      bullets.splice(i, 1);
      continue;
    }

    // Hit test against enemies
    let hit = false;
    for (let j = enemies.length - 1; j >= 0; j--) {
      const e = enemies[j];
      if (b.mesh.position.distanceTo(e.group.position.clone().add(new THREE.Vector3(0, 1, 0))) < 0.7) {
        const dmg = 20 + Math.floor(Math.random() * 10);
        e.hp -= dmg;
        hit = true;

        // Update enemy health bar
        const pct = Math.max(0, e.hp / e.maxHp);
        e.hbFill.scale.x = pct;
        e.hbFill.position.x = -(1 - pct) * 0.39;

        if (e.hp <= 0) {
          scene.remove(e.group);
          enemies.splice(j, 1);
          state.score += 100 + state.wave * 50;
          updateScoreHUD();
          addKillMsg();
          spawnDeathEffect(b.mesh.position);
        }
        break;
      }
    }

    if (hit) {
      scene.remove(b.mesh);
      bullets.splice(i, 1);
    }
  }
}

function spawnDeathEffect(pos) {
  for (let k = 0; k < 8; k++) {
    const p = new THREE.Mesh(
      new THREE.SphereGeometry(0.08, 4, 4),
      new THREE.MeshBasicMaterial({ color: 0xe74c3c })
    );
    p.position.copy(pos);
    scene.add(p);
    const vel = new THREE.Vector3((Math.random()-0.5)*6, Math.random()*5+1, (Math.random()-0.5)*6);
    let life = 0.5;
    const tick = () => {
      if (!state.running) { scene.remove(p); return; }
      p.position.addScaledVector(vel, 0.016);
      vel.y -= 9.8 * 0.016;
      life -= 0.016;
      if (life > 0) requestAnimationFrame(tick);
      else scene.remove(p);
    };
    requestAnimationFrame(tick);
  }
}

// ─── UPDATE ENEMIES ───────────────────────────────────────────────────────────
function updateEnemies(dt) {
  const pPos = player.group.position;

  for (let i = 0; i < enemies.length; i++) {
    const e = enemies[i];

    // Face and move toward player
    const diff = new THREE.Vector3().subVectors(pPos, e.group.position);
    diff.y = 0;
    const dist = diff.length();
    e.group.rotation.y = Math.atan2(diff.x, diff.z);

    if (dist > 1.2) {
      diff.normalize().multiplyScalar(e.speed * dt);
      e.group.position.add(diff);
    }

    // Health bar faces camera
    e.hbFill.parent.children
      .filter(c => c.geometry && c.geometry.type === 'PlaneGeometry')
      .forEach(c => c.lookAt(camera.position));

    // Attack player
    e.attackTimer -= dt;
    if (dist < 1.5 && e.attackTimer <= 0) {
      e.attackTimer = 1.2;
      state.hp -= 8 + state.wave * 2;
      state.hp = Math.max(0, state.hp);
      updateHpHUD();
      flashDamage();
      if (state.hp <= 0) endGame();
    }
  }
}

// ─── WAVE SYSTEM ──────────────────────────────────────────────────────────────
function updateWaves(dt) {
  if (enemies.length === 0) {
    waveTimer -= dt;
    if (waveTimer <= 0) {
      state.wave++;
      updateScoreHUD();
      spawnEnemyRing();
      waveTimer = 5;
    }
  }
}

// ─── GAME LOOP ────────────────────────────────────────────────────────────────
let lastTime = 0;

function loop(time) {
  if (!state.running) return;
  const dt = Math.min((time - lastTime) / 1000, 0.05);
  lastTime = time;

  // Reload timer
  if (state.reloading) {
    state.reloadTime -= dt;
    if (state.reloadTime <= 0) finishReload();
  }

  // Shoot cooldown
  if (state.shootCooldown > 0) state.shootCooldown -= dt;

  movePlayer(dt);
  updateCamera();
  updateBullets(dt);
  updateEnemies(dt);
  updateWaves(dt);

  renderer.render(scene, camera);
  requestAnimationFrame(loop);
}

// ─── START / END ──────────────────────────────────────────────────────────────
function startGame() {
  document.getElementById('overlay').style.display = 'none';
  state.hp = 100;
  state.score = 0;
  state.wave = 1;
  state.ammo = 30;
  state.reserve = 90;
  state.reloading = false;
  state.gameOver = false;
  state.shootCooldown = 0;

  player.group.position.set(0, 0, 0);
  yaw = 0;

  // Clear old enemies
  enemies.forEach(e => scene.remove(e.group));
  enemies.length = 0;
  bullets.forEach(b => scene.remove(b.mesh));
  bullets.length = 0;

  waveTimer = 1;
  updateHpHUD();
  updateAmmoHUD();
  updateScoreHUD();
  document.getElementById('reload-indicator').style.display = 'none';

  state.running = true;
  lastTime = performance.now();
  requestAnimationFrame(loop);
  canvas.requestPointerLock();
}

function endGame() {
  state.running = false;
  state.gameOver = true;
  document.exitPointerLock();

  const overlay = document.getElementById('overlay');
  overlay.innerHTML = `
    <h1>GAME OVER</h1>
    <div class="sub">WAVE REACHED: ${state.wave}</div>
    <div class="final-score">SCORE: ${state.score}</div>
    <button id="start-btn">PLAY AGAIN</button>
  `;
  overlay.style.display = 'flex';
  document.getElementById('start-btn').addEventListener('click', startGame);
}

document.getElementById('start-btn').addEventListener('click', startGame);
