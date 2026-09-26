/* ФСП Контест — клиентская логика (без inline-скриптов, совместимо со строгим CSP) */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  /* ---------- мобильное меню ---------- */
  const burger = $("[data-burger]");
  if (burger) burger.addEventListener("click", () => {
    const nav = $("#nav");
    nav.classList.toggle("is-open");
    burger.setAttribute("aria-expanded", nav.classList.contains("is-open"));
  });

  /* ---------- выпадающее меню профиля ---------- */
  document.addEventListener("click", (e) => {
    $$("details.menu[open]").forEach((d) => { if (!d.contains(e.target)) d.removeAttribute("open"); });
  });

  /* ---------- уведомления (toasts) ---------- */
  $$(".toast").forEach((t, i) => {
    const close = () => { t.classList.add("is-hiding"); setTimeout(() => t.remove(), 300); };
    const btn = $("button", t);
    if (btn) btn.addEventListener("click", close);
    if (!t.classList.contains("toast--error")) setTimeout(close, 5500 + i * 400);
  });

  /* ---------- обратный отсчёт ---------- */
  const pad = (n) => String(n).padStart(2, "0");
  function tick(el) {
    const target = Date.parse(el.dataset.countdown);
    let diff = Math.max(0, Math.floor((target - Date.now()) / 1000));
    const d = Math.floor(diff / 86400); diff %= 86400;
    const h = Math.floor(diff / 3600); diff %= 3600;
    const m = Math.floor(diff / 60); const s = diff % 60;
    if (el.dataset.mode === "mini") {
      el.textContent = (d ? d + "д " : "") + pad(h) + ":" + pad(m) + ":" + pad(s);
    } else {
      const set = (k, v) => { const n = $("[data-u=" + k + "]", el); if (n) n.textContent = pad(v); };
      set("d", d); set("h", h); set("m", m); set("s", s);
      const du = $("[data-unit=d]", el);
      if (du) du.hidden = d === 0;
    }
    if (target <= Date.now() && el.dataset.reload && !el.dataset.done) {
      el.dataset.done = "1";
      setTimeout(() => location.reload(), 1500);
    }
  }
  const timers = $$("[data-countdown]");
  if (timers.length) { timers.forEach(tick); setInterval(() => timers.forEach(tick), 1000); }

  /* ---------- счётчики на главной ---------- */
  const counters = $$("[data-count]");
  const animateCount = (el) => {
    const end = parseInt(el.dataset.count, 10) || 0; const dur = 1200; const t0 = performance.now();
    const step = (t) => { const p = Math.min(1, (t - t0) / dur); el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3))).toLocaleString("ru-RU"); if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  };

  /* ---------- появление при скролле ---------- */
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        en.target.classList.add("is-in");
        if (en.target.dataset.count !== undefined) animateCount(en.target);
        io.unobserve(en.target);
      });
    }, { threshold: 0.12 });
    $$(".reveal").forEach((el) => io.observe(el));
    counters.forEach((el) => io.observe(el));
  } else {
    $$(".reveal").forEach((el) => el.classList.add("is-in"));
  }

  /* ---------- подтверждение опасных действий ---------- */
  $$("form[data-confirm]").forEach((f) => f.addEventListener("submit", (e) => {
    if (!window.confirm(f.dataset.confirm)) e.preventDefault();
  }));

  /* ---------- копирование ---------- */
  $$("[data-copy]").forEach((b) => b.addEventListener("click", () => {
    const src = document.getElementById(b.dataset.copy);
    if (!src || !navigator.clipboard) return;
    navigator.clipboard.writeText(src.textContent).then(() => {
      const old = b.textContent; b.textContent = "Скопировано"; setTimeout(() => (b.textContent = old), 1400);
    });
  }));

  /* ---------- клиентские вкладки ---------- */
  $$("[data-tabs]").forEach((wrap) => {
    const btns = $$("[data-tab]", wrap);
    const panes = $$("[data-pane-id]", wrap.closest("[data-tabs-scope]") || document);
    btns.forEach((b) => b.addEventListener("click", () => {
      btns.forEach((x) => x.classList.toggle("is-active", x === b));
      panes.forEach((p) => (p.hidden = p.dataset.paneId !== b.dataset.tab));
    }));
  });

  /* ---------- редактор кода ---------- */
  $$("textarea[data-editor]").forEach((ta) => {
    const gutter = $("[data-gutter]", ta.closest(".editor"));
    const info = $("[data-editor-info]", ta.closest(".editor"));
    const update = () => {
      const lines = ta.value.split("\n").length;
      if (gutter) gutter.textContent = Array.from({ length: lines }, (_, i) => i + 1).join("\n");
      ta.style.height = "auto";
      ta.style.height = Math.max(380, ta.scrollHeight) + "px";
      if (info) {
        const before = ta.value.slice(0, ta.selectionStart).split("\n");
        info.textContent = "Стр " + before.length + ", Кол " + (before[before.length - 1].length + 1) + " · " + ta.value.length + " симв.";
      }
    };
    ta.addEventListener("input", update);
    ta.addEventListener("click", update);
    ta.addEventListener("keyup", update);
    ta.addEventListener("keydown", (e) => {
      const s = ta.selectionStart, en = ta.selectionEnd, v = ta.value;
      if (e.key === "Tab") {
        e.preventDefault();
        if (e.shiftKey) {
          const ls = v.lastIndexOf("\n", s - 1) + 1;
          const rm = v.slice(ls, ls + 4).match(/^ {1,4}/);
          if (rm) { ta.value = v.slice(0, ls) + v.slice(ls + rm[0].length); ta.selectionStart = ta.selectionEnd = Math.max(ls, s - rm[0].length); }
        } else {
          ta.value = v.slice(0, s) + "    " + v.slice(en);
          ta.selectionStart = ta.selectionEnd = s + 4;
        }
        update();
      } else if (e.key === "Enter" && !e.ctrlKey && !e.metaKey) {
        const ls = v.lastIndexOf("\n", s - 1) + 1;
        const indent = (v.slice(ls, s).match(/^[ \t]*/) || [""])[0];
        const extra = /[:{(\[]\s*$/.test(v.slice(ls, s)) ? "    " : "";
        e.preventDefault();
        ta.value = v.slice(0, s) + "\n" + indent + extra + v.slice(en);
        ta.selectionStart = ta.selectionEnd = s + 1 + indent.length + extra.length;
        update();
      } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        const f = ta.form; if (f) f.requestSubmit();
      }
    });
    update();
  });

  /* ---------- способ отправки: код / файл ---------- */
  $$("[data-submit-modes]").forEach((wrap) => {
    const form = wrap.closest("form");
    const btns = $$("[data-mode]", wrap);
    const code = $("textarea[name=code]", form);
    const file = $("input[type=file]", form);
    btns.forEach((b) => b.addEventListener("click", () => {
      btns.forEach((x) => x.classList.toggle("is-active", x === b));
      $$("[data-mode-pane]", form).forEach((p) => (p.hidden = p.dataset.modePane !== b.dataset.mode));
      if (b.dataset.mode === "file" && code) code.dataset.saved = code.value, code.value = "";
      if (b.dataset.mode === "code") { if (file) file.value = ""; if (code && code.dataset.saved) code.value = code.dataset.saved; $$("[data-file-name]", form).forEach((n) => (n.textContent = "")); }
    }));
  });

  /* ---------- зона перетаскивания файла ---------- */
  $$(".dropzone").forEach((dz) => {
    const input = $("input[type=file]", dz);
    const name = $("[data-file-name]", dz);
    ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("is-over"); }));
    ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove("is-over")));
    dz.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event("change")); } });
    input.addEventListener("change", () => {
      const f = input.files[0];
      if (name) name.textContent = f ? f.name + " · " + Math.ceil(f.size / 1024) + " КБ" : "";
    });
  });

  /* ---------- быстрые баллы при проверке ---------- */
  $$("[data-score]").forEach((b) => b.addEventListener("click", () => {
    const input = document.getElementById(b.dataset.target);
    if (input) { input.value = b.dataset.score; input.focus(); }
  }));

  /* ---------- автоотправка фильтров ---------- */
  $$("form[data-autosubmit] select").forEach((s) => s.addEventListener("change", () => s.form.submit()));
})();
