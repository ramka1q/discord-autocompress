/* Moon: місяць + промені + пил + зорі + падаюча зірка + зерно. Рендер у половинній
   роздільності, 60 кадрів/с (requestAnimationFrame). Кнопки підсвічуються, коли на них
   падає промінь (раз на 90 мс). Лише чорний/білий/сірий. */
(function () {
  const cv = document.getElementById("sky");
  const ctx = cv.getContext("2d");
  const DPR = 0.5;                       // половинна роздільність -> у 4 рази легше
  let W = 0, H = 0, R = 110, MX = 0, MY = 0;
  let bass = 0;                          // «подих» (повільна псевдо-пульсація)
  const rnd = mulberry(20261119);

  function mulberry(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  // ---------- текстура місяця 720×720 (малюється один раз) ----------
  const TEX = document.createElement("canvas"); TEX.width = TEX.height = 720;
  (function paintMoon() {
    const c = TEX.getContext("2d"), S = 720, r = S / 2;
    c.save(); c.beginPath(); c.arc(r, r, r, 0, Math.PI * 2); c.clip();
    let g = c.createRadialGradient(r * 0.55, r * 1.45, r * 0.1, r * 0.8, r * 1.1, r * 1.5);   // світло знизу зліва
    g.addColorStop(0, "#fbfaf6"); g.addColorStop(1, "#a9a7a0");
    c.fillStyle = g; c.fillRect(0, 0, S, S);
    c.filter = "blur(14px)";                                         // моря
    for (let i = 0; i < 8; i++) {
      c.fillStyle = "rgba(70,70,66,0.40)";
      c.beginPath(); c.ellipse(S * (0.25 + rnd() * 0.5), S * (0.2 + rnd() * 0.5), S * (0.07 + rnd() * 0.12),
        S * (0.05 + rnd() * 0.1), rnd() * 3, 0, Math.PI * 2); c.fill();
    }
    c.filter = "none";
    function crater(x, y, rr, k) {
      const o = rr * 0.16;
      c.fillStyle = `rgba(255,255,250,${0.30 * k})`; c.beginPath(); c.arc(x + o, y - o, rr, 0, 7); c.fill();   // світлий обідок згори справа
      c.fillStyle = `rgba(40,40,38,${0.34 * k})`; c.beginPath(); c.arc(x - o, y + o, rr, 0, 7); c.fill();     // темний край знизу зліва
      c.fillStyle = `rgba(150,149,144,${0.25 * k})`; c.beginPath(); c.arc(x, y, rr * 0.82, 0, 7); c.fill();
    }
    for (let i = 0; i < 8; i++) { const a = rnd() * 6.28, d = rnd() * 0.72 * r; crater(r + Math.cos(a) * d, r + Math.sin(a) * d, S * (0.04 + rnd() * 0.045), 1); }
    for (let i = 0; i < 70; i++) { const a = rnd() * 6.28, d = rnd() * 0.9 * r; crater(r + Math.cos(a) * d, r + Math.sin(a) * d, S * (0.005 + rnd() * 0.013), 0.8); }
    const yx = r * 0.62, yy = r * 1.32;                              // молодий кратер з 26 смугами
    c.strokeStyle = "rgba(252,251,247,0.45)"; c.lineWidth = 2.2; c.filter = "blur(1.2px)";
    for (let i = 0; i < 26; i++) { const a = i / 26 * 6.28 + (rnd() - 0.5) * 0.2, L = (0.25 + rnd() * 0.45) * r;
      c.beginPath(); c.moveTo(yx, yy); c.lineTo(yx + Math.cos(a) * L, yy + Math.sin(a) * L); c.stroke(); }
    c.filter = "none"; c.fillStyle = "#fffffc"; c.beginPath(); c.arc(yx, yy, S * 0.014, 0, 7); c.fill();
    g = c.createRadialGradient(r, r, r * 0.55, r, r, r);             // потемніння країв
    g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(0,0,0,0.38)");
    c.fillStyle = g; c.fillRect(0, 0, S, S);
    g = c.createLinearGradient(S, 0, S * 0.35, S * 0.65);             // тінь згори справа
    g.addColorStop(0, "rgba(0,0,0,0.32)"); g.addColorStop(1, "rgba(0,0,0,0)");
    c.fillStyle = g; c.fillRect(0, 0, S, S);
    const id = c.getImageData(0, 0, S, S), d = id.data;             // зерно ±7
    for (let i = 0; i < d.length; i += 4) { const n = (rnd() - 0.5) * 14; d[i] += n; d[i + 1] += n; d[i + 2] += n; }
    c.putImageData(id, 0, 0); c.restore();
  })();

  // ---------- заготовка променя: вузька біля місяця, широка далі, м'які краї ----------
  const RAY = document.createElement("canvas"); RAY.width = 1024; RAY.height = 160;
  (function paintRay() {
    const c = RAY.getContext("2d");
    c.filter = "blur(10px)";
    const g = c.createLinearGradient(0, 0, 1024, 0);
    // м'яке згасання по довжині (без різкого обриву): ~експонента до нуля в самому кінці
    g.addColorStop(0, "rgba(255,255,250,0.0)"); g.addColorStop(0.05, "rgba(255,255,250,0.9)");
    for (let i = 1; i <= 10; i++) { const x = 0.05 + 0.95 * i / 10; g.addColorStop(x, `rgba(255,255,250,${(0.9 * Math.pow(1 - i / 10, 1.8)).toFixed(3)})`); }
    c.fillStyle = g; c.beginPath(); c.moveTo(0, 80); c.lineTo(1024, 20); c.lineTo(1024, 140); c.closePath(); c.fill();
  })();
  const GRAIN = document.createElement("canvas"); GRAIN.width = GRAIN.height = 256;
  (function () { const c = GRAIN.getContext("2d"), id = c.createImageData(256, 256);
    for (let i = 0; i < id.data.length; i += 4) { const v = rnd() * 255; id.data[i] = id.data[i + 1] = id.data[i + 2] = v; id.data[i + 3] = 255; }
    c.putImageData(id, 0, 0); })();

  const RAYS = [];
  for (let i = 0; i < 17; i++) RAYS.push({ base: 135 + (i - 8) * 6.2 + (rnd() - 0.5) * 3, main: i % 4 === 0,
    p1: rnd() * 6.28, p2: rnd() * 6.28, p3: rnd() * 6.28, f1: 0.07 + rnd() * 0.05, f2: 0.13 + rnd() * 0.08,
    k: i % 4 === 0 ? 0.55 : 0.18 + rnd() * 0.14, ang: 0 });
  const STARS = [], DUST = [];
  for (let i = 0; i < 150; i++) STARS.push({ x: rnd(), y: rnd(), b: 0.3 + rnd() * 0.7, ph: rnd() * 6.28, sp: 0.5 + rnd() * 1.5, v: 0.002 + rnd() * 0.006 });
  for (let i = 0; i < 150; i++) DUST.push({ x: rnd(), y: rnd(), vx: (rnd() - 0.5) * 0.004, vy: (rnd() - 0.5) * 0.004, s: 0.6 + rnd() * 1.2 });
  let shoot = null, nextShoot = 6 + rnd() * 10;

  function resize() {
    W = Math.max(2, Math.round(innerWidth * DPR)); H = Math.max(2, Math.round(innerHeight * DPR));
    cv.width = W; cv.height = H;
    R = Math.max(110, 0.2 * Math.min(innerWidth, innerHeight)) * DPR;   // 20% меншої сторони, ≥110 px
    MX = W - R * 0.25; MY = R * 0.35;                                   // наполовину за краєм
  }
  addEventListener("resize", resize); resize();

  function rayLight(px, py) {            // наскільки промінь падає на точку (0..1), у CSS-пікселях
    const dx = px * DPR - MX, dy = py * DPR - MY, d = Math.hypot(dx, dy);
    if (d < R) return 1;
    const a = Math.atan2(dy, dx) * 180 / Math.PI;
    let best = 0;
    for (const r of RAYS) {
      let da = Math.abs(((a - r.ang + 540) % 360) - 180);
      const w = (r.main ? 4.2 : 2.6) * (0.5 + Math.min(1.5, d / (R * 4)) * 0.6);
      best = Math.max(best, Math.exp(-((da / w) ** 2)) * r.k * Math.exp(-d / (R * (r.main ? 9 : 6))) * 2.2);
    }
    return Math.min(1, best);
  }
  window.MoonRayLight = rayLight;

  let t0 = performance.now(), last = t0, lastGlow = 0;
  function frame(now) {
    const t = (now - t0) / 1000, dt = Math.min(0.05, (now - last) / 1000); last = now;
    bass = 0.5 + 0.5 * Math.sin(t * 2.1) * Math.sin(t * 0.7);
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
    // зорі: мерехтять і повільно пливуть угору
    for (const s of STARS) {
      s.y -= s.v * dt * 0.2; if (s.y < 0) { s.y = 1; s.x = rnd(); }
      const a = s.b * (0.55 + 0.45 * Math.sin(t * s.sp + s.ph));
      ctx.fillStyle = `rgba(245,245,242,${a * 0.8})`; ctx.fillRect(s.x * W, s.y * H, 1, 1);
    }
    const fx = MX + R * 0.06 * Math.sin(t * 0.21) + R * 0.02 * Math.sin(t * 0.53);   // місяць ледь плаває
    const fy = MY + R * 0.05 * Math.cos(t * 0.17) + R * 0.02 * Math.sin(t * 0.41);
    ctx.globalCompositeOperation = "lighter";
    let g = ctx.createRadialGradient(fx, fy, R * 0.6, fx, fy, R * 4.2);          // широке сяйво
    g.addColorStop(0, "rgba(245,245,240,0.16)"); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    for (const r of RAYS) {                                                      // промені (адитивно)
      r.ang = r.base + 2.4 * Math.sin(t * r.f1 + r.p1) + 1.1 * Math.sin(t * r.f2 + r.p2) + 0.5 * Math.sin(t * 0.9 + r.p3);
      const fl = 0.8 + 0.2 * Math.sin(t * 1.7 + r.p2) * Math.sin(t * 0.6 + r.p3);
      const len = Math.max(W, H) * (r.main ? 1.5 : 1.15), wid = len * (r.main ? 0.17 : 0.11);
      ctx.save(); ctx.translate(fx, fy); ctx.rotate(r.ang * Math.PI / 180);
      ctx.globalAlpha = r.k * fl * (0.9 + bass * 0.15);
      ctx.drawImage(RAY, R * 0.7, -wid / 2, len, wid); ctx.restore();
    }
    ctx.globalAlpha = 1;
    // пил: майже невидимий, спалахує в промені
    for (const p of DUST) {
      p.x += p.vx * dt; p.y += p.vy * dt; if (p.x < 0) p.x += 1; if (p.x > 1) p.x -= 1; if (p.y < 0) p.y += 1; if (p.y > 1) p.y -= 1;
      const L = rayLight(p.x * W / DPR, p.y * H / DPR);
      if (L > 0.02) { ctx.fillStyle = `rgba(255,255,250,${Math.min(0.9, L * 1.4)})`; ctx.fillRect(p.x * W, p.y * H, p.s, p.s); }
    }
    g = ctx.createRadialGradient(fx, fy, R * 0.95, fx, fy, R * 1.35);           // щільна корона
    g.addColorStop(0, "rgba(255,255,250,0.42)"); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(fx, fy, R * 1.4, 0, 7); ctx.fill();
    // падаюча зірка
    nextShoot -= dt;
    if (!shoot && nextShoot <= 0) { shoot = { x: rnd() * W * 0.6, y: rnd() * H * 0.4, vx: W * 0.6, vy: H * 0.25, life: 0.9 }; nextShoot = 9 + rnd() * 16; }
    if (shoot) {
      shoot.life -= dt; shoot.x += shoot.vx * dt; shoot.y += shoot.vy * dt;
      const gl = ctx.createLinearGradient(shoot.x, shoot.y, shoot.x - shoot.vx * 0.12, shoot.y - shoot.vy * 0.12);
      gl.addColorStop(0, `rgba(255,255,250,${Math.max(0, shoot.life)})`); gl.addColorStop(1, "rgba(0,0,0,0)");
      ctx.strokeStyle = gl; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(shoot.x, shoot.y);
      ctx.lineTo(shoot.x - shoot.vx * 0.12, shoot.y - shoot.vy * 0.12); ctx.stroke();
      if (shoot.life <= 0) shoot = null;
    }
    ctx.globalCompositeOperation = "source-over";
    const rr = R * (1 + 0.035 * bass);                                          // «дихає»
    ctx.save(); ctx.translate(fx, fy); ctx.rotate(5 * Math.sin(t * 0.13) * Math.PI / 180);
    ctx.drawImage(TEX, -rr, -rr, rr * 2, rr * 2); ctx.restore();
    ctx.globalAlpha = 0.05; ctx.globalCompositeOperation = "overlay";          // зерно плівки 5%
    ctx.drawImage(GRAIN, (t * 37) % 256 - 256, (t * 53) % 256 - 256, W + 512, H + 512);
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
    if (now - lastGlow > 90) {                                                   // підсвітка кнопок променями
      lastGlow = now;
      for (const el of document.querySelectorAll(".btn, .play, .chip-btn")) {
        const b = el.getBoundingClientRect();
        if (!b.width) continue;
        el.style.setProperty("--ray", rayLight(b.left + b.width / 2, b.top + b.height / 2).toFixed(2));
      }
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
