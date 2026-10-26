/* Visual engine for the technology guide: static SVG drawings and small simulators.
   Every widget is a function (mount, lang) and is mounted into each <div data-widget="…">. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const TONE = { a: "tone-a", b: "tone-b", c: "tone-c", d: "tone-d", hot: "tone-hot" };

  // ---------- SVG helpers ----------
  function el(tag, attrs, parent) {
    const node = document.createElementNS(NS, tag);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }
  function wrapWords(str, maxChars) {
    const words = str.split(" "), lines = [];
    let line = "";
    for (const w of words) {
      if (line && (line + " " + w).length > maxChars) { lines.push(line); line = w; } else line = line ? line + " " + w : w;
    }
    if (line) lines.push(line);
    return lines;
  }
  // Long notes wrap onto several lines; the available width follows from the anchor
  // and position inside the 960-wide figure unless maxW says otherwise.
  function text(parent, x, y, str, cls, anchor, maxW) {
    cls = cls || ""; anchor = anchor || "middle";
    const isNote = /\bnote\b/.test(cls);
    if (maxW == null && isNote) maxW = anchor === "middle" ? Math.min(x, 960 - x) * 2 - 24 : anchor === "start" ? 950 - x : x - 10;
    const t = el("text", { x, y, class: cls, "text-anchor": anchor }, parent);
    if (!maxW) { t.textContent = str; return t; }
    const perChar = /[Ѐ-ӿ]/.test(str) ? 7.3 : 6.4;
    const lines = wrapWords(str, Math.max(12, Math.floor(maxW / perChar)));
    lines.forEach((ln, i) => { const ts = el("tspan", { x, dy: i ? 16 : 0 }, t); ts.textContent = ln; });
    return t;
  }
  let uid = 0;
  function fig(parent, w, h, label) {
    const wrap = document.createElement("div");
    wrap.className = "fig-wrap";
    parent.appendChild(wrap);
    const s = el("svg", { viewBox: `0 0 ${w} ${h}`, class: "fig", role: "img", "aria-label": label || "" });
    s.dataset.uid = String(++uid);
    const defs = el("defs", {}, s);
    for (const [id, cls] of [["ah", "ah-line"], ["ah-b", "ah-b"], ["ah-hot", "ah-hot"]]) {
      const m = el("marker", { id: `${id}-${s.dataset.uid}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
      el("path", { d: "M0,0 L10,5 L0,10 z", class: cls }, m);
    }
    wrap.appendChild(s);
    return s;
  }
  function box(s, x, y, w, h, title, sub, tone, dashed) {
    const g = el("g", {}, s);
    el("rect", { x, y, width: w, height: h, rx: 9, class: "bx " + (tone || TONE.a), "stroke-dasharray": dashed ? "6 5" : "" }, g);
    text(g, x + w / 2, y + (sub ? h / 2 - 4 : h / 2 + 5), title, "bx-t");
    if (sub) text(g, x + w / 2, y + h / 2 + 15, sub, "bx-s");
    return g;
  }
  function arrow(s, x1, y1, x2, y2, label, opts) {
    opts = opts || {};
    const cls = opts.hot ? "ln hot" : opts.ok ? "ln ok" : "ln";
    const marker = opts.hot ? "ah-hot" : opts.ok ? "ah-b" : "ah";
    const d = opts.path || `M${x1},${y1} L${x2},${y2}`;
    el("path", { d, class: cls, "marker-end": `url(#${marker}-${s.dataset.uid})`, "stroke-dasharray": opts.dashed ? "5 4" : "" }, s);
    if (label) {
      const mx = opts.lx != null ? opts.lx : (x1 + x2) / 2, my = opts.ly != null ? opts.ly : (y1 + y2) / 2 - 6;
      text(s, mx, my, label, "lbl", opts.anchor || "middle");
    }
  }
  function div(parent, cls, html) {
    const d = document.createElement("div");
    if (cls) d.className = cls;
    if (html != null) d.innerHTML = html;
    parent.appendChild(d);
    return d;
  }
  function button(parent, label, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "wbtn";
    b.textContent = label;
    b.addEventListener("click", onClick);
    parent.appendChild(b);
    return b;
  }
  function slider(parent, label, min, max, value, step, onInput, fmt) {
    const wrap = div(parent, "wslider");
    const id = "sl" + (++uid);
    const lab = document.createElement("label");
    lab.htmlFor = id;
    const val = document.createElement("span");
    val.className = "wval";
    const inp = document.createElement("input");
    inp.type = "range"; inp.id = id; inp.min = min; inp.max = max; inp.step = step || 1; inp.value = value;
    const render = () => { val.textContent = fmt ? fmt(+inp.value) : inp.value; };
    inp.addEventListener("input", () => { render(); onInput(+inp.value); });
    lab.textContent = label + " ";
    lab.appendChild(val);
    wrap.appendChild(lab);
    wrap.appendChild(inp);
    render();
    return inp;
  }
  const T = (lang, en, ru) => (lang === "ru" ? ru : en);

  const W = {};

  // =====================================================================
  // D1. Architecture of the cloud mode
  // =====================================================================
  W.architecture = function (m, lang) {
    const s = fig(m, 960, 430, T(lang, "Cloud mode architecture", "Архитектура облачного режима"));
    el("rect", { x: 10, y: 20, width: 250, height: 390, rx: 12, class: "lane" }, s);
    el("rect", { x: 280, y: 20, width: 670, height: 390, rx: 12, class: "lane" }, s);
    text(s, 135, 44, "GitHub", "lane-t");
    text(s, 615, 44, "Google Cloud", "lane-t");
    box(s, 40, 70, 190, 64, T(lang, "Pull request", "Pull request"), T(lang, "opened / synchronize", "opened / synchronize"), TONE.a);
    box(s, 40, 300, 190, 64, T(lang, "Commit status", "Статус коммита"), "ai-test-assistant ✓ / ✗", TONE.a);
    box(s, 310, 70, 200, 64, "webhook-receiver", T(lang, "Cloud Run · public", "Cloud Run · публичный"), TONE.b);
    box(s, 560, 70, 170, 64, T(lang, "Topic", "Топик"), "pr-analysis-jobs", TONE.c);
    box(s, 560, 170, 170, 56, T(lang, "Push subscription", "Push-подписка"), T(lang, "ack 600 s · 5 attempts", "ack 600 с · 5 попыток"), TONE.c);
    box(s, 770, 170, 160, 56, "Dead-letter", T(lang, "after 5 failures", "после 5 неудач"), TONE.d, true);
    box(s, 310, 260, 200, 64, "analysis-worker", T(lang, "Cloud Run · private", "Cloud Run · приватный"), TONE.b);
    box(s, 560, 300, 170, 64, "Cloud Storage", "repo/pr/sha/…", TONE.c);
    arrow(s, 230, 102, 308, 102, T(lang, "POST /webhook · HMAC", "POST /webhook · HMAC"), { ly: 90 });
    arrow(s, 510, 102, 558, 102, "publish", { ly: 90 });
    arrow(s, 645, 134, 645, 168, "", {});
    arrow(s, 560, 198, 410, 258, T(lang, "push POST /pubsub", "push POST /pubsub"), { path: "M560,198 L410,198 L410,258", lx: 470, ly: 190 });
    arrow(s, 730, 198, 768, 198, "", { dashed: true });
    arrow(s, 510, 292, 558, 332, T(lang, "upload report + tests", "загрузка отчёта и тестов"), { path: "M510,300 L540,300 L540,332 L558,332", lx: 600, ly: 285 });
    arrow(s, 310, 300, 230, 332, T(lang, "POST status", "POST статус"), { path: "M310,300 L270,300 L270,332 L232,332", lx: 262, ly: 288 });
    text(s, 410, 350, T(lang, "answers 200 = ack · 500 = retry", "ответ 200 = ack · 500 = повтор"), "note");
    text(s, 410, 370, T(lang, "skips a job whose report already exists", "пропускает задачу, чей отчёт уже есть"), "note");
    text(s, 645, 395, T(lang, "the folder name is the idempotency key", "имя папки — ключ идемпотентности"), "note");
  };

  // =====================================================================
  // D2. Sequence diagram with time budgets
  // =====================================================================
  W.sequence = function (m, lang) {
    const parts = ["GitHub", "receiver", "Pub/Sub", "worker", "Cloud Storage", "GitHub API"];
    const xs = [80, 250, 420, 590, 760, 910];
    const s = fig(m, 960, 520, T(lang, "Sequence of one job", "Последовательность одной задачи"));
    parts.forEach((p, i) => {
      box(s, xs[i] - 65, 20, 130, 40, p, "", i === 0 || i === 5 ? TONE.a : i === 2 || i === 4 ? TONE.c : TONE.b);
      el("line", { x1: xs[i], y1: 60, x2: xs[i], y2: 500, class: "life" }, s);
    });
    const msg = (i, j, y, label, opts) => arrow(s, xs[i] + (j > i ? 3 : -3), y, xs[j] + (j > i ? -3 : 3), y, label, Object.assign({ ly: y - 11 }, opts || {}));
    msg(0, 1, 95, T(lang, "POST /webhook (signed body)", "POST /webhook (подписанное тело)"));
    msg(1, 2, 130, "publish(job)");
    msg(1, 0, 165, T(lang, "202 Accepted", "202 Accepted"), { ok: true });
    el("rect", { x: 20, y: 80, width: 300, height: 100, rx: 8, class: "budget" }, s);
    text(s, 40, 198, T(lang, "budget: 10 s (GitHub webhook timeout), real: ≈ 50 ms", "бюджет: 10 с (таймаут webhook GitHub), реально: ≈ 50 мс"), "note", "start");
    msg(2, 3, 240, T(lang, "push POST /pubsub (attempt 1)", "push POST /pubsub (попытка 1)"));
    el("rect", { x: 560, y: 255, width: 60, height: 150, rx: 6, class: "act" }, s);
    text(s, 640, 275, "git clone + checkout sha", "note", "start");
    text(s, 640, 295, T(lang, "run the 8 steps (LLM, pytest)", "8 шагов (LLM, pytest)"), "note", "start");
    msg(3, 4, 330, T(lang, "upload reports/ + tests/", "загрузка reports/ + tests/"));
    msg(3, 5, 365, "POST /statuses/{sha}");
    msg(3, 2, 420, T(lang, "200 → message acknowledged", "200 → сообщение подтверждено"), { ok: true });
    el("rect", { x: 360, y: 225, width: 580, height: 215, rx: 8, class: "budget" }, s);
    text(s, 380, 458, T(lang, "budget: 600 s ack deadline; no answer → redelivery (up to 5), then dead-letter", "бюджет: 600 с до ack; нет ответа → повторная доставка (до 5), затем dead-letter"), "note", "start");
    text(s, 380, 478, T(lang, "crash before the upload → the retry redoes everything; after it → the retry is skipped", "сбой до загрузки → повтор делает всё заново; после → повтор пропускается"), "note", "start");
  };

  // =====================================================================
  // D3. Why two services: conflicting requirements
  // =====================================================================
  W.split = function (m, lang) {
    const rows = [
      [T(lang, "must answer within", "должен ответить за"), "10 s", T(lang, "minutes are fine", "минуты — нормально"), 0.03, 1.0],
      [T(lang, "reachable from", "доступен из"), T(lang, "the internet (GitHub)", "интернета (GitHub)"), T(lang, "Pub/Sub only", "только Pub/Sub"), 1.0, 0.1],
      [T(lang, "work per request", "работа на запрос"), T(lang, "verify + publish", "проверить + опубликовать"), T(lang, "clone + LLM + pytest", "clone + LLM + pytest"), 0.05, 1.0],
      [T(lang, "memory", "память"), "≈ 128 MB", "1 GB", 0.15, 1.0],
      [T(lang, "scales by", "масштабируется"), T(lang, "requests", "запросами"), T(lang, "queue depth", "глубиной очереди"), 0.6, 0.6],
    ];
    const s = fig(m, 960, 60 + rows.length * 58 + 30, T(lang, "Conflicting requirements", "Конфликтующие требования"));
    text(s, 420, 40, "webhook-receiver", "lane-t");
    text(s, 780, 40, "analysis-worker", "lane-t");
    rows.forEach((r, i) => {
      const y = 70 + i * 58;
      text(s, 20, y + 24, r[0], "row-t", "start");
      el("rect", { x: 270, y: y, width: 300 * r[3], height: 34, rx: 6, class: "bar tone-b" }, s);
      text(s, 280, y + 23, r[1], "bar-t", "start");
      el("rect", { x: 630, y: y, width: 300 * r[4], height: 34, rx: 6, class: "bar tone-c" }, s);
      text(s, 640, y + 23, r[2], "bar-t", "start");
    });
    text(s, 480, 60 + rows.length * 58 + 18, T(lang, "Different needs on every row → two services, one JSON message between them.", "Разные потребности в каждой строке → два сервиса и одно JSON-сообщение между ними."), "note");
  };

  // =====================================================================
  // D4. Message lifecycle (state machine)
  // =====================================================================
  W.lifecycle = function (m, lang) {
    const s = fig(m, 960, 300, T(lang, "Life of one message", "Жизнь одного сообщения"));
    box(s, 20, 110, 150, 60, T(lang, "Published", "Опубликовано"), T(lang, "receiver → topic", "ресивер → топик"), TONE.c);
    box(s, 230, 110, 170, 60, T(lang, "Delivered", "Доставлено"), T(lang, "attempt n", "попытка n"), TONE.c);
    box(s, 460, 110, 170, 60, T(lang, "Processing", "Обработка"), T(lang, "worker runs the job", "воркер выполняет задачу"), TONE.b);
    box(s, 700, 30, 180, 60, T(lang, "Acknowledged", "Подтверждено"), T(lang, "200 → deleted", "200 → удалено"), TONE.b);
    box(s, 700, 190, 180, 60, "Dead-letter", T(lang, "n = 5 → parked", "n = 5 → отложено"), TONE.d, true);
    arrow(s, 170, 140, 228, 140, "push");
    arrow(s, 400, 140, 458, 140, "POST /pubsub");
    arrow(s, 630, 125, 698, 65, T(lang, "200 or malformed", "200 или битое"), { ok: true, path: "M630,125 L660,125 L660,60 L698,60", lx: 700, ly: 112, anchor: "start" });
    arrow(s, 630, 155, 698, 215, T(lang, "500, crash, or 600 s silence", "500, сбой или 600 с тишины"), { hot: true, path: "M630,155 L660,155 L660,220 L698,220", lx: 650, ly: 245, anchor: "middle" });
    arrow(s, 545, 170, 315, 170, T(lang, "redeliver (n < 5), with backoff", "повторная доставка (n < 5), с паузой"), { hot: true, path: "M545,170 L545,250 L315,250 L315,172", lx: 430, ly: 268 });
    text(s, 480, 20, T(lang, "Pub/Sub delivers at least once: the same message can reach the worker twice.", "Pub/Sub доставляет как минимум один раз: одно сообщение может прийти воркеру дважды."), "note");
  };

  // =====================================================================
  // D5. Duplicate delivery and idempotency (interactive)
  // =====================================================================
  W.idempotency = function (m, lang) {
    const steps = [
      T(lang, "clone the PR", "клонировать PR"), T(lang, "run the 8 steps", "8 шагов"), T(lang, "record metrics", "записать метрики"),
      T(lang, "upload to GCS", "загрузить в GCS"), T(lang, "post commit status", "статус коммита"), T(lang, "answer 200", "ответить 200"),
    ];
    const ctrl = div(m, "wctrl");
    const lab = div(ctrl, "wlabel", T(lang, "The worker crashes after step:", "Воркер падает после шага:"));
    let crash = 2;
    const holder = div(m, "");
    const draw = () => {
      holder.innerHTML = "";
      const s = fig(holder, 960, 300, T(lang, "Two attempts of the same message", "Две попытки одного сообщения"));
      const drawAttempt = (y, title, lastDone, skipped, note) => {
        text(s, 20, y - 14, title, "row-t", "start");
        steps.forEach((st, i) => {
          const x = 20 + i * 155;
          const state = skipped ? "skip" : i <= lastDone ? "done" : i === lastDone + 1 ? "crash" : "todo";
          el("rect", { x, y, width: 140, height: 44, rx: 8, class: "step " + state }, s);
          text(s, x + 70, y + 27, st, "step-t");
          if (i < steps.length - 1) arrow(s, x + 140, y + 22, x + 155, y + 22, "");
        });
        if (note) text(s, 20, y + 70, note, "note", "start");
      };
      drawAttempt(50, T(lang, "Attempt 1", "Попытка 1"), crash, false,
        T(lang, `No 200 was sent → after the ack deadline Pub/Sub delivers the message again.`, `200 не отправлен → после дедлайна ack Pub/Sub доставляет сообщение снова.`));
      const uploaded = crash >= 3;
      drawAttempt(180, T(lang, "Attempt 2", "Попытка 2"), uploaded ? -1 : 5, uploaded, uploaded
        ? T(lang, "The report already exists at repo/pr/sha → the job is skipped and acknowledged. Nothing is uploaded or posted twice.", "Отчёт уже лежит в repo/pr/sha → задача пропускается и подтверждается. Ничего не загружается и не публикуется дважды.")
        : T(lang, "No report in GCS yet → the whole job runs again. Attempt 1 left nothing behind, so this is safe.", "Отчёта в GCS ещё нет → задача выполняется заново. Попытка 1 ничего не оставила, так что это безопасно."));
      text(s, 480, 290, T(lang, "The marker (the JSON report in Cloud Storage) is written only at step 4, so a retry can never half-apply a job.", "Маркер (JSON-отчёт в Cloud Storage) пишется только на шаге 4, поэтому повтор не может применить задачу наполовину."), "note");
    };
    steps.forEach((st, i) => {
      if (i === 5) return;
      button(ctrl, `${i + 1}`, () => { crash = i; draw(); [...ctrl.querySelectorAll("button")].forEach((b, j) => b.classList.toggle("on", j === i)); });
    });
    [...ctrl.querySelectorAll("button")].forEach((b, j) => b.classList.toggle("on", j === crash));
    draw();
  };

  // =====================================================================
  // D6. Queue-based load levelling (simulation)
  // =====================================================================
  W.queue = function (m, lang) {
    const ctrl = div(m, "wctrl");
    let workers = 2, jobSec = 90, burst = 12;
    const holder = div(m, "");
    const run = () => {
      // 60 simulated minutes, 1 s ticks; steady arrivals 1 PR / 2 min plus a burst at minute 10
      const total = 3600, arrivals = [];
      for (let t = 0; t < total; t += 120) arrivals.push(t);
      for (let k = 0; k < burst; k++) arrivals.push(600 + k * 2);
      arrivals.sort((a, b) => a - b);
      let qi = 0, queue = [], busy = [], depth = [], util = [], maxWait = 0, served = 0;
      for (let t = 0; t < total; t++) {
        while (qi < arrivals.length && arrivals[qi] <= t) queue.push(arrivals[qi++]);
        busy = busy.filter(end => end > t);
        while (busy.length < workers && queue.length) {
          const start = queue.shift();
          maxWait = Math.max(maxWait, t - start);
          busy.push(t + jobSec); served++;
        }
        if (t % 10 === 0) { depth.push(queue.length); util.push(busy.length); }
      }
      holder.innerHTML = "";
      const s = fig(holder, 960, 330, T(lang, "Queue depth over one hour", "Глубина очереди за час"));
      const x0 = 60, y0 = 230, w = 860, h = 180, maxD = Math.max(5, ...depth);
      el("line", { x1: x0, y1: y0, x2: x0 + w, y2: y0, class: "axis" }, s);
      el("line", { x1: x0, y1: y0 - h, x2: x0, y2: y0, class: "axis" }, s);
      for (let mn = 0; mn <= 60; mn += 10) text(s, x0 + w * mn / 60, y0 + 18, mn + " min", "tick");
      text(s, 14, y0 - h + 4, String(maxD), "tick", "start");
      text(s, 14, y0 + 4, "0", "tick", "start");
      const pts = depth.map((d, i) => `${x0 + w * i / (depth.length - 1)},${y0 - h * d / maxD}`).join(" ");
      el("polygon", { points: `${x0},${y0} ${pts} ${x0 + w},${y0}`, class: "area" }, s);
      el("polyline", { points: pts, class: "series" }, s);
      const upts = util.map((u, i) => `${x0 + w * i / (util.length - 1)},${y0 - h * (u / workers) * 0.25}`).join(" ");
      el("polyline", { points: upts, class: "series ok" }, s);
      text(s, x0 + w - 4, y0 - h * 0.25 - 6, T(lang, "busy workers (scaled)", "занятые воркеры (масштаб)"), "lbl ok", "end");
      text(s, x0 + w * 600 / 3600, y0 - h - 8, T(lang, `burst: ${burst} PRs at minute 10`, `всплеск: ${burst} PR на 10-й минуте`), "lbl hot");
      text(s, 480, 285, T(lang, `queue peak ${Math.max(...depth)} · longest wait ${Math.round(maxWait / 60)} min · ${served} jobs done · steady load 1 PR / 2 min`, `пик очереди ${Math.max(...depth)} · макс. ожидание ${Math.round(maxWait / 60)} мин · ${served} задач · фон 1 PR / 2 мин`), "note");
      text(s, 480, 310, T(lang, "The queue absorbs the burst; nothing is lost, nothing is overloaded. More workers drain it faster.", "Очередь поглощает всплеск; ничего не теряется и не перегружается. Больше воркеров — быстрее разбор."), "note");
    };
    slider(ctrl, T(lang, "workers", "воркеров"), 1, 6, workers, 1, v => { workers = v; run(); });
    slider(ctrl, T(lang, "job duration", "длительность задачи"), 30, 300, jobSec, 10, v => { jobSec = v; run(); }, v => v + " s");
    slider(ctrl, T(lang, "burst size", "размер всплеска"), 0, 40, burst, 1, v => { burst = v; run(); }, v => v + " PRs");
    run();
  };

  // =====================================================================
  // D7. Serverless: instances follow traffic
  // =====================================================================
  W.serverless = function (m, lang) {
    const s = fig(m, 960, 300, T(lang, "Scale to zero and cold starts", "Масштаб до нуля и холодные старты"));
    const x0 = 60, w = 860, y0 = 220;
    const reqs = [120, 125, 131, 140, 300, 302, 305, 309, 312, 318, 324, 330, 600, 605];
    el("line", { x1: x0, y1: y0, x2: x0 + w, y2: y0, class: "axis" }, s);
    for (let t = 0; t <= 720; t += 120) text(s, x0 + w * t / 720, y0 + 18, Math.round(t / 60) + " min", "tick");
    reqs.forEach(t => el("line", { x1: x0 + w * t / 720, y1: y0 - 2, x2: x0 + w * t / 720, y2: y0 - 14, class: "req" }, s));
    text(s, x0 + 4, y0 - 20, T(lang, "requests", "запросы"), "lbl", "start");
    // instances: 0 → 1 at first request (+cold start), → 3 at the burst, back to 0 after idle
    const inst = [[0, 0], [120, 0], [122, 1], [200, 1], [200, 0], [300, 0], [302, 1], [306, 2], [310, 3], [400, 3], [400, 0], [600, 0], [602, 1], [680, 1], [680, 0], [720, 0]];
    const pts = inst.map(([t, n]) => `${x0 + w * t / 720},${y0 - 40 - n * 40}`).join(" ");
    el("polyline", { points: pts, class: "series ok" }, s);
    [0, 1, 2, 3].forEach(n => text(s, x0 - 8, y0 - 36 - n * 40, String(n), "tick", "end"));
    text(s, x0 - 30, y0 - 190, T(lang, "instances", "экземпляры"), "lbl", "start");
    [122, 302, 602].forEach(t => { el("circle", { cx: x0 + w * t / 720, cy: y0 - 80, r: 5, class: "dot hot" }, s); });
    text(s, x0 + w * 122 / 720 + 10, y0 - 96, T(lang, "cold start: a new container boots before it answers (0.1–2 s)", "холодный старт: новый контейнер загружается, прежде чем ответить (0,1–2 с)"), "lbl hot", "start");
    text(s, 480, 270, T(lang, "You pay only while an instance runs. The worker's cache lives in the instance, so it is a bonus, not state the system depends on.", "Платят только пока экземпляр работает. Кэш воркера живёт в экземпляре — это бонус, а не состояние, от которого зависит система."), "note");
  };

  // =====================================================================
  // M1. Three pillars of observability
  // =====================================================================
  W.pillars = function (m, lang) {
    const s = fig(m, 960, 230, T(lang, "Logs, metrics, traces", "Логи, метрики, трейсы"));
    const cols = [
      [T(lang, "Logs", "Логи"), T(lang, "one line per event", "строка на событие"), T(lang, "what exactly happened", "что именно случилось"), T(lang, "costly to keep, slow to query", "дорого хранить, медленно искать")],
      [T(lang, "Metrics", "Метрики"), T(lang, "a number per time slot", "число на интервал времени"), T(lang, "how much, how fast, how often", "сколько, как быстро, как часто"), T(lang, "cheap, always on, no detail", "дёшево, всегда, без деталей")],
      [T(lang, "Traces", "Трейсы"), T(lang, "one request across services", "один запрос через сервисы"), T(lang, "where the time went", "куда ушло время"), T(lang, "needs instrumentation everywhere", "нужна инструментация везде")],
    ];
    cols.forEach((c, i) => {
      const x = 30 + i * 310;
      box(s, x, 20, 290, 56, c[0], c[1], i === 1 ? TONE.b : TONE.a);
      text(s, x + 145, 110, c[2], "row-t");
      text(s, x + 145, 140, c[3], "note");
    });
    el("rect", { x: 20, y: 170, width: 920, height: 44, rx: 8, class: "lane" }, s);
    text(s, 480, 197, T(lang, "This project uses metrics (the subject of this part) and plain logs on stderr for failures.", "В проекте используются метрики (тема этой части) и обычные логи в stderr для ошибок."), "note");
  };

  // =====================================================================
  // M2. Pull model timeline
  // =====================================================================
  W.pull = function (m, lang) {
    const s = fig(m, 960, 330, T(lang, "Prometheus pulls, the service only answers", "Prometheus забирает, сервис только отвечает"));
    box(s, 30, 30, 200, 56, "Prometheus", T(lang, "scrape every 5 s", "сбор каждые 5 с"), TONE.b);
    box(s, 30, 210, 200, 56, "analysis-worker", "GET /metrics", TONE.c);
    for (let i = 0; i < 6; i++) {
      const x = 300 + i * 105;
      arrow(s, x, 88, x, 206, i === 0 ? "GET /metrics" : "", {});
      arrow(s, x + 20, 206, x + 20, 90, i === 0 ? T(lang, "text page", "текст") : "", { ok: true });
      text(s, x + 10, 290, `t = ${i * 5} s`, "tick");
      el("circle", { cx: x + 60, cy: 150, r: 3, class: "dot" }, s);
    }
    el("line", { x1: 290, y1: 150, x2: 920, y2: 150, class: "axis" }, s);
    const sample = el("foreignObject", { x: 30, y: 300, width: 900, height: 30 }, s);
    const code = document.createElementNS("http://www.w3.org/1999/xhtml", "div");
    code.className = "mono small";
    code.textContent = 'jobs_processed_total{status="processed"} 8.0    job_duration_seconds_bucket{le="60"} 7.0    llm_cache_hits_total{policy="lru"} 9.0';
    sample.appendChild(code);
    text(s, 610, 120, T(lang, "each answer is a text page of current values; Prometheus stamps the time and stores it", "каждый ответ — текстовая страница текущих значений; Prometheus ставит время и сохраняет"), "note");
    text(s, 610, 250, T(lang, "the service does not know where Prometheus is; it just serves a page", "сервис не знает, где Prometheus; он просто отдаёт страницу"), "note");
  };

  // =====================================================================
  // M3. Counter + rate() with a restart (interactive)
  // =====================================================================
  W.rate = function (m, lang) {
    const ctrl = div(m, "wctrl");
    let windowS = 60;
    const holder = div(m, "");
    // samples every 5 s for 150 s; counter increments, process restarts at t=85
    const samples = [];
    let v = 0;
    for (let t = 0; t <= 150; t += 5) {
      if (t === 85) v = 0;
      v += t < 85 ? (t % 15 === 0 ? 3 : 1) : 2;
      samples.push([t, v]);
    }
    const draw = () => {
      holder.innerHTML = "";
      const s = fig(holder, 960, 360, T(lang, "A counter, a restart, and rate()", "Счётчик, рестарт и rate()"));
      const x0 = 60, w = 860, y0 = 150, h = 110, maxV = 40;
      el("line", { x1: x0, y1: y0, x2: x0 + w, y2: y0, class: "axis" }, s);
      samples.forEach(([t, val], i) => {
        const x = x0 + w * t / 150, y = y0 - h * val / maxV;
        el("circle", { cx: x, cy: y, r: 3.5, class: "dot" }, s);
        if (i) { const [pt, pv] = samples[i - 1]; el("line", { x1: x0 + w * pt / 150, y1: y0 - h * pv / maxV, x2: x, y2: y, class: "series thin" }, s); }
      });
      text(s, x0 + w * 85 / 150, y0 - h - 10, T(lang, "restart: the counter falls to 0", "рестарт: счётчик падает до 0"), "lbl hot");
      el("line", { x1: x0 + w * 85 / 150, y1: y0 - h, x2: x0 + w * 85 / 150, y2: y0, class: "req hot" }, s);
      text(s, 20, y0 - h, "40", "tick", "start"); text(s, 20, y0, "0", "tick", "start");
      text(s, x0, y0 - h - 10, T(lang, "jobs_processed_total (raw)", "jobs_processed_total (сырое)"), "lbl", "start");
      // rate over window at each sample
      const y1 = 320, h1 = 90;
      el("line", { x1: x0, y1: y1, x2: x0 + w, y2: y1, class: "axis" }, s);
      const rates = samples.map(([t]) => {
        const inWin = samples.filter(([u]) => u > t - windowS && u <= t);
        if (inWin.length < 2) return [t, null];
        let inc = 0;
        for (let i = 1; i < inWin.length; i++) { const d = inWin[i][1] - inWin[i - 1][1]; inc += d >= 0 ? d : inWin[i][1]; }
        return [t, inc / (inWin[inWin.length - 1][0] - inWin[0][0])];
      }).filter(r => r[1] != null);
      const maxR = 0.6;
      const pts = rates.map(([t, r]) => `${x0 + w * t / 150},${y1 - h1 * Math.min(r, maxR) / maxR}`).join(" ");
      el("polyline", { points: pts, class: "series ok" }, s);
      text(s, 20, y1 - h1, "0.6/s", "tick", "start"); text(s, 20, y1, "0", "tick", "start");
      text(s, x0, y1 - h1 - 10, `rate(jobs_processed_total[${windowS}s])`, "lbl ok", "start");
      for (let t = 0; t <= 150; t += 30) text(s, x0 + w * t / 150, y1 + 18, t + " s", "tick");
      text(s, 480, 355, T(lang, "rate() = increase inside the window ÷ window length. A drop to zero is read as a restart and the increase before it is kept, not subtracted.", "rate() = прирост внутри окна ÷ длина окна. Падение до нуля читается как рестарт, и прирост до него сохраняется, а не вычитается."), "note");
    };
    slider(ctrl, T(lang, "window", "окно"), 15, 120, windowS, 5, v => { windowS = v; draw(); }, v => v + " s");
    draw();
  };

  // =====================================================================
  // M4. Metric types
  // =====================================================================
  W.types = function (m, lang) {
    const s = fig(m, 960, 250, T(lang, "Counter, gauge, histogram", "Counter, gauge, histogram"));
    const panel = (x, title, sub) => { box(s, x, 20, 290, 40, title, "", TONE.a); text(s, x + 145, 225, sub, "note"); el("line", { x1: x + 20, y1: 190, x2: x + 270, y2: 190, class: "axis" }, s); };
    panel(30, "counter", T(lang, "only up; look at rate()", "только вверх; смотрите rate()"));
    panel(340, "gauge", T(lang, "up and down; look at the value", "вверх и вниз; смотрите значение"));
    panel(650, "histogram", T(lang, "counts per bucket (le=…); quantiles later", "число в корзинах (le=…); квантили потом"));
    let pts = "", v = 0;
    for (let i = 0; i <= 12; i++) { v += [1, 0, 2, 1, 3, 0, 1, 2, 1, 0, 2, 1, 1][i]; pts += `${50 + i * 20},${190 - v * 7} `; }
    el("polyline", { points: pts.trim(), class: "series" }, s);
    pts = "";
    for (let i = 0; i <= 12; i++) pts += `${360 + i * 20},${150 + Math.sin(i / 1.5) * 30} `;
    el("polyline", { points: pts.trim(), class: "series ok" }, s);
    const buckets = [["5", 1], ["15", 2], ["30", 4], ["60", 6], ["120", 7], ["300", 8], ["600", 8], ["+Inf", 8]];
    buckets.forEach(([le, c], i) => {
      const x = 672 + i * 32;
      el("rect", { x, y: 190 - c * 13, width: 24, height: c * 13, rx: 3, class: "bar tone-c" }, s);
      text(s, x + 12, 205, le, "tick");
    });
    text(s, 795, 80, T(lang, "cumulative: le=60 counts everything ≤ 60 s", "накопительно: le=60 считает всё ≤ 60 с"), "note");
  };

  // =====================================================================
  // M5. histogram_quantile (interactive)
  // =====================================================================
  W.quantile = function (m, lang) {
    const ctrl = div(m, "wctrl");
    let q = 0.95;
    const holder = div(m, "");
    const les = [5, 15, 30, 60, 120, 300, 600, Infinity];
    const counts = [1, 3, 9, 17, 25, 29, 30, 30]; // cumulative
    const draw = () => {
      holder.innerHTML = "";
      const s = fig(holder, 960, 330, "histogram_quantile");
      const total = counts[counts.length - 1], target = q * total;
      let bi = counts.findIndex(c => c >= target);
      const lo = bi === 0 ? 0 : les[bi - 1], hi = les[bi];
      const cLo = bi === 0 ? 0 : counts[bi - 1], cHi = counts[bi];
      const est = hi === Infinity ? lo : lo + (hi - lo) * (target - cLo) / (cHi - cLo);
      les.forEach((le, i) => {
        const x = 60 + i * 110, hgt = counts[i] * 6;
        el("rect", { x, y: 230 - hgt, width: 80, height: hgt, rx: 4, class: "bar " + (i === bi ? "tone-hot" : "tone-c") }, s);
        text(s, x + 40, 250, "le=" + (le === Infinity ? "+Inf" : le), "tick");
        text(s, x + 40, 222 - hgt, String(counts[i]), "tick");
      });
      el("line", { x1: 50, y1: 230 - target * 6, x2: 930, y2: 230 - target * 6, class: "req hot" }, s);
      text(s, 930, 224 - target * 6, `${q} × ${total} = ${target.toFixed(1)}`, "lbl hot", "end");
      text(s, 480, 290, T(lang, `The ${target.toFixed(1)}th observation falls in bucket (${lo}, ${hi === Infinity ? "+Inf" : hi}]; assuming values spread evenly inside it: p${Math.round(q * 100)} ≈ ${est.toFixed(0)} s`, `${target.toFixed(1)}-е наблюдение попадает в корзину (${lo}, ${hi === Infinity ? "+Inf" : hi}]; считая значения равномерными внутри: p${Math.round(q * 100)} ≈ ${est.toFixed(0)} с`), "note");
      text(s, 480, 315, T(lang, "Precision = bucket width. Buckets must be chosen around the values that matter (here: the 600 s deadline).", "Точность = ширина корзины. Корзины выбирают вокруг значений, которые важны (здесь: дедлайн 600 с)."), "note");
    };
    slider(ctrl, T(lang, "quantile", "квантиль"), 0.5, 0.99, q, 0.01, v => { q = v; draw(); }, v => v.toFixed(2));
    draw();
  };

  // =====================================================================
  // M6. Vector matching: the sum() bug
  // =====================================================================
  W.matching = function (m, lang) {
    const s = fig(m, 960, 370, T(lang, "Why ratios need sum() on both sides", "Почему долям нужен sum() с обеих сторон"));
    text(s, 240, 30, T(lang, "as written (wrong)", "как было (неверно)"), "lane-t");
    text(s, 720, 30, T(lang, "with sum() (right)", "с sum() (верно)"), "lane-t");
    box(s, 30, 60, 210, 44, "jobs{status=\"failed\"}", "0.02 /s", TONE.c);
    text(s, 250, 88, "÷", "op");
    box(s, 270, 60, 210, 44, "jobs{status=\"failed\"}", "0.02 /s", TONE.c);
    box(s, 270, 120, 210, 44, "jobs{status=\"processed\"}", "0.13 /s", TONE.c);
    box(s, 270, 180, 210, 44, "jobs{status=\"skipped\"}", "0.01 /s", TONE.c);
    arrow(s, 240, 82, 268, 82, "", { hot: true });
    text(s, 255, 245, T(lang, "the operator pairs series with identical labels: failed ÷ failed = 1.0; the other two have no partner and vanish", "оператор сопоставляет ряды с одинаковыми метками: failed ÷ failed = 1.0; у двух других нет пары, и они исчезают"), "note", "middle", 430);
    box(s, 520, 60, 200, 44, "sum(failed)", "0.02 /s", TONE.b);
    text(s, 730, 88, "÷", "op");
    box(s, 740, 60, 200, 44, "sum(all)", "0.16 /s", TONE.b);
    el("rect", { x: 520, y: 130, width: 420, height: 44, rx: 9, class: "bx tone-hot" }, s);
    text(s, 730, 158, "= 0.125  →  12.5 % failing", "bx-t");
    text(s, 730, 245, T(lang, "sum() drops the labels on both sides, so there is exactly one series each and the division is the real ratio", "sum() убирает метки с обеих сторон: по одному ряду с каждой стороны, и деление даёт настоящую долю"), "note", "middle", 420);
    text(s, 480, 335, T(lang, "Found in this project with a rule unit test: the old alert fired \"more than 20 % failing\" on one failed job in a hundred.", "Найдено в этом проекте юнит-тестом правил: старый алерт срабатывал «более 20 % ошибок» на одну упавшую задачу из ста."), "note");
  };

  // =====================================================================
  // M7. Alert states with `for` (interactive)
  // =====================================================================
  W.alert = function (m, lang) {
    const ctrl = div(m, "wctrl");
    let forMin = 15;
    const holder = div(m, "");
    const cond = t => (t >= 10 && t < 18) || (t >= 30 && t < 58); // minutes where expr > threshold
    const draw = () => {
      holder.innerHTML = "";
      const s = fig(holder, 960, 260, T(lang, "inactive → pending → firing", "inactive → pending → firing"));
      const x0 = 60, w = 860;
      let since = null;
      for (let t = 0; t < 70; t++) {
        const on = cond(t);
        if (on && since === null) since = t;
        if (!on) since = null;
        const state = !on ? "inactive" : t - since >= forMin ? "firing" : "pending";
        el("rect", { x: x0 + w * t / 70, y: 80, width: w / 70 + 0.5, height: 50, class: "state " + state }, s);
        el("rect", { x: x0 + w * t / 70, y: 150, width: w / 70 + 0.5, height: 24, class: "state " + (on ? "cond" : "inactive") }, s);
      }
      text(s, x0 - 6, 110, T(lang, "alert", "алерт"), "lbl", "end");
      text(s, x0 - 6, 167, T(lang, "expr > 0.2", "expr > 0.2"), "lbl", "end");
      for (let t = 0; t <= 70; t += 10) text(s, x0 + w * t / 70, 200, t + " min", "tick");
      [["inactive", T(lang, "inactive", "inactive")], ["pending", T(lang, "pending: true, but not yet for 'for'", "pending: истинно, но ещё не 'for'")], ["firing", T(lang, "firing → Alertmanager", "firing → Alertmanager")]].forEach(([c, l], i) => {
        el("rect", { x: 60 + i * 300, y: 225, width: 16, height: 16, class: "state " + c }, s);
        text(s, 84 + i * 300, 238, l, "lbl", "start");
      });
      text(s, 480, 50, T(lang, `The 8-minute spike never fires with for: ${forMin}m; the long one fires after ${forMin} minutes of being true.`, `Всплеск на 8 минут при for: ${forMin}m не срабатывает; долгий срабатывает через ${forMin} минут истинности.`), "note");
    };
    slider(ctrl, "for:", 0, 30, forMin, 1, v => { forMin = v; draw(); }, v => v + "m");
    draw();
  };

  // =====================================================================
  // M8. Grafana dashboard anatomy
  // =====================================================================
  W.dashboard = function (m, lang) {
    const s = fig(m, 960, 330, T(lang, "Anatomy of the dashboard", "Анатомия дашборда"));
    el("rect", { x: 20, y: 20, width: 920, height: 290, rx: 10, class: "lane" }, s);
    const panel = (x, y, w, h, title, body) => { el("rect", { x, y, width: w, height: h, rx: 6, class: "panel" }, s); text(s, x + 10, y + 18, title, "panel-t", "start"); if (body) body(x, y, w, h); };
    panel(35, 35, 440, 120, T(lang, "Jobs by outcome (per minute)  ·  time series", "Задачи по исходу (в минуту)  ·  time series"), (x, y, w, h) => {
      let p = ""; for (let i = 0; i <= 20; i++) p += `${x + 20 + i * 20},${y + 95 - (i > 8 && i < 12 ? 50 : 15 + (i % 3) * 5)} `;
      el("polyline", { points: p.trim(), class: "series ok" }, s);
      text(s, x + w - 10, y + h - 8, "rate(jobs_processed_total[5m]) * 60", "mono-lbl", "end");
    });
    panel(490, 35, 215, 120, T(lang, "LLM cache hit ratio  ·  stat", "Доля попаданий в кэш  ·  stat"), (x, y) => { text(s, x + 107, y + 85, "85.7 %", "big ok"); });
    panel(720, 35, 205, 120, T(lang, "Tests passed ratio  ·  stat", "Доля прошедших тестов  ·  stat"), (x, y) => { text(s, x + 102, y + 85, "100 %", "big ok"); });
    panel(35, 170, 440, 125, T(lang, "Job duration p50 / p95  ·  time series", "Длительность p50 / p95  ·  time series"), (x, y, w, h) => {
      text(s, x + w - 10, y + h - 8, "histogram_quantile(0.95, rate(job_duration_seconds_bucket[15m]))", "mono-lbl", "end");
    });
    panel(490, 170, 435, 125, T(lang, "LLM tokens per minute  ·  time series", "Токены LLM в минуту  ·  time series"), (x, y, w, h) => {
      text(s, x + 10, y + 50, T(lang, "every panel = one PromQL query + a unit + a legend", "каждая панель = один запрос PromQL + единица + легенда"), "note", "start");
      text(s, x + 10, y + 75, T(lang, "the whole dashboard is one JSON file in git, loaded at start-up", "весь дашборд — один JSON-файл в git, загружаемый при старте"), "note", "start");
      text(s, x + 10, y + 100, T(lang, "a data source YAML points Grafana at Prometheus", "YAML источника данных указывает Grafana на Prometheus"), "note", "start");
    });
  };

  // =====================================================================
  // A2. Kahn's algorithm step-through (interactive)
  // =====================================================================
  W.kahn = function (m, lang) {
    const examples = {
      dag: {
        nodes: ["models.py", "pricing.py", "checkout.py", "report.py", "cli.py"],
        pos: [[120, 150], [330, 60], [540, 150], [330, 240], [760, 150]],
        edges: [[0, 1], [1, 2], [0, 3], [2, 4], [3, 4]],
      },
      cycle: {
        nodes: ["a.py", "b.py", "c.py", "d.py"],
        pos: [[160, 150], [400, 150], [640, 60], [640, 240]],
        edges: [[0, 1], [1, 0], [1, 2], [1, 3]],
      },
    };
    const ctrl = div(m, "wctrl");
    let exName = "dag", st;
    const holder = div(m, "");
    const log = div(m, "wlog");
    const reset = () => {
      const ex = examples[exName];
      st = { indeg: ex.nodes.map(() => 0), ready: [], out: [], done: new Set(), used: new Set(), current: null, finished: false };
      ex.edges.forEach(([a, b]) => st.indeg[b]++);
      ex.nodes.forEach((n, i) => { if (st.indeg[i] === 0) st.ready.push(i); });
      log.textContent = T(lang, "In-degrees counted. Ready (in-degree 0): ", "Входящие рёбра посчитаны. Готовы (in-degree 0): ") + st.ready.map(i => ex.nodes[i]).join(", ");
      draw();
    };
    const step = () => {
      const ex = examples[exName];
      if (st.finished) return;
      if (!st.ready.length) {
        st.finished = true;
        const left = ex.nodes.map((n, i) => i).filter(i => !st.done.has(i));
        log.textContent = left.length
          ? T(lang, `Queue empty but ${left.length} node(s) remain: ${left.map(i => ex.nodes[i]).join(", ")} → they are in or behind a cycle. Reported, kept in original order.`, `Очередь пуста, но осталось ${left.length}: ${left.map(i => ex.nodes[i]).join(", ")} → они в цикле или за ним. В отчёт, исходный порядок.`)
          : T(lang, "Done. Order: ", "Готово. Порядок: ") + st.out.map(i => ex.nodes[i]).join(" → ");
        draw();
        return;
      }
      st.ready.sort((a, b) => a - b); // min-heap by original position
      const n = st.ready.shift();
      st.current = n; st.done.add(n); st.out.push(n);
      const freed = [];
      ex.edges.forEach(([a, b], ei) => { if (a === n) { st.used.add(ei); st.indeg[b]--; if (st.indeg[b] === 0) { st.ready.push(b); freed.push(b); } } });
      log.textContent = T(lang, `Emit ${ex.nodes[n]} (smallest original position among ready). `, `Выдаём ${ex.nodes[n]} (наименьшая исходная позиция среди готовых). `)
        + (freed.length ? T(lang, `Its dependents' in-degree drops; now ready: ${freed.map(i => ex.nodes[i]).join(", ")}.`, `У зависимых уменьшается in-degree; теперь готовы: ${freed.map(i => ex.nodes[i]).join(", ")}.`) : T(lang, "No new node became ready.", "Новых готовых вершин нет."));
      draw();
    };
    const draw = () => {
      const ex = examples[exName];
      holder.innerHTML = "";
      const s = fig(holder, 960, 320, T(lang, "Kahn's algorithm", "Алгоритм Кана"));
      ex.edges.forEach(([a, b], ei) => {
        const [x1, y1] = ex.pos[a], [x2, y2] = ex.pos[b];
        const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy), ux = dx / len, uy = dy / len;
        const bend = (a === 1 && b === 0) ? 1 : 0; // the back edge of the cycle example
        const path = bend ? `M${x1 - 60 * ux + 0},${y1 + 40} Q${(x1 + x2) / 2},${y1 + 90} ${x2 + 60 * ux},${y2 + 40}` : `M${x1 + 62 * ux},${y1 + 26 * uy} L${x2 - 62 * ux},${y2 - 26 * uy}`;
        el("path", { d: path, class: "ln " + (st.used.has(ei) ? "faded" : ""), "marker-end": `url(#ah-${s.dataset.uid})` }, s);
      });
      ex.nodes.forEach((n, i) => {
        const [x, y] = ex.pos[i];
        const tone = st.done.has(i) ? (st.current === i ? TONE.hot : TONE.b) : st.ready.includes(i) ? TONE.c : TONE.a;
        box(s, x - 60, y - 24, 120, 48, n, "in-degree " + st.indeg[i], tone);
      });
      text(s, 20, 300, T(lang, "ready queue: ", "очередь готовых: ") + (st.ready.map(i => ex.nodes[i]).join(", ") || "∅"), "row-t", "start");
      text(s, 940, 300, T(lang, "output: ", "вывод: ") + (st.out.map(i => ex.nodes[i]).join(" → ") || "∅"), "row-t", "end");
    };
    button(ctrl, T(lang, "Step", "Шаг"), step);
    button(ctrl, T(lang, "Reset", "Сброс"), reset);
    button(ctrl, T(lang, "Example: project files", "Пример: файлы проекта"), () => { exName = "dag"; reset(); });
    button(ctrl, T(lang, "Example: with a cycle", "Пример: с циклом"), () => { exName = "cycle"; reset(); });
    reset();
  };

  // =====================================================================
  // A3. LRU cache internals (interactive)
  // =====================================================================
  function makeLru(cap) {
    const nodes = new Map();
    const head = { key: "HEAD" }, tail = { key: "TAIL" };
    head.next = tail; tail.prev = head;
    const unlink = n => { n.prev.next = n.next; n.next.prev = n.prev; };
    const linkFront = n => { n.prev = head; n.next = head.next; head.next.prev = n; head.next = n; };
    return {
      cap, hits: 0, misses: 0, evicted: null,
      get(k) { const n = nodes.get(k); this.evicted = null; if (!n) { this.misses++; return null; } this.hits++; unlink(n); linkFront(n); return n.key; },
      put(k) { this.evicted = null; let n = nodes.get(k); if (n) { unlink(n); linkFront(n); return; } if (nodes.size >= cap) { const lru = tail.prev; unlink(lru); nodes.delete(lru.key); this.evicted = lru.key; } n = { key: k }; nodes.set(k, n); linkFront(n); },
      order() { const o = []; for (let n = head.next; n !== tail; n = n.next) o.push(n.key); return o; },
      keys() { return [...nodes.keys()]; },
    };
  }
  W.lru = function (m, lang) {
    const ctrl = div(m, "wctrl");
    let cache = makeLru(3), last = "";
    const holder = div(m, "");
    const log = div(m, "wlog");
    const draw = () => {
      holder.innerHTML = "";
      const s = fig(holder, 960, 300, "LRU");
      text(s, 20, 36, T(lang, "hash map: key → node", "хеш-таблица: ключ → узел"), "row-t", "start");
      const keys = cache.keys();
      ["A", "B", "C", "D", "E"].forEach((k, i) => {
        const has = keys.includes(k);
        el("rect", { x: 20 + i * 70, y: 50, width: 60, height: 40, rx: 6, class: "bx " + (has ? "tone-c" : "tone-d") }, s);
        text(s, 50 + i * 70, 75, has ? k + " → •" : k + " → ∅", "bx-s");
      });
      text(s, 20, 140, T(lang, "doubly linked list: most recent on the left", "двусвязный список: самое свежее слева"), "row-t", "start");
      const order = cache.order();
      const items = ["HEAD", ...order, "TAIL"];
      items.forEach((k, i) => {
        const x = 20 + i * 150;
        const sentinel = k === "HEAD" || k === "TAIL";
        box(s, x, 160, 120, 50, k, sentinel ? T(lang, "sentinel", "страж") : k === last ? T(lang, "just used", "только что") : "", sentinel ? TONE.d : k === last ? TONE.hot : TONE.b, sentinel);
        if (i < items.length - 1) { arrow(s, x + 120, 178, x + 150, 178, "", {}); arrow(s, x + 150, 195, x + 120, 195, "", {}); }
      });
      if (order.length) text(s, 20 + (items.length - 2) * 150 + 60, 235, T(lang, "← evicted next", "← вытеснится следующим"), "lbl hot");
      text(s, 480, 280, T(lang, `capacity ${cache.cap} · hits ${cache.hits} · misses ${cache.misses}`, `ёмкость ${cache.cap} · попаданий ${cache.hits} · промахов ${cache.misses}`) + (cache.evicted ? T(lang, ` · evicted ${cache.evicted}`, ` · вытеснен ${cache.evicted}`) : ""), "note");
    };
    const act = (op, k) => {
      const before = cache.keys().includes(k);
      if (op === "get") { const r = cache.get(k); log.textContent = r ? T(lang, `get(${k}): hit. Unlink the node and re-link it after HEAD: two pointer swaps, no scanning.`, `get(${k}): попадание. Отвязать узел и привязать после HEAD: две перестановки указателей, без сканирования.`) : T(lang, `get(${k}): miss. The map has no node for ${k}.`, `get(${k}): промах. В таблице нет узла для ${k}.`); }
      else { cache.put(k); log.textContent = before ? T(lang, `put(${k}): already cached; moved to the front.`, `put(${k}): уже в кэше; перенесён вперёд.`) : cache.evicted ? T(lang, `put(${k}): full, so TAIL.prev (${cache.evicted}) is unlinked and dropped from the map, then ${k} goes to the front.`, `put(${k}): полно, поэтому TAIL.prev (${cache.evicted}) отвязывается и удаляется из таблицы, затем ${k} встаёт вперёд.`) : T(lang, `put(${k}): new node after HEAD, map entry added.`, `put(${k}): новый узел после HEAD, запись в таблице добавлена.`); }
      last = k; draw();
    };
    ["A", "B", "C", "D", "E"].forEach(k => button(ctrl, "get " + k, () => act("get", k)));
    ["A", "B", "C", "D", "E"].forEach(k => button(ctrl, "put " + k, () => act("put", k)));
    button(ctrl, T(lang, "Reset", "Сброс"), () => { cache = makeLru(3); last = ""; log.textContent = ""; draw(); });
    draw();
  };

  // =====================================================================
  // A4. LFU cache internals (interactive)
  // =====================================================================
  function makeLfu(cap) {
    const values = new Map(), freq = new Map(), buckets = new Map();
    let minF = 0;
    const bump = k => {
      const f = freq.get(k); buckets.get(f).delete(k);
      if (!buckets.get(f).size) { buckets.delete(f); if (minF === f) minF = f + 1; }
      freq.set(k, f + 1); if (!buckets.has(f + 1)) buckets.set(f + 1, new Set()); buckets.get(f + 1).add(k);
    };
    return {
      cap, hits: 0, misses: 0, evicted: null,
      get(k) { this.evicted = null; if (!values.has(k)) { this.misses++; return null; } this.hits++; bump(k); return k; },
      put(k) { this.evicted = null; if (values.has(k)) { bump(k); return; } if (values.size >= cap) { const b = buckets.get(minF); const victim = b.values().next().value; b.delete(victim); if (!b.size) buckets.delete(minF); values.delete(victim); freq.delete(victim); this.evicted = victim; } values.set(k, true); freq.set(k, 1); if (!buckets.has(1)) buckets.set(1, new Set()); buckets.get(1).add(k); minF = 1; },
      state() { return { buckets: [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([f, s]) => [f, [...s]]), minF, keys: [...values.keys()] }; },
    };
  }
  W.lfu = function (m, lang) {
    const ctrl = div(m, "wctrl");
    let cache = makeLfu(3), last = "";
    const holder = div(m, "");
    const log = div(m, "wlog");
    const draw = () => {
      holder.innerHTML = "";
      const s = fig(holder, 960, 300, "LFU");
      const st = cache.state();
      text(s, 20, 36, T(lang, "buckets: use count → keys in insertion order (oldest first)", "корзины: число обращений → ключи в порядке добавления (старые первыми)"), "row-t", "start");
      const fs = [1, 2, 3, 4, 5];
      fs.forEach((f, i) => {
        const x = 20 + i * 185;
        const isMin = f === st.minF && st.keys.length;
        el("rect", { x, y: 55, width: 170, height: 150, rx: 9, class: "bx " + (isMin ? "tone-hot" : "tone-d"), "stroke-dasharray": isMin ? "" : "6 5" }, s);
        text(s, x + 85, 80, T(lang, `used ${f}×`, `${f}× обращений`), "bx-t");
        const entry = st.buckets.find(b => b[0] === f);
        (entry ? entry[1] : []).forEach((k, j) => { el("rect", { x: x + 15 + j * 50, y: 100, width: 42, height: 36, rx: 6, class: "bx " + (k === last ? "tone-hot" : "tone-b") }, s); text(s, x + 36 + j * 50, 124, k, "bx-t"); });
        if (isMin) text(s, x + 85, 190, T(lang, "min pointer: evict from here", "min-указатель: вытеснять отсюда"), "lbl hot");
      });
      text(s, 480, 240, T(lang, "a use moves the key one bucket to the right; eviction pops the oldest key of the min bucket", "обращение переносит ключ на корзину вправо; вытеснение забирает самый старый ключ из min-корзины"), "note");
      text(s, 480, 280, T(lang, `capacity ${cache.cap} · hits ${cache.hits} · misses ${cache.misses}`, `ёмкость ${cache.cap} · попаданий ${cache.hits} · промахов ${cache.misses}`) + (cache.evicted ? T(lang, ` · evicted ${cache.evicted}`, ` · вытеснен ${cache.evicted}`) : ""), "note");
    };
    const act = (op, k) => {
      if (op === "get") { const r = cache.get(k); log.textContent = r ? T(lang, `get(${k}): hit, count +1 → moved one bucket right.`, `get(${k}): попадание, счётчик +1 → на корзину правее.`) : T(lang, `get(${k}): miss.`, `get(${k}): промах.`); }
      else { cache.put(k); log.textContent = cache.evicted ? T(lang, `put(${k}): full → the oldest key of the min bucket (${cache.evicted}) is evicted; ${k} enters bucket 1 and min = 1.`, `put(${k}): полно → самый старый ключ min-корзины (${cache.evicted}) вытеснен; ${k} входит в корзину 1, min = 1.`) : T(lang, `put(${k}): enters bucket 1 (or count +1 if present).`, `put(${k}): в корзину 1 (или счётчик +1, если уже есть).`); }
      last = k; draw();
    };
    ["A", "B", "C", "D", "E"].forEach(k => button(ctrl, "get " + k, () => act("get", k)));
    ["A", "B", "C", "D", "E"].forEach(k => button(ctrl, "put " + k, () => act("put", k)));
    button(ctrl, T(lang, "Reset", "Сброс"), () => { cache = makeLfu(3); last = ""; log.textContent = ""; draw(); });
    draw();
  };

  // =====================================================================
  // A5. LRU vs LFU on two workloads (interactive)
  // =====================================================================
  W.race = function (m, lang) {
    const ctrl = div(m, "wctrl");
    let cap = 3;
    const holder = div(m, "");
    const patterns = {
      bursty: { name: T(lang, "bursty re-runs: three files pushed twice, then three others twice, then three more", "всплески: три файла дважды, затем три других дважды, затем ещё три"), seq: "ABCABCDEFDEFGHIGHI".split("") },
      hot: { name: T(lang, "hot key: A used twice at the start, then every fourth access; the others pass through once", "горячий ключ: A дважды в начале, затем каждое четвёртое обращение; остальные по разу"), seq: "AABCDAEFGAHIJAKLMA".split("") },
    };
    const simulate = (seq, mk) => { const c = mk(cap); seq.forEach(k => { if (c.get(k) === null) c.put(k); }); return c; };
    const draw = () => {
      holder.innerHTML = "";
      const s = fig(holder, 960, 300, T(lang, "LRU vs LFU", "LRU и LFU"));
      Object.entries(patterns).forEach(([id, p], row) => {
        const y = 40 + row * 130;
        text(s, 20, y, p.name, "row-t", "start");
        [["LRU", makeLru], ["LFU", makeLfu]].forEach(([nm, mk], i) => {
          const c = simulate(p.seq, mk);
          const ratio = c.hits / (c.hits + c.misses);
          const x = 40 + i * 470;
          text(s, x, y + 36, nm, "bx-t", "start");
          el("rect", { x: x + 50, y: y + 20, width: 240, height: 24, rx: 5, class: "bar tone-d" }, s);
          el("rect", { x: x + 50, y: y + 20, width: 240 * ratio, height: 24, rx: 5, class: "bar " + (ratio >= 0.4 ? "tone-b" : "tone-c") }, s);
          text(s, x + 300, y + 37, `${c.hits} / ${c.hits + c.misses}  (${Math.round(ratio * 100)} %)`, "lbl", "start");
        });
        text(s, 20, y + 75, T(lang, "sequence: ", "последовательность: ") + p.seq.join(" "), "mono-lbl", "start");
      });
      text(s, 480, 290, T(lang, `capacity ${cap}. LRU keeps what was used recently; LFU keeps what was used often. The workload decides which wins.`, `ёмкость ${cap}. LRU хранит недавнее; LFU — частое. Какая выиграет, решает нагрузка.`), "note");
    };
    slider(ctrl, T(lang, "capacity", "ёмкость"), 2, 5, cap, 1, v => { cap = v; draw(); });
    draw();
  };

  // ---------- mount everything ----------
  document.querySelectorAll("[data-widget]").forEach(node => {
    const name = node.dataset.widget;
    const lang = node.closest("[lang]").getAttribute("lang");
    if (W[name]) { try { W[name](node, lang); } catch (e) { node.textContent = "widget error: " + e.message; } }
  });
})();
