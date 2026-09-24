const $ = (id) => document.getElementById(id);
const VIEW_ORDER = ["front", "side", "back"];
const VIEW_LABEL = { front: "正面", side: "侧面", back: "背面", video: "转身视频" };
const EXAMPLES = ["明天要去面试，想穿得得体一点", "周末去海边度假拍照", "晚上有个正式派对，想吸睛", "今天好冷，想在家窝着", "晚上去看球赛", "下午去打网球"];
const TRYON_LABEL = { idle: "未启动", downloading: "下载权重中", loading: "加载中", ready: "就绪", error: "出错" };
const TRUST_LABEL = { trusted: "资料可信", suspicious: "资料存疑", untrusted: "资料不可信", unverified: "资料未校验" };
const SOURCE_LABEL = { platform: "平台", extracted: "识别", user_input: "用户填写", measured: "照片测量", derived: "推算", mock: "模拟数据", missing: "缺失" };
const ATTR_LABEL = { material: "材质", thickness: "厚薄", stretch: "弹力", fit: "版型", length_type: "衣长", sleeve: "袖型", neckline: "领型", season: "季节", style: "风格" };
const MEASURE_LABEL = { length: "衣长", chest: "胸围", shoulder: "肩宽", sleeve: "袖长", waist: "腰围", hip: "臀围" };
const PROFILE_FIELDS = [["gender", "性别"], ["height_cm", "身高", "cm"], ["weight_kg", "体重", "kg"], ["chest_cm", "胸围", "cm"], ["waist_cm", "腰围", "cm"], ["hip_cm", "臀围", "cm"], ["shoulder_cm", "肩宽", "cm"], ["usual_top_size", "常穿上衣"], ["usual_bottom_size", "常穿下装"]];

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function sourceTag(source) {
  return el("span", "src src-" + source, SOURCE_LABEL[source] || source);
}

function renderPersonInfo(p) {
  const box = $("person-info");
  box.replaceChildren();
  const head = el("div", "pi-head");
  head.append(el("span", "trust-pill " + p.trust, TRUST_LABEL[p.trust]));
  if (p.note) head.append(el("span", "pi-note", p.note));
  box.append(head);
  if (p.profile) {
    const dl = el("dl", "pi-fields");
    for (const [key, label, unit] of PROFILE_FIELDS) {
      const v = p.profile[key];
      if (!v || v.value === null || v.value === undefined || v.value === "") continue;
      const shown = key === "gender" ? (v.value === "female" ? "女" : "男") : `${v.value}${unit || ""}`;
      dl.append(el("dt", "", label), el("dd", "", shown));
    }
    box.append(dl);
  }
  for (const i of p.issues || []) box.append(el("div", "pi-issue " + i.level, i.message));
  for (const w of p.warnings || []) box.append(el("div", "pi-warn", w));
}

function renderProduct(item) {
  const box = $("product");
  box.hidden = false;
  box.replaceChildren();
  const head = el("div", "pd-head");
  const title = el("div", "pd-title");
  title.append(el("b", "", item.title), el("span", "pd-platform", item.platform === "mock" ? "模拟商品" : item.platform === "demo" ? "演示图" : item.platform));
  head.append(title);
  if (item.price?.value) head.append(el("div", "pd-price", "¥" + item.price.value));
  box.append(head);

  const attrs = el("div", "pd-attrs");
  for (const [k, label] of Object.entries(ATTR_LABEL)) {
    const v = item.attributes?.[k];
    if (!v || v.value === null) continue;
    const chip = el("span", "pd-attr");
    chip.append(el("i", "", label), document.createTextNode(String(v.value)), sourceTag(v.source));
    attrs.append(chip);
  }
  if (!attrs.children.length) attrs.append(el("span", "pd-missing", "没有商品属性数据"));
  box.append(attrs);

  const chart = item.size_chart;
  if (chart) {
    const keys = Object.keys(chart.rows[0].measures);
    const table = el("table", "pd-chart");
    const hr = el("tr");
    hr.append(el("th", "", "尺码"), ...keys.map((k) => el("th", "", MEASURE_LABEL[k] || k)));
    table.append(hr);
    for (const r of chart.rows) {
      const tr = el("tr");
      tr.append(el("td", "", r.size), ...keys.map((k) => el("td", "", r.measures[k] ?? "–")));
      table.append(tr);
    }
    const cap = el("div", "pd-caption");
    cap.append(document.createTextNode(`尺码表（${chart.basis === "garment" ? "成衣尺寸" : "适穿人体尺寸"}，cm）`), sourceTag(chart.source));
    box.append(cap, table);
  }
  const ref = item.model_reference;
  if (ref) {
    const line = el("div", "pd-ref");
    line.append(document.createTextNode(`模特 ${ref.height_cm}cm${ref.weight_kg ? " / " + ref.weight_kg + "kg" : ""}，穿 ${ref.size} 码`), sourceTag(ref.source));
    box.append(line);
  }
  const missingCaps = Object.values(item.capabilities).filter((c) => !c.ok).map((c) => c.reason);
  if (missingCaps.length) {
    const ul = el("ul", "pd-gaps");
    missingCaps.forEach((r) => ul.append(el("li", "", r)));
    box.append(el("div", "pd-caption", "数据缺口（对应功能已关闭）"), ul);
  }
}

const state = {
  persons: [],
  person: null,
  wardrobe: [],
  entry: null, // current outfit: { item, results: {view: result}, pending: Set, prog: {view: progress}, video, laya }
  videoConfig: null,
  view: "front",
  gen: 0,
  busy: false,
  history: [],
};

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `请求失败 (${res.status})`);
  return body;
}

function toast(msg, ms = 3200) {
  const el = $("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.hidden = true), ms);
}

function fmtMs(ms) {
  return ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : Math.round(ms) + "ms";
}

function personViews() {
  return state.person ? VIEW_ORDER.filter((v) => state.person.views[v]) : [];
}

// ---------- status ----------

async function pollStatus() {
  let delay = 3000;
  try {
    const s = await api("/api/status");
    const laya = $("st-laya");
    laya.className = "pill " + (s.laya ? "ok" : "err");
    laya.title = s.laya ? "laya 服务在线" : "laya 服务未连接";
    const t = $("st-tryon");
    t.className = "pill " + (s.tryon === "ready" ? "ok" : s.tryon === "error" ? "err" : "wait");
    t.lastChild.textContent = "FASHN · " + (TRYON_LABEL[s.tryon] || s.tryon);
    t.title = s.tryon_error || "";
    if (s.laya && s.tryon === "ready") delay = 15000;
  } catch {
    $("st-laya").className = $("st-tryon").className = "pill err";
  }
  setTimeout(pollStatus, delay);
}

// ---------- stage rendering ----------

function render() {
  const e = state.entry;
  const view = state.view;
  const img = $("stage-img");
  const video = $("stage-video");
  const hasPerson = !!state.person;
  $("stage-empty").hidden = hasPerson;
  const showVideo = view === "video" && e?.video?.url;
  video.hidden = !showVideo;
  img.hidden = !hasPerson || showVideo;
  if (showVideo) {
    if (video.getAttribute("src") !== e.video.url) video.src = e.video.url;
    video.play().catch(() => {});
  } else {
    video.pause();
    const prog = e?.prog[view];
    const src = e?.results[view]?.image || (e?.pending.has(view) && prog?.preview) || state.person?.views[view];
    if (src && img.getAttribute("src") !== src) img.src = src;
  }

  const result = view !== "video" && e?.results[view];
  $("compare").hidden = !result;
  $("badge").hidden = !result;
  if (result) {
    $("badge-laya").hidden = !e.laya;
    if (e.laya) {
      $("badge-laya").textContent = "";
      const b = document.createElement("b");
      b.textContent = fmtMs(e.laya.ms);
      $("badge-laya").append("laya ", b, " · " + e.laya.occ);
    }
    $("badge-tryon").textContent = `${VIEW_LABEL[view]} ${fmtMs(result.timing.total_ms)}`;
  }
  const skippedReason = e?.skipped?.[view];
  const failures = result ? e?.score?.[view]?.qc_failures || [] : [];
  const note = $("stage-note");
  note.classList.toggle("fail", !skippedReason && failures.length > 0);
  note.hidden = !skippedReason && !failures.length;
  note.textContent = skippedReason ? `${skippedReason}（这里显示的是你的原照片）` : failures.length ? `质检未通过：${failures.join("；")}，这张图仅供参考` : "";

  renderScore();
  renderBusy();
  renderTabs();
  renderVideoButton();
}

function renderScore() {
  const e = state.entry;
  const s = e?.score?.[state.view === "video" ? "front" : state.view];
  const pill = $("score-pill");
  const card = $("score");
  pill.hidden = card.hidden = !s;
  if (!s) return;
  pill.className = "score-pill g" + s.grade;
  pill.textContent = `可信度 ${s.overall} · ${s.grade}${s.checked ? " · 已质检" : " · 待质检"}`;
  card.replaceChildren();
  const head = el("div", "sc-head");
  head.append(el("b", "", `换装可信度（${VIEW_LABEL[s.view]}）`), el("span", "sc-total g" + s.grade, `${s.overall} 分 · ${s.grade}`));
  card.append(head);
  for (const [key, label] of [["visual", "视觉可信度"], ["fit", "合身判断依据"]]) {
    const part = s[key];
    const row = el("div", "sc-part");
    const bar = el("div", "sc-bar");
    const fill = el("i", "g" + part.grade);
    fill.style.width = part.score + "%";
    bar.append(fill);
    row.append(el("span", "sc-label", label), bar, el("span", "sc-num", String(part.score)));
    card.append(row);
    if (part.deductions.length) {
      const ul = el("ul", "sc-deductions");
      for (const d of part.deductions) {
        const li = el("li");
        li.append(el("span", "sc-minus", `-${d.points}`), document.createTextNode(d.reason));
        ul.append(li);
      }
      card.append(ul);
    }
  }
  card.append(el("div", "sc-note", s.note));
}

function renderBusy() {
  const e = state.entry;
  const view = state.view;
  const pending = e?.pending.has(view);
  const choosing = state.choosing;
  const box = $("stage-busy");
  box.hidden = !(pending || choosing);
  clearInterval(renderBusy.timer);
  if (box.hidden) return;
  const prog = pending ? e.prog[view] : null;
  box.classList.toggle("previewing", !!prog?.preview);
  $("busy-bar").style.width = prog?.step ? (prog.step / prog.total) * 100 + "%" : "0";
  if (choosing) $("busy-text").textContent = "laya 正在挑衣服…";
  else if (prog?.step) $("busy-text").textContent = `${VIEW_LABEL[view]}生成中 ${prog.step}/${prog.total}`;
  else if (prog?.t0) $("busy-text").textContent = `正在穿上「${e.item.title}」· ${VIEW_LABEL[view]}`;
  else $("busy-text").textContent = `排队中 · ${VIEW_LABEL[view]}`;
  const t0 = choosing ? state.choosing : prog?.t0;
  const tick = () => ($("busy-timer").textContent = t0 ? ((performance.now() - t0) / 1000).toFixed(1) + "s" : "");
  tick();
  renderBusy.timer = setInterval(tick, 100);
}

function renderTabs() {
  const box = $("view-tabs");
  box.replaceChildren();
  const e = state.entry;
  const views = personViews();
  if (e?.video?.url) views.push("video");
  if (views.length <= 1 && !e) return;
  for (const v of views) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "view-tab" + (v === state.view ? " active" : "");
    if (e?.pending.has(v)) b.classList.add("pending");
    else if (e?.results[v]) b.classList.add("done");
    else if (e?.skipped?.[v]) {
      b.classList.add("skipped");
      b.title = e.skipped[v];
    }
    const thumb = document.createElement("span");
    thumb.className = "thumb";
    const src = v === "video" ? e.results.front?.image : e?.results[v]?.image || state.person.views[v];
    if (src) thumb.style.backgroundImage = `url("${src}")`;
    if (v === "video") thumb.classList.add("play");
    const label = document.createElement("span");
    label.textContent = VIEW_LABEL[v];
    b.append(thumb, label);
    b.onclick = () => setView(v);
    box.append(b);
  }
}

function renderVideoButton() {
  const btn = $("video-btn");
  const e = state.entry;
  btn.hidden = !e?.results.front;
  if (btn.hidden) return;
  const v = e.video;
  btn.disabled = false;
  btn.title = state.videoConfig?.available ? `使用你配置的视频模型（${state.videoConfig.provider}）` : state.videoConfig?.reason || "";
  if (!v) btn.textContent = "生成转身视频";
  else if (v.url) btn.textContent = "看转身视频";
  else if (v.status === "failed") btn.textContent = "视频失败，重试";
  else {
    btn.textContent = `视频生成中… ${Math.round((performance.now() - v.t0) / 1000)}s`;
    btn.disabled = true;
  }
  if (e.pending.has("back")) {
    btn.disabled = true;
    btn.title = "等背面生成完再做视频（尾帧用背面结果）";
  }
}

function setView(v) {
  state.view = v;
  render();
}

function stepView(dir) {
  const views = personViews();
  if (views.length < 2) return;
  const cur = views.indexOf(state.view === "video" ? "front" : state.view);
  setView(views[(cur + dir + views.length) % views.length]);
}

function setupStageGestures() {
  const stage = $("stage");
  let x0 = null;
  stage.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button")) return;
    x0 = e.clientX;
    stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener("pointermove", (e) => {
    if (x0 === null) return;
    const dx = e.clientX - x0;
    if (Math.abs(dx) > 60) {
      stepView(dx < 0 ? 1 : -1);
      x0 = e.clientX;
    }
  });
  const end = () => (x0 = null);
  stage.addEventListener("pointerup", end);
  stage.addEventListener("pointercancel", end);
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, select, textarea")) return;
    if (e.key === "ArrowRight") stepView(1);
    if (e.key === "ArrowLeft") stepView(-1);
  });

  const btn = $("compare");
  const show = () => {
    const src = state.person?.views[state.view];
    if (src) $("stage-img").src = src;
  };
  const hide = () => render();
  btn.addEventListener("pointerdown", show);
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => btn.addEventListener(ev, hide));
}

// ---------- persons ----------

async function loadPersons(selectId) {
  state.persons = await api("/api/persons");
  const grid = $("model-grid");
  grid.replaceChildren();
  for (const p of state.persons) {
    const b = document.createElement("button");
    b.dataset.id = p.id;
    const img = document.createElement("img");
    img.src = p.views.front;
    img.alt = "";
    img.loading = "lazy";
    b.append(img);
    const n = Object.keys(p.views).length;
    if (n > 1) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = `${n} 视角`;
      b.append(tag);
    }
    const trust = document.createElement("span");
    trust.className = "trust " + p.trust;
    trust.title = TRUST_LABEL[p.trust];
    b.append(trust);
    if (!p.sample) {
      const del = document.createElement("span");
      del.className = "del";
      del.title = "删除这个模特";
      del.textContent = "×";
      del.onclick = async (ev) => {
        ev.stopPropagation();
        if (!confirm("删除这个模特和他的照片？")) return;
        await api(`/api/person/${encodeURIComponent(p.id)}`, { method: "DELETE" });
        if (state.person?.id === p.id) state.person = null;
        loadPersons(state.person?.id);
      };
      b.append(del);
    }
    b.onclick = () => selectPerson(p);
    grid.append(b);
  }
  const target = state.persons.find((p) => p.id === selectId) || (!state.person && state.persons[0]);
  if (target) selectPerson(target);
  else markPerson();
}

function markPerson() {
  document.querySelectorAll("#model-grid button").forEach((b) => b.classList.toggle("active", b.dataset.id === state.person?.id));
}

function selectPerson(p) {
  if (state.choosing) return;
  state.gen++;
  state.busy = false;
  state.person = p;
  state.entry = null;
  state.view = "front";
  markPerson();
  markItem(null);
  renderPersonInfo(p);
  $("product").hidden = true;
  render();
  fetch("/api/prepare", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ person_id: p.id }),
  }).catch(() => {});
}

// ---------- wardrobe ----------

async function loadWardrobe() {
  state.wardrobe = await api("/api/wardrobe");
  const grid = $("closet-grid");
  grid.replaceChildren();
  $("closet-count").textContent = `· ${state.wardrobe.length} 件`;
  for (const it of state.wardrobe) {
    const b = document.createElement("div");
    b.className = "item";
    b.dataset.id = it.id;
    b.tabIndex = 0;
    b.innerHTML = `<img alt="" loading="lazy"><span class="tag"></span><button class="del" title="从衣柜移除">×</button><div class="meta"><div class="name"></div><div class="occ"></div></div>`;
    b.querySelector("img").src = it.url;
    b.querySelector(".tag").textContent = it.category_label + (it.url_back ? " · 含背面" : "");
    b.querySelector(".name").textContent = it.title;
    b.querySelector(".occ").textContent = [it.price?.value ? "¥" + it.price.value : "", it.occasions?.value || ""].filter(Boolean).join(" · ");
    b.onclick = () => tryOn(it.id);
    b.onkeydown = (e) => e.key === "Enter" && tryOn(it.id);
    b.querySelector(".del").onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(`从衣柜移除「${it.title}」？`)) return;
      await api(`/api/wardrobe/${encodeURIComponent(it.id)}`, { method: "DELETE" });
      loadWardrobe();
    };
    if (it.id === state.entry?.item.id) b.classList.add("active");
    grid.append(b);
  }
}

function markItem(id, picked) {
  document.querySelectorAll(".closet-grid .item").forEach((b) => {
    b.classList.toggle("active", b.dataset.id === id);
    if (picked && b.dataset.id === id) {
      b.classList.remove("picked");
      void b.offsetWidth;
      b.classList.add("picked");
      b.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  });
}

// ---------- try-on ----------

async function streamTryOn(itemId, view, onPreview) {
  const res = await fetch("/api/tryon/stream", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ person_id: state.person.id, item_id: itemId, view, mode: $("mode").value }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败 (${res.status})`);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) throw new Error("生成中断，请重试");
    buf += value;
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const msg = JSON.parse(buf.slice(0, nl));
      buf = buf.slice(nl + 1);
      if (msg.type === "preview") onPreview(msg);
      else if (msg.type === "error") throw new Error(msg.detail);
      else if (msg.type === "done") return msg;
    }
  }
}

async function tryOn(itemId, laya = null) {
  if (!state.person) return toast("先在左边选一个模特");
  if (state.choosing) return;
  const item = state.wardrobe.find((w) => w.id === itemId);
  if (!item) return;
  const gen = ++state.gen;
  const skipped = {};
  if (!item.capabilities.tryon_back.ok && state.person.views.back) skipped.back = item.capabilities.tryon_back.reason;
  const views = personViews().filter((v) => !skipped[v]);
  const entry = { item, person: state.person, results: {}, pending: new Set(views), prog: {}, video: null, laya, skipped, score: null };
  renderProduct(item);
  const qs = new URLSearchParams({ person_id: state.person.id, item_id: itemId, mode: $("mode").value });
  api(`/api/score?${qs}`).then((s) => {
    entry.score = s;
    if (state.entry === entry) render();
  }).catch(() => {});
  state.entry = entry;
  if (!views.includes(state.view)) state.view = "front";
  state.busy = true;
  $("ask-btn").disabled = true;
  markItem(itemId);
  if (!laya) $("decision").hidden = true;
  render();

  const t0 = performance.now();
  const superseded = () => {
    if (gen === state.gen) return false;
    entry.pending.clear();
    return true;
  };
  for (const view of views) {
    if (superseded()) return;
    entry.prog[view] = { t0: performance.now() };
    if (state.view === view) render();
    try {
      const r = await streamTryOn(itemId, view, (p) => {
        if (gen !== state.gen) return;
        Object.assign(entry.prog[view], { step: p.step, total: p.total, preview: p.image });
        if (view === "front" && p.step === 1) $("m-first").textContent = fmtMs(p.elapsed_ms);
        if (state.view === view) render();
      });
      if (superseded()) return;
      entry.results[view] = r;
      if (r.score) entry.score = { ...(entry.score || {}), [view]: r.score };
      entry.pending.delete(view);
      if (view === "front") {
        $("m-tryon").textContent = fmtMs(r.timing.total_ms);
        state.busy = false;
        $("ask-btn").disabled = false;
        addHistory(entry);
      }
    } catch (err) {
      if (superseded()) return;
      entry.pending.delete(view);
      toast(`${VIEW_LABEL[view]}生成失败：${err.message}`, 5000);
      if (view === "front") {
        entry.pending.clear();
        state.busy = false;
        $("ask-btn").disabled = false;
        state.entry = null;
        render();
        return;
      }
    }
    render();
    renderHistory();
  }
  $("m-all").textContent = views.length > 1 ? fmtMs(performance.now() - t0) : "–";
}

// ---------- history ----------

function addHistory(entry) {
  state.history = [entry, ...state.history.filter((h) => h !== entry)].slice(0, 20);
  renderHistory();
}

function renderHistory() {
  const box = $("history");
  box.replaceChildren();
  for (const h of state.history) {
    const b = document.createElement("button");
    const img = document.createElement("img");
    img.src = h.results.front?.image || "";
    img.alt = "";
    b.append(img);
    const n = Object.keys(h.results).length;
    if (n > 1 || h.video?.url) {
      const tag = document.createElement("span");
      tag.textContent = h.video?.url ? "▶" : `${n}`;
      b.append(tag);
    }
    if (h === state.entry) b.classList.add("active");
    b.onclick = () => {
      if (state.busy || state.choosing) return;
      state.gen++;
      state.person = h.person;
      state.entry = h;
      if (!h.results[state.view] && state.view !== "video") state.view = "front";
      markPerson();
      markItem(h.item.id);
      renderPersonInfo(h.person);
      renderProduct(h.item);
      render();
      renderHistory();
    };
    box.append(b);
  }
}

// ---------- laya ----------

function renderDecision(d) {
  const item = state.wardrobe.find((w) => w.id === d.choice);
  $("decision").hidden = false;
  $("dec-img").src = item.url;
  $("dec-name").textContent = item.title;
  $("dec-occ").textContent = "匹配场合：" + d.matched_occasion.replace(/·+$/, "");
  $("m-laya").textContent = fmtMs(d.latency_ms);
  $("m-first").textContent = $("m-tryon").textContent = $("m-all").textContent = "…";
  const probs = Object.entries(d.probabilities || {}).sort((a, b) => b[1] - a[1]).slice(0, 4);
  const max = probs[0]?.[1] || 1;
  const box = $("probs");
  box.replaceChildren();
  probs.forEach(([id, p], i) => {
    const w = state.wardrobe.find((x) => x.id === id);
    const row = document.createElement("div");
    row.className = "prob" + (i === 0 ? " top" : "");
    row.innerHTML = `<span></span><div class="bar"><i></i></div><span></span>`;
    row.children[0].textContent = w?.title || id;
    row.querySelector("i").style.width = (p / max) * 100 + "%";
    row.children[2].textContent = (p * 100).toFixed(0) + "%";
    box.append(row);
  });
}

async function ask(text) {
  text = text.trim();
  if (!text || state.busy || state.choosing) return;
  if (!state.person) return toast("先在左边选一个模特");
  state.choosing = performance.now();
  $("ask-btn").disabled = true;
  render();
  let d;
  try {
    d = await api("/api/choose", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text, current_item: state.entry?.item.id }),
    });
  } catch (e) {
    toast(e.message, 5000);
    return;
  } finally {
    state.choosing = null;
    $("ask-btn").disabled = false;
    render();
  }
  renderDecision(d);
  markItem(d.choice, true);
  await tryOn(d.choice, { ms: d.latency_ms, occ: d.matched_occasion.replace(/·+$/, "").split("、")[0] });
}

function setupAsk() {
  $("ask").onsubmit = (e) => {
    e.preventDefault();
    ask($("ask-input").value);
  };
  for (const ex of EXAMPLES) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = ex;
    b.onclick = () => {
      $("ask-input").value = ex;
      ask(ex);
    };
    $("chips").append(b);
  }

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("mic");
  if (!SR) {
    mic.title = "当前浏览器不支持语音输入（推荐 Chrome / Edge）";
    mic.onclick = () => toast(mic.title);
    return;
  }
  const rec = new SR();
  rec.lang = "zh-CN";
  rec.interimResults = true;
  let listening = false;
  rec.onresult = (e) => {
    const r = e.results[e.results.length - 1];
    $("ask-input").value = r[0].transcript;
    if (r.isFinal) ask(r[0].transcript);
  };
  rec.onend = () => {
    listening = false;
    mic.classList.remove("on");
  };
  rec.onerror = (e) => toast("语音识别出错：" + e.error);
  mic.onclick = () => {
    if (listening) return rec.stop();
    listening = true;
    mic.classList.add("on");
    rec.start();
  };
}

// ---------- turnaround video (provider configured by the user, see docs/generation.md) ----------

async function startVideo() {
  const e = state.entry;
  if (!e?.results.front) return;
  if (e.video?.url) return setView("video");
  if (!state.videoConfig?.available) return toast(state.videoConfig?.reason || "未配置视频生成模型", 8000);
  const back = e.results.back;
  const how = back ? "首帧用正面换装结果、尾帧用背面换装结果" : "只有正面结果，背面和侧面由视频模型推测";
  if (!confirm(`用你配置的视频模型（${state.videoConfig.provider}）生成 ${state.videoConfig.seconds} 秒转身视频（${how}）。
可能产生费用、需要几分钟。继续？`)) return;
  const video = { status: "submitting", t0: performance.now() };
  e.video = video;
  render();
  try {
    const r = await api("/api/video", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ front_url: e.results.front.url, back_url: back?.url || null }),
    });
    video.requestId = r.request_id;
    video.status = "pending";
    toast("转身视频已提交，好了会提醒你");
  } catch (err) {
    e.video = null;
    render();
    return toast(err.message, 8000);
  }
  pollVideo(e);
}

async function pollVideo(e) {
  const video = e.video;
  for (;;) {
    await new Promise((r) => setTimeout(r, 5000));
    if (e.video !== video) return;
    try {
      const s = await api(`/api/video/${encodeURIComponent(video.requestId)}`);
      video.status = s.status;
      if (s.url) {
        video.url = s.url;
        toast(`「${e.item.title}」的转身视频好了`, 5000);
        if (state.entry === e) setView("video");
        renderHistory();
        return;
      }
      if (s.status === "failed") {
        toast("视频生成失败：" + (s.error || "未知原因"), 6000);
        if (state.entry === e) render();
        return;
      }
    } catch (err) {
      video.status = "failed";
      toast(err.message, 6000);
      if (state.entry === e) render();
      return;
    }
    if (state.entry === e) renderVideoButton();
  }
}

// ---------- dialogs ----------

function setupSlots(form) {
  form.querySelectorAll(".slot input").forEach((input) => {
    input.onchange = () => {
      const box = input.parentElement.querySelector(".slot-img");
      const f = input.files[0];
      box.style.backgroundImage = f ? `url("${URL.createObjectURL(f)}")` : "";
      input.parentElement.classList.toggle("filled", !!f);
    };
  });
}

function resetSlots(form) {
  form.reset();
  form.querySelectorAll(".slot").forEach((s) => {
    s.classList.remove("filled", "bad", "warn");
    s.querySelector(".slot-img").style.backgroundImage = "";
    const msg = s.querySelector(".slot-msg");
    if (msg) msg.textContent = "";
  });
}

function setupDialogs() {
  for (const [openId, dlgId] of [["person-open", "person-dialog"], ["add-open", "add-dialog"]]) {
    const dlg = $(dlgId);
    $(openId).onclick = () => dlg.showModal();
    dlg.querySelector("[data-close]").onclick = () => dlg.close();
    setupSlots(dlg.querySelector("form"));
  }

  $("person-form").onsubmit = async (e) => {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector("[type=submit]");
    btn.disabled = true;
    btn.textContent = "检查照片中…";
    form.querySelectorAll(".slot").forEach((s) => s.classList.remove("bad", "warn"));
    form.querySelectorAll(".slot-msg").forEach((m) => (m.textContent = ""));
    $("person-error").textContent = "";
    try {
      const fd = new FormData(form);
      for (const [k, v] of [...fd.entries()]) if ((v instanceof File && !v.size) || v === "") fd.delete(k);
      const res = await fetch("/api/person", { method: "POST", body: fd });
      const body = await res.json().catch(() => ({}));
      if (res.status === 422 && body.checks) {
        for (const [view, c] of Object.entries(body.checks)) {
          const slot = form.querySelector(`.slot[data-view=${view}]`);
          slot.classList.add(c.passed ? (c.warnings.length ? "warn" : "") : "bad");
          slot.querySelector(".slot-msg").textContent = [...c.blocking, ...c.warnings].join("；");
        }
        $("person-error").textContent = body.detail;
        return;
      }
      if (!res.ok) throw new Error(body.detail || `请求失败 (${res.status})`);
      resetSlots(form);
      $("person-dialog").close();
      await loadPersons(body.id);
      toast(`模特已创建：${TRUST_LABEL[body.trust]}${body.issues.length ? "，请查看左侧提示" : ""}`, 4500);
    } catch (err) {
      $("person-error").textContent = err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = "创建";
    }
  };

  $("add-form").onsubmit = async (e) => {
    e.preventDefault();
    const form = e.target;
    try {
      const fd = new FormData(form);
      for (const [k, v] of [...fd.entries()]) if (v instanceof File && !v.size) fd.delete(k);
      await api("/api/wardrobe", { method: "POST", body: fd });
      resetSlots(form);
      $("add-dialog").close();
      await loadWardrobe();
      toast("已加入衣柜");
    } catch (err) {
      toast(err.message);
    }
  };
}

$("video-btn").onclick = startVideo;
$("score-pill").onclick = () => $("score").scrollIntoView({ behavior: "smooth", block: "center" });
setupAsk();
setupStageGestures();
setupDialogs();
pollStatus();
api("/api/video/config").then((c) => (state.videoConfig = c)).catch(() => {});
loadPersons().catch((e) => toast(e.message));
loadWardrobe().catch((e) => toast(e.message));
