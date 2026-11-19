/* Меню / галерея / «Що нового» в дизайні Moon. Дані — з /api/state, дії — /api/do,
   прогрес довгих дій — /api/poll. Тексти — ті самі переклади, що й у програмі. */
"use strict";
const TOKEN = new URLSearchParams(location.search).get("t") || "";
let ST = null, S = {}, PAGE = "menu", TAB = "general", LAST_EV = 0;
const live = {};                     // стан довгих дій (оновлення, тести) — переживає перемикання вкладок

const $ = (sel, el = document) => el.querySelector(sel);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function T(k, f) { let s = S[k] ?? k; if (f) for (const [a, b] of Object.entries(f)) s = s.split("{" + a + "}").join(b); return s; }
function api(path, body) {
  const o = { headers: { "X-Token": TOKEN } };
  if (body !== undefined) { o.method = "POST"; o.body = JSON.stringify(body); o.headers["Content-Type"] = "application/json"; }
  return fetch(path, o).then(r => r.json());
}
const act = (action, args) => api("/api/do", { action, args });
function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.add("on"); clearTimeout(toast.h); toast.h = setTimeout(() => el.classList.remove("on"), 1600); }
function fmtMB(mb) { return mb >= 1024 ? (mb / 1024).toFixed(2) + " " + T("unit_gb") : (+mb).toFixed(1) + " " + T("unit_mb"); }
function fmtDate(d) { const [a, t] = String(d).split(" "); const [y, m, dd] = (a || "").split("-"); return [`${dd}.${m}.${y}`, t || ""]; }
function released() { const [d, t] = fmtDate(ST.released); return T("released", { d, t }); }
function ts(t, withYear) { const d = new Date(t * 1000), p = n => String(n).padStart(2, "0");
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}${withYear ? "." + d.getFullYear() : ""} ${p(d.getHours())}:${p(d.getMinutes())}`; }
const LOGO = `<svg viewBox="0 0 24 24" fill="none" stroke="#f5f5f2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v10M7.5 10 12 14.5 16.5 10M6 19h12"/></svg>`;

// ---------- маленькі компоненти ----------
function toggle(key) { return `<label class="sw"><input type="checkbox" data-k="${key}" ${ST.cfg[key] ? "checked" : ""}><i></i></label>`; }
function row(title, desc, key) { return `<div class="row"><div class="tx"><b>${esc(title)}</b>${desc ? `<span>${esc(desc)}</span>` : ""}</div>${toggle(key)}</div>`; }
function seg(key, opts) {
  return `<div class="seg" data-seg="${key}">` + opts.map(([v, l, sub]) =>
    `<button data-v="${esc(v)}" class="${String(ST.cfg[key]) === String(v) ? "on" : ""}">${esc(l)}${sub !== undefined ? `<small>${esc(sub || " ")}</small>` : ""}</button>`).join("") + "</div>";
}
function card(label, sub, inner) { return `<section class="glass card rise">${label ? `<span class="label">${esc(label)}</span>` : ""}${sub ? `<p class="sub">${esc(sub)}</p>` : (label ? "<div style='height:10px'></div>" : "")}${inner}</section>`; }

async function setCfg(k, v) {
  ST.cfg[k] = v;
  const r = await api("/api/set", { [k]: v });
  if (r.reload) return location.reload();
  toast(T("saved"));
}

// ---------- сторінки меню ----------
const TABS = [["general", "tab_general", "⚙"], ["gpu", "tab_gpu", "◐"], ["media", "tab_media", "▤"], ["stats", "tab_stats", "▥"],
  ["appearance", "tab_appearance", "◑"], ["whatsnew", "tab_whatsnew", "✦"], ["setup", "tab_setup", "⬡"], ["updates", "tab_updates", "⟳"],
  ["performance", "tab_performance", "ϟ"], ["facts", "tab_facts", "✧"], ["about", "tab_about", "ⓘ"]];
const HEADS = { general: ["tab_general", "st_general_sub"], media: ["tab_media", "st_media_sub"], stats: ["stats_title", "st_stats_sub"],
  appearance: ["tab_appearance", "st_appearance_sub"], setup: ["setup_title", "setup_hint"], updates: ["tab_updates", "update_hint"],
  performance: ["tab_performance", "perf_hint"], facts: ["facts_title", "facts_hint"], about: ["tab_about", null], gpu: ["tab_gpu", "st_gpu_sub"],
  whatsnew: ["tab_whatsnew", "st_whatsnew_sub"] };

const PAGES = {
  general() {
    const s = ST.stats;
    let h = `<section class="glass hero rise"><div class="plus" data-do="open_editor" title="${esc(T("st_editor_open"))}">+</div><div style="flex:1">
      <h3>${esc(T("st_ready"))}</h3><div class="muted">${esc(T("st_ready_body", { mb: ST.cfg.target_mb }))}</div>
      ${s.files ? `<div class="stats label dim">${esc(T("st_ready_stats", { files: s.files, saved: fmtMB(s.saved_mb) }))}</div>` : ""}</div></section>`;
    h += card(T("st_editor_title"), T("st_editor_sub"), `<div class="btns"><button class="btn primary" data-do="open_editor">${esc(T("st_editor_open"))}</button>
      <button class="btn" data-do="open_gallery">${esc(T("st_editor_gallery"))}</button></div>`);
    h += card(T("limit_title"), T("st_limit_sub"), seg("target_mb", [[20, "20 " + T("unit_mb"), T("lim_free")], [25, "25 " + T("unit_mb"), ""],
      [50, "50 " + T("unit_mb"), T("lim_basic")], [500, "500 " + T("unit_mb"), T("lim_nitro")]]));
    h += card(T("st_behavior"), "", row(T("opt_autoscale"), T("st_autoscale_d"), "auto_scale") + row(T("opt_block"), T("st_block_d"), "block_paste")
      + row(T("opt_paste"), T("st_paste_d"), "auto_paste"));
    const a = ST.cfg.audio_kbps;
    h += card(T("st_audio"), T("st_audio_d"), `<div class="slider"><input type="range" min="0" max="320" step="32" value="${a}" data-range="audio_kbps">
      <span class="val" id="audio_val">${a ? a + " kbps" : esc(T("audio_off"))}</span></div><div class="ticks"><span>0</span><span>160</span><span>320</span></div>`);
    return h;
  },
  media() {
    let h = card(T("media_title"), "", row(T("media_video"), T("st_video_d"), "compress_video") + row(T("media_image"), T("st_image_d"), "compress_images")
      + row(T("media_audio"), T("st_audio2_d"), "compress_audio"));
    h += card(T("st_extras"), "", row(T("opt_shrink"), T("st_shrink_d"), "offer_shrink") + row(T("opt_notify"), T("st_notify_d"), "notify_done")
      + row(T("opt_sound"), "", "sound_done") + `<div class="btns" style="margin-top:12px"><button class="btn sm" data-do="pick_sound">${esc(T("sound_pick"))}</button>
      <button class="btn sm" data-do="reset_sound">${esc(T("sound_win"))}</button><span class="muted">${esc(ST.sound_custom ? T("sound_custom") : T("sound_windows"))}</span></div>`);
    h += card(T("keep_title"), T("st_keep_d"), seg("keep_local", [["ask", T("keep_ask")], ["always", T("keep_always")], ["never", T("keep_never")]]));
    return h;
  },
  stats() {
    const s = ST.stats;
    let h = s.since ? `<p class="muted" style="margin:0 0 12px 4px">${esc(T("stats_since", { d: ts(s.since, true).split(" ")[0] }))}</p>` : "";
    h += `<div class="grid3">` + [[s.files, T("stats_files")], [fmtMB(s.saved_mb), T("stats_saved")], [s.avg != null ? "−" + s.avg + "%" : "—", T("stats_avg")]]
      .map(([b, l]) => `<section class="glass card rise" style="margin:0"><span class="label dim">${esc(l)}</span><div class="big">${esc(b)}</div></section>`).join("") + `</div>`;
    const bk = s.by_kind || {}, tot = Object.values(bk).reduce((a, b) => a + (+b), 0);
    if (tot) h += card(T("st_by_type"), "", [["video", T("media_video")], ["image", T("media_image")], ["audio", T("media_audio")]].map(([k, n]) =>
      `<div style="display:flex;justify-content:space-between"><span>${esc(n)}</span><b>${bk[k] || 0}</b></div><div class="kbar"><i style="width:${(100 * (bk[k] || 0) / tot).toFixed(1)}%"></i></div>`).join(""));
    if (!s.history.length) return h + card(T("stats_hist"), "", `<p class="muted">${esc(T("stats_empty"))}</p>`);
    h += card(T("stats_hist"), T("stats_hint"), `<div class="list" id="hist">` + s.history.map(e => `<div class="li" data-i="${e.i}">
        <span class="when">${esc(ts(e.t))}</span><span class="nm">${esc(e.name)}</span><span class="mb">${(+e.orig).toFixed(1)} → ${(+e.final).toFixed(1)} ${esc(T("unit_mb"))}${e.parts > 1 ? " ×" + e.parts : ""}</span></div>`).join("")
      + `</div><div class="btns" style="margin-top:12px"><button class="btn sm primary" data-hist="hist_copy">${esc(T("stats_copy"))}</button>
      <button class="btn sm" data-hist="hist_open">${esc(T("stats_open"))}</button><button class="btn sm" data-do="hist_clear" data-then="reload">${esc(T("stats_clear"))}</button>
      <span class="muted" id="hist_msg"></span></div>`);
    return h;
  },
  appearance() {
    let h = card(T("theme_title"), "", `<div class="themes">` + ST.themes.map(([k, name, bg, a1, a2]) => `<div class="theme ${ST.cfg.theme === k ? "on" : ""}" data-theme="${k}">
      <div class="pv" style="background:${bg}"><div style="position:absolute;left:12px;right:12px;bottom:12px;height:14px;border-radius:8px;background:linear-gradient(90deg,${a1},${a2})"></div>
      ${k === "mono" ? `<div style="position:absolute;right:-18px;top:-18px;width:60px;height:60px;border-radius:50%;background:radial-gradient(circle at 35% 70%,#fbfaf6,#a9a7a0);box-shadow:0 0 30px #fff8"></div>` : ""}</div>
      ${esc(name)}${ST.cfg.theme === k ? " ✓" : ""}</div>`).join("") + `</div><p class="sub" style="margin:14px 0 0">${esc(T("web_theme_note") === "web_theme_note" ? "" : T("web_theme_note"))}</p>`);
    h += card(T("lang_title"), "", seg("lang", ST.langs));
    return h;
  },
  updates() {
    const u = live.update || {};
    return card("", "", `<div style="display:flex;gap:16px;align-items:center"><div class="logo" style="width:54px;height:54px;border-radius:16px">${LOGO}</div><div>
      <div style="font:italic 400 30px/1 var(--serif)">Discord Auto-Compress <span class="vchip">v${esc(ST.version)}</span></div><div class="muted">${esc(released())}</div></div></div>
      <div class="status ${u.warn ? "warn" : ""}" id="upd_status">${esc(u.text || T("upd_idle"))}</div><div class="bar" id="upd_bar" style="${u.pct == null ? "display:none" : ""}"><i style="width:${u.pct || 0}%"></i></div>
      <div class="btns" style="margin-top:16px"><button class="btn primary" data-do="update" ${u.busy ? "disabled" : ""}>${esc(T("check_updates"))}</button></div>`);
  },
  performance() {
    const p = live.perf || {};
    return card("", "", `<button class="btn primary" data-do="perf" ${p.busy ? "disabled" : ""}>${esc(p.busy ? T("perf_running") : T("perf_run"))}</button>
      <div id="perf_box">${p.html || ""}</div>`);
  },
  facts() { return card("", "", ST.facts.map(f => `<div class="fact"><span class="label dim">✧</span><div>${esc(f)}</div></div>`).join("")); },
  setup() {
    const d = live.deps_now || ST.deps, all = Object.values(d).every(Boolean);
    return card(T("st_components"), "", Object.entries(d).map(([n, ok]) => `<div class="check"><span class="o ${ok ? "" : "no"}">${ok ? "✓" : "✗"}</span><b>${esc(n)}</b>
        <span class="muted">— ${esc(ok ? T("setup_present") : T("setup_missing"))}</span></div>`).join("")
      + `<div class="btns" style="margin-top:14px"><button class="btn primary" data-do="deps_install" ${all || live.deps_busy ? "disabled" : ""}>${esc(live.deps_busy ? T("setup_installing") : T("setup_install"))}</button>
        <button class="btn" data-do="deps_check">${esc(T("setup_recheck"))}</button></div><div class="status" id="deps_msg">${esc(all ? T("setup_all_ok") : (live.deps_msg || ""))}</div>
        <p class="sub" style="margin:8px 0 0">${esc(T("setup_manual"))}</p>`)
      + card(T("st_log"), "", `<div class="log" id="deps_log">${esc(live.deps_log || "")}</div>`);
  },
  about() {
    let h = `<section class="glass hero rise"><div class="logo" style="width:72px;height:72px;border-radius:22px">${LOGO}</div><div><h3>Discord Auto-Compress</h3>
      <div class="muted">${esc(T("st_tagline"))}</div><div class="label dim" style="margin-top:10px">v${esc(ST.version)} · ${esc(released())} · MIT</div></div></section>`;
    h += card(T("st_how"), "", `<div class="muted" style="white-space:pre-line">${esc(T("about_body"))}</div>`);
    h += card(T("st_report_title"), T("st_report_d"), `<div class="btns"><button class="btn primary" data-do="report">${esc(T("st_report_btn"))}</button><span class="muted" id="report_msg">${esc(live.report || "")}</span></div>`);
    h += card(T("st_donate_title"), T("st_donate_d"), `<div class="btns">${ST.donate ? `<button class="btn primary" data-do="donate">${esc(T("st_donate_btn"))}</button>` : ""}
      <button class="btn" data-url="${esc(ST.repo)}">GitHub ↗</button></div>`);
    h += `<p class="label dim" style="margin:6px 8px">Fonts: Instrument Serif, Manrope, JetBrains Mono, Cormorant — SIL OFL 1.1</p>`;
    return h;
  },
  gpu() {
    const g = live.gpu || ST.gpu, enc = n => (!n || n === "x264") ? T("enc_cpu_name") : (g.names[n] || n);
    let now = T("st_gpu_checking");
    if (g.known) {
      const m = ST.cfg.encoder, best = ST.cfg.encoder_best || "";
      const e = (m === "cpu" || !g.hw) ? "x264" : (m === "gpu" ? g.hw : (best === "x264" ? "x264" : g.hw));
      now = T("st_gpu_now", { name: enc(e) }) + (m === "gpu" && !g.hw ? "  ·  " + T("st_dev_gpu_no") : "");
    }
    let h = card(T("st_enc_title"), T("st_enc_d"), seg("encoder", [["auto", T("enc_auto")], ["gpu", T("enc_gpu")], ["cpu", T("enc_cpu")]]) + `<div class="status" id="gpu_now">${esc(now)}</div>`);
    h += card(T("st_devices"), "", g.known ? [[true, T("enc_cpu_name"), T("st_dev_cpu", { n: ST.cpu })], [!!g.hw, g.hw ? g.hw_name : T("st_dev_gpu_none"), g.hw ? T("st_dev_gpu_ok") : T("st_dev_gpu_no")]]
      .map(([ok, n, note]) => `<div class="check"><span class="o ${ok ? "" : "no"}">${ok ? "✓" : "—"}</span><b>${esc(n)}</b><span class="muted">— ${esc(note)}</span></div>`).join("")
      : `<p class="muted">${esc(T("st_gpu_checking"))}</p>`);
    const b = live.bench || {};
    h += card(T("st_bench_title"), T("st_bench_d"), `<button class="btn primary" data-do="bench" ${b.busy ? "disabled" : ""}>${esc(b.busy ? T("st_bench_running") : T("st_bench_btn"))}</button>
      <div class="bar" id="bench_bar" style="${b.busy ? "" : "display:none"}"><i style="width:${b.pct || 0}%"></i></div><div id="bench_box">${benchHTML(ST.cfg.bench, ST.cfg.bench_at, enc)}</div>`);
    if (!g.known && !live.gpu_asked) { live.gpu_asked = true; act("gpu"); }
    return h;
  },
  whatsnew() {
    let h = `<div class="btns rise" style="margin:0 0 16px 4px"><button class="btn primary" data-do="whatsnew_popup">${esc(T("wn_replay"))}</button>
      <button class="btn" data-url="${esc(ST.release_url)}">${esc(T("wn_site"))}</button></div>`;
    for (const e of ST.news) { const [d, t] = fmtDate(e.date); h += card("v" + e.v, T("released", { d, t }), newsItems(e.items, true)); }
    return h;
  },
};

function newsItems(items, withShow, ver) {
  return items.map(it => `<div class="news-item"><span class="ico">${esc(it.icon)}</span><div class="tx"><b>${esc(it.title)}${ver ? ` <span class="label dim">· v${esc(ver)}</span>` : ""}</b><span>${esc(it.desc)}</span></div>
    ${withShow && it.tab && it.tab !== "whatsnew" ? `<button class="btn sm" data-tab="${esc(it.tab)}">${esc(T("wn_show"))}</button>` : ""}</div>`).join("");
}
function benchHTML(res, at, enc) {
  res = res || []; const ok = res.filter(r => r.sec); if (!res.length) return "";
  if (!ok.length) return `<div class="status">${esc(T("st_bench_fail"))}</div>`;
  const slow = Math.max(...ok.map(r => r.sec)), best = ok[0];
  let h = res.map((r, i) => `<div style="margin-top:12px;display:flex;justify-content:space-between"><b>${i === 0 && r.sec ? "★ " : ""}${esc(enc(r.enc))}</b>
    <span class="label" style="letter-spacing:0">${r.sec ? r.sec.toFixed(1) + " " + esc(T("unit_sec")) : esc(T("st_bench_err"))}</span></div>
    <div class="kbar"><i style="width:${r.sec ? (100 * r.sec / slow).toFixed(1) : 0}%;${i ? "background:#5d5d5b" : ""}"></i></div>`).join("");
  let msg = T("st_bench_result", { name: enc(best.enc) });
  if (ok.length > 1) msg += "  " + T("st_bench_faster", { x: (slow / best.sec).toFixed(1) });
  if (at) msg += "\n" + T("st_bench_when", { d: at });
  return h + `<div class="status" style="white-space:pre-line">${esc(msg)}</div>`;
}

// ---------- каркас меню ----------
function renderMenu() {
  document.title = "Discord Auto-Compress";
  const [tk, sk] = HEADS[TAB] || HEADS.general;
  $("#app").innerHTML = `<header class="top"><div class="brand"><div class="logo">${LOGO}</div><h1>Discord Auto-Compress</h1><span class="vchip">v${esc(ST.version)}</span></div>
    <span class="label dim" style="margin-left:6px">${esc(released())}</span><div class="spacer"></div>
    <button class="btn" data-do="open_gallery">${esc(T("st_editor_gallery"))}</button><button class="btn primary" data-do="open_editor">${esc(T("st_editor_open"))}</button></header>
    <div class="layout"><nav class="glass side rise"><span class="label">Menu</span>
      ${TABS.map(([k, tkey, ic]) => `<div class="nav ${k === TAB ? "on" : ""}" data-tab="${k}"><span class="ic">${ic}</span>${esc(T(tkey))}${k === "gpu" && !ST.cfg.gpu_seen_web && !ST.gpu_seen ? "" : ""}</div>`).join("")}
      <div class="foot"><b><span class="pulse"></span>${esc(T("st_status_on"))}</b>${esc(T("st_status_hint"))}<div style="margin-top:8px" class="dimc">${esc(T("autosave_hint"))}</div></div></nav>
    <main class="main" id="main"><div class="page-head rise"><span class="label dim">Discord Auto-Compress</span><h2>${esc(T(tk))}</h2>${sk ? `<p>${esc(T(sk))}</p>` : ""}</div>
      ${(PAGES[TAB] || PAGES.general)()}</main></div>`;
}

// ---------- галерея ----------
function renderGallery() {
  document.title = "My edits — Discord Auto-Compress";
  const items = ST.lib;
  $("#app").innerHTML = `<header class="top"><div class="brand"><div class="logo">${LOGO}</div><h1>${esc(T("lib_title"))}</h1><span class="vchip">${esc(ST.hotkey)}</span></div>
    <div class="spacer"></div><button class="btn" data-do="lib_folder">${esc(T("lib_folder"))}</button><button class="btn primary" data-do="open_editor" data-then="close">${esc(T("lib_new"))}</button></header>
    <div class="main" style="padding:0 22px"><p class="label dim" style="margin:6px 4px 14px">${esc(T("lib_hint"))}</p>
    ${items.length ? `<div class="gal-grid">` + items.map((it, i) => `<div class="glass gal rise" style="animation-delay:${Math.min(i, 12) * 40}ms" data-paste="${esc(it.path)}">
      <div class="pic" ${it.audio ? "" : `style="background-image:url('/api/thumb?t=${encodeURIComponent(TOKEN)}&p=${encodeURIComponent(it.path)}')"`}>${it.audio ? "♪" : ""}</div>
      <div class="nm">${esc(it.name)}</div><div class="meta"><span>${it.mb.toFixed(1)} ${esc(T("unit_mb"))} · ${esc(ts(it.t))}</span><span class="spacer"></span>
      <button class="icon-btn" data-lib="lib_play" data-p="${esc(it.path)}" title="▶">▶</button><button class="icon-btn" data-lib="lib_edit" data-p="${esc(it.path)}" title="✂">✂</button></div></div>`).join("") + `</div>`
      : `<div class="empty glass"><div class="plus" data-do="open_editor" style="margin:0 auto 18px">+</div>${esc(T("lib_empty"))}</div>`}</div>`;
}

// ---------- «Що нового» (вікно після оновлення) ----------
function renderNews() {
  document.title = "What's new — Discord Auto-Compress";
  let entries = ST.news.slice(0, 1), since = ST.news_since;
  if (since) { const i = ST.news.findIndex(e => e.v === since); if (i > 0) entries = ST.news.slice(0, i); else since = null; }
  const many = entries.length > 1, [d, t] = fmtDate(entries[0].date);
  const title = many ? T("wn_title_from", { a: since, v: entries[0].v }) : T("wn_title", { v: entries[0].v });
  const sub = many ? T("wn_sub_many", { n: entries.length }) : T("wn_sub", { d, t });
  $("#app").innerHTML = `<div class="news-page"><div class="page-head rise" style="text-align:center;padding-top:60px"><div class="logo" style="width:70px;height:70px;border-radius:22px;margin:0 auto 10px">${LOGO}</div>
    <h2>${esc(title)}</h2><p style="margin:0 auto">${esc(sub)}</p></div>
    ${entries.map(e => `<section class="glass card rise">${newsItems(e.items, true, many ? e.v : null)}</section>`).join("")}
    <div class="btns" style="justify-content:center;margin-top:8px"><button class="btn primary" data-url="${esc(ST.release_url)}">${esc(T("wn_site"))}</button>
    <button class="btn" data-tab-menu="whatsnew">${esc(T("wn_inapp"))}</button></div></div>`;
}

// ---------- вікно стиснення: сцену шле програма (webov.py) ----------
let OVS = null, OV_KEY = "";
function col(c) {           // будь-який колір із Tk -> тільки білий/сірий (дизайн Moon)
  if (!c || c[0] !== "#" || c.length < 7) return "var(--text)";
  const r = parseInt(c.slice(1, 3), 16), g = parseInt(c.slice(3, 5), 16), b = parseInt(c.slice(5, 7), 16);
  const l = 0.299 * r + 0.587 * g + 0.114 * b;
  return l > 200 ? "var(--text)" : l > 120 ? "var(--muted)" : "var(--dim)";
}
const emo = s => s.replace(/(\p{Extended_Pictographic}️?)/gu, '<span class="em">$1</span>');
function renderOverlay() {
  document.title = "DAC Overlay";
  document.body.classList.add("ov");
  const sc = OVS;
  if (!sc) { $("#app").innerHTML = ""; OV_KEY = ""; return; }
  const key = sc.screen + "|" + sc.buttons.map(b => b.id).join(",");
  const fresh = key !== OV_KEY; OV_KEY = key;
  let h = `<div class="ovc"><div class="hd" id="ovdrag"><div class="logo">${LOGO}</div><span class="label">AUTO-COMPRESS</span></div><div class="x" data-ov="esc">✕</div>`;
  if (sc.badge) h += `<div class="el badge ${fresh ? "fadein" : ""}" style="left:${sc.badge.cx}px;top:${sc.badge.cy}px;width:${sc.badge.R * 2}px;height:${sc.badge.R * 2}px;font-size:${Math.round(sc.badge.R * .75)}px">${emo(esc(sc.badge.icon))}</div>`;
  if (sc.done) h += `<div class="el done ${fresh ? "pop" : ""}" style="left:${sc.done.cx}px;top:${sc.done.cy}px">✓</div>`;
  if (sc.ring) {
    const R = sc.ring.R, C = 2 * Math.PI * R, p = Math.max(0, Math.min(100, sc.ring.pct));
    h += `<div class="el ring" style="left:${sc.ring.cx}px;top:${sc.ring.cy}px"><svg width="${R * 2 + 24}" height="${R * 2 + 24}" viewBox="${-R - 12} ${-R - 12} ${R * 2 + 24} ${R * 2 + 24}">
      <circle r="${R}" fill="rgba(0,0,0,.35)" stroke="rgba(255,255,255,.12)" stroke-width="6"/>
      <circle r="${R}" fill="none" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-dasharray="${(C * p / 100).toFixed(1)} ${C.toFixed(1)}" transform="rotate(-90)" style="filter:drop-shadow(0 0 6px #fff)"/>
      <text y="6" text-anchor="middle" fill="#f5f5f2" style="font:italic 400 42px var(--serif)">${Math.round(p)}%</text>
      <text y="28" text-anchor="middle" fill="#9b9b98" style="font:500 10px var(--mono)">${esc(sc.ring.eta || "")}</text></svg></div>`;
  }
  const chips = sc.chips.slice().sort((a, b) => a.x1 - b.x1);
  for (let i = 0; i < chips.length; i++) {
    const c = chips[i];
    h += `<div class="el chip ${c.hot ? "hot" : ""}" ${c.hot ? `data-ovchip="${esc(c.tag)}"` : ""} style="left:${c.x1}px;top:${c.cy}px;width:${c.x2 - c.x1}px;height:${c.h + 4}px;font-size:${c.size + 3}px">${emo(esc(c.t))}</div>`;
    const nx = chips[i + 1];
    if (nx && Math.abs(nx.cy - c.cy) < 2) h += `<div class="el arrow" style="left:${c.x2 + 9}px;top:${c.cy}px;width:${Math.max(4, nx.x1 - c.x2 - 18)}px"></div>`;
  }
  for (const t of sc.texts) {
    const cls = t.anchor === "n" ? "n" : (t.anchor === "w" ? "w" : "");
    const fs = t.serif ? Math.round(t.size * 1.45) : Math.round(t.size * 1.33);
    h += `<div class="el tx ${cls} ${t.serif ? "serif" : ""}" style="left:${t.x}px;top:${t.y}px;${t.w ? `width:${t.w}px;` : ""}font-size:${fs}px;font-weight:${t.bold ? 700 : 500};color:${col(t.fill)}">${emo(esc(t.t))}</div>`;
  }
  if (sc.entry) h += `<div class="el entry" style="left:${sc.W / 2 - 20}px;top:${sc.entry.y}px"><input id="ovin" value="${esc(sc.entry.v)}" inputmode="decimal"></div>`;
  for (const b of sc.buttons)
    h += `<button class="btn ${b.kind === "primary" ? "primary" : ""} ${fresh ? "fadein" : ""}" data-ovb="${b.id}" style="left:${b.cx}px;top:${b.cy}px;width:${b.w - (b.kind === "primary" ? 8 : 0)}px">${emo(esc(b.t))}</button>`;
  if (sc.ac) h += `<div class="el ac" style="left:64px;right:64px;top:${sc.ac.y}px"><i style="width:${(sc.ac.f * 100).toFixed(1)}%"></i></div>`;
  h += `</div>`;
  const act_el = document.activeElement, typing = act_el && act_el.id === "ovin" && sc.entry;
  if (typing) {                  // не перемальовуємо поле, поки в ньому друкують
    const pos = act_el.selectionStart, tmp = document.createElement("div");
    tmp.innerHTML = h;
    tmp.querySelector("#ovin").replaceWith(act_el);
    $("#app").replaceChildren(...tmp.childNodes);
    act_el.focus(); try { act_el.setSelectionRange(pos, pos); } catch (e) {}
  } else {
    $("#app").innerHTML = h;
    const inp = $("#ovin"); if (inp && fresh) { inp.focus(); inp.select(); }
  }
}
document.addEventListener("click", e => {
  if (PAGE !== "overlay") return;
  const b = e.target.closest("[data-ovb],[data-ovchip],[data-ov]");
  if (!b) return;
  e.stopImmediatePropagation();
  if (b.dataset.ovb) act("ov_click", { id: b.dataset.ovb });
  else if (b.dataset.ovchip) act("ov_chip", { tag: b.dataset.ovchip });
  else act("ov_esc");
}, true);
document.addEventListener("input", e => { if (e.target.id === "ovin") act("ov_entry", { v: e.target.value }); });
document.addEventListener("keydown", e => {
  if (PAGE !== "overlay") return;
  if (e.key === "Enter" && e.target.id === "ovin") { e.preventDefault(); act("ov_entry", { v: e.target.value, submit: true }); }
  else if (e.key === "Escape") act("ov_esc");
});
document.addEventListener("mousedown", e => {
  if (PAGE !== "overlay" || !e.target.closest("#ovdrag")) return;
  let x = e.screenX, y = e.screenY, busy = false;
  const mv = ev => { const dx = ev.screenX - x, dy = ev.screenY - y; if ((!dx && !dy) || busy) return; x = ev.screenX; y = ev.screenY; busy = true;
    act("ov_drag", { dx, dy }).finally(() => { busy = false; }); };
  const up = () => { removeEventListener("mousemove", mv); removeEventListener("mouseup", up); };
  addEventListener("mousemove", mv); addEventListener("mouseup", up);
});

function render() {
  if (PAGE === "overlay") return renderOverlay();
  if (PAGE === "gallery") renderGallery(); else if (PAGE === "news") renderNews(); else renderMenu();
}

// ---------- події ----------
document.addEventListener("click", async e => {
  const el = e.target.closest("[data-tab],[data-do],[data-url],[data-theme],[data-seg] button,[data-paste],[data-lib],[data-hist],[data-tab-menu],.li");
  if (!el) return;
  if (el.matches(".li")) { document.querySelectorAll(".li.on").forEach(x => x.classList.remove("on")); el.classList.add("on"); return; }
  if (el.dataset.tabMenu) { act("open_menu", { tab: el.dataset.tabMenu }); return window.close(); }
  if (el.dataset.tab) {
    if (PAGE !== "menu") { act("open_menu", { tab: el.dataset.tab }); return; }
    TAB = el.dataset.tab; history.replaceState(null, "", "#menu/" + TAB); return render();
  }
  if (el.dataset.url) return act("open_url", { url: el.dataset.url });
  if (el.dataset.theme) return setCfg("theme", el.dataset.theme);
  if (el.parentElement && el.parentElement.dataset.seg) {
    const k = el.parentElement.dataset.seg; let v = el.dataset.v;
    if (k === "target_mb") v = +v;
    el.parentElement.querySelectorAll("button").forEach(b => b.classList.toggle("on", b === el));
    await setCfg(k, v); if (k === "encoder") render(); return;
  }
  if (el.dataset.lib) { e.stopPropagation(); const r = await act(el.dataset.lib, { path: el.dataset.p }); if (el.dataset.lib === "lib_edit") window.close(); return r; }
  if (el.dataset.paste) { const r = await act("lib_paste", { path: el.dataset.paste }); toast(T("lib_copied")); setTimeout(() => window.close(), r.pasted ? 120 : 900); return; }
  if (el.dataset.hist) {
    const sel = $(".li.on"); const msg = $("#hist_msg");
    if (!sel) { msg.textContent = T("stats_pick"); return; }
    const r = await act(el.dataset.hist, { i: +sel.dataset.i });
    msg.textContent = r.ok === false ? T("stats_gone") : (el.dataset.hist === "hist_copy" ? T("stats_copied") : "");
    return;
  }
  const a = el.dataset.do;
  if (!a) return;
  if (a === "update") { live.update = { busy: true, text: T("checking"), pct: 0 }; render(); }
  if (a === "perf") { live.perf = { busy: true, html: progressHTML(T("perf_running"), 0) }; render(); }
  if (a === "deps_install") { live.deps_busy = true; live.deps_log = ""; render(); }
  if (a === "bench") { live.bench = { busy: true, pct: 0 }; render(); }
  if (a === "report") { live.report = T("checking"); render(); }
  const r = await act(a);
  if (a === "deps_check" && r.deps) { live.deps_now = r.deps; render(); }
  if (a === "pick_sound" || a === "reset_sound") { ST = await api("/api/state?page=" + PAGE); S = ST.S; render(); }
  if (el.dataset.then === "reload") { ST = await api("/api/state?page=" + PAGE); render(); }
  if (el.dataset.then === "close" || (PAGE === "gallery" && a === "open_editor")) window.close();
});
document.addEventListener("change", e => {
  const el = e.target;
  if (el.dataset.k) setCfg(el.dataset.k, el.checked);
  if (el.dataset.range) setCfg(el.dataset.range, +el.value);
});
document.addEventListener("input", e => {
  const el = e.target;
  if (el.type === "range") { el.style.setProperty("--p", (100 * (el.value - el.min) / (el.max - el.min)) + "%");
    if (el.dataset.range === "audio_kbps") $("#audio_val").textContent = +el.value ? el.value + " kbps" : T("audio_off"); }
});
addEventListener("keydown", e => { if (e.key === "Escape" && PAGE !== "menu" && PAGE !== "overlay") window.close(); });
new MutationObserver(() => document.querySelectorAll("input[type=range]").forEach(el =>
  el.style.setProperty("--p", (100 * (el.value - el.min) / (el.max - el.min)) + "%"))).observe(document.body, { childList: true, subtree: true });

function progressHTML(text, pct) { return `<div class="status">${esc(text)}  ${Math.round(pct)}%</div><div class="bar"><i style="width:${pct}%"></i></div>`; }
function sizeTxt(b) { return b >= 1048576 ? (b / 1048576).toFixed(1) + " МБ" : Math.max(1, Math.round(b / 1024)) + " КБ"; }

function onEvent(ev) {
  const k = ev.kind;
  if (k === "ov") { if (PAGE === "overlay") { OVS = ev.scene; renderOverlay(); } return; }
  if (k === "nav") { PAGE = ev.page; if (ev.tab) TAB = ev.tab; return render(); }
  if (k === "reload") return boot();
  if (k === "update") {
    const u = live.update || (live.update = { busy: true });
    if (ev.state === "plan") {
      const parts = [];
      if (ev.n) parts.push(T("upd_plan_files", { n: ev.n }) + (ev.size ? ` (${sizeTxt(ev.size)})` : ""));
      if (ev.mpv) parts.push(T("upd_plan_player", { s: sizeTxt(ev.mpv_size) }));
      u.plan = parts.length ? T("upd_plan", { what: parts.join(" + ") }) : T("checking");
      u.text = u.plan; u.pct = 0;
    } else if (ev.state === "files" || ev.state === "player") { u.pct = ev.pct; u.text = (u.plan || T("upd_files")) + "  " + ev.pct + "%"; }
    else if (ev.state === "retry") { u.text = T("upd_player_retry", { src: ev.src }); u.warn = true; }
    else if (ev.state === "wait") { u.text = T("upd_player_wait", { s: ev.pct }); u.warn = true; }
    else if (ev.state === "done") {
      u.busy = false; u.warn = !ev.ok; u.pct = ev.ok ? 100 : null;
      u.text = !ev.ok ? T("update_fail") : (ev.changed ? T("upd_restarting") : T("up_to_date"));
    } else if (ev.state === "error") { u.busy = false; u.text = T("update_fail"); u.warn = true; }
    if (PAGE === "menu" && TAB === "updates") {
      const s = $("#upd_status"), b = $("#upd_bar");
      if (s && b && ev.state !== "done") { s.textContent = u.text; s.className = "status" + (u.warn ? " warn" : ""); b.style.display = u.pct == null ? "none" : ""; b.firstElementChild.style.width = (u.pct || 0) + "%"; }
      else render();
    }
  }
  if (k === "perf") {
    const p = live.perf || (live.perf = {});
    if (ev.state === "dl") p.html = progressHTML(T("perf_dl"), ev.pct);
    if (ev.state === "run") p.html = progressHTML(T("perf_running"), ev.pct);
    if (ev.state === "dl_fail") { p.busy = false; p.html = `<div class="status warn">${esc(T("perf_dl_fail"))}</div>`; }
    if (ev.state === "done" || ev.state === "error") {
      p.busy = false;
      p.html = (ev.lines || []).map(([ic, tx]) => `<div class="check"><span class="o ${ic === "✓" ? "" : "no"}">${esc(ic)}</span><span>${esc(tx)}</span></div>`).join("")
        + `<div class="status ${ev.ok ? "" : "warn"}" style="font:italic 400 26px/1.2 var(--serif)">${esc(ev.verdict || ev.err || "")}</div>`;
    }
    if (PAGE === "menu" && TAB === "performance") { const b = $("#perf_box"); if (b && p.busy) b.innerHTML = p.html; else render(); }
  }
  if (k === "deps") {
    if (ev.state === "log") { live.deps_log = (live.deps_log || "") + ev.line + "\n"; const l = $("#deps_log"); if (l) { l.textContent = live.deps_log; l.scrollTop = 1e9; } }
    if (ev.state === "done") { live.deps_busy = false; live.deps_now = ev.deps; live.deps_msg = ev.ok ? T("setup_done_ok") : T("setup_done_fail"); if (TAB === "setup") render(); }
  }
  if (k === "report") { live.report = ev.ok ? T("st_report_ok") : T("st_report_fail") + " " + (ev.err || ""); if (TAB === "about") render(); }
  if (k === "gpu") { live.gpu = ev.gpu; if (TAB === "gpu") render(); }
  if (k === "bench") {
    const b = live.bench || (live.bench = {});
    if (ev.state === "run") { b.pct = ev.pct; const bar = $("#bench_bar"); if (bar) bar.firstElementChild.style.width = ev.pct + "%"; }
    if (ev.state === "done" || ev.state === "error") { b.busy = false; if (ev.bench) { ST.cfg.bench = ev.bench; ST.cfg.bench_at = ev.at; ST.cfg.encoder_best = ev.best; } if (TAB === "gpu") render(); }
  }
}
async function pollLoop() {
  for (;;) {
    try { const r = await api("/api/poll?since=" + LAST_EV); LAST_EV = r.last; r.events.forEach(onEvent); }
    catch (e) { await new Promise(res => setTimeout(res, 1500)); }
  }
}

async function boot() {
  const [p, t] = (location.hash.slice(1) || "menu").split("/");
  if (p === "overlay") { document.title = "DAC Overlay"; document.body.classList.add("ov"); }
  PAGE = ["menu", "gallery", "news", "overlay"].includes(p) ? p : "menu";
  if (t) TAB = t;
  ST = await api("/api/state?page=" + PAGE); S = ST.S;
  if (PAGE === "overlay") { const r = await act("ov_scene"); OVS = r.scene; }
  document.documentElement.lang = ST.lang;
  render();
  if (!LAST_EV) { const r = await api("/api/poll?since=999999999&w=0").catch(() => ({ last: 0 })); LAST_EV = r.last || 0; }
}
boot().then(pollLoop);
