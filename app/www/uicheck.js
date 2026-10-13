/* uicheck.js - automated layout check. Runs ONLY with ?uicheck=1: measures
   clipping, control heights, header height and page scroll, then writes the
   JSON result into #uicheck-result for the headless driver (tests/ui_check.js)
   to read from the dumped DOM. Plain script, no modules. */
var KIOSK = KIOSK || {};

KIOSK.uicheck = (function () {
  function visible(el) {
    if (!el || !el.getClientRects) return false;
    if (!el.getClientRects().length) return false;
    var cs = window.getComputedStyle ? getComputedStyle(el) : null;
    if (cs && (cs.display === "none" || cs.visibility === "hidden")) {
      return false;
    }
    return true;
  }

  function sel(el) {
    var s = el.tagName ? el.tagName.toLowerCase() : "?";
    if (el.id) s += "#" + el.id;
    else if (el.className && typeof el.className === "string") {
      s += "." + el.className.trim().split(/\s+/).slice(0, 2).join(".");
    }
    if (el.getAttribute) {
      var t = el.getAttribute("data-tab") || el.getAttribute("data-close") ||
        el.getAttribute("data-dept");
      if (t) s += "[" + t + "]";
    }
    var txt = (el.textContent || "").trim().replace(/\s+/g, " ");
    if (txt) s += " '" + txt.slice(0, 28) + "'";
    return s;
  }

  function run(screen) {
    var out = {
      screen: screen, date: KIOSK.app.date(),
      viewport: { w: window.innerWidth, h: window.innerHeight },
      doc: { sw: document.documentElement.scrollWidth,
             sh: document.documentElement.scrollHeight },
      violations: []
    };
    function bad(kind, el, detail) {
      out.violations.push({ kind: kind, el: sel(el), detail: detail });
    }

    var topbar = document.getElementById("topbar");
    if (topbar && topbar.offsetHeight !== 120) {
      bad("header-height", topbar, "height=" + topbar.offsetHeight);
    }
    /* Toolbars clip children instead of wrapping: catch cut-off tabs. */
    var toolbars = document.querySelectorAll("#tabbar, #topbar, #datenav");
    for (var t = 0; t < toolbars.length; t++) {
      if (!visible(toolbars[t])) continue;
      if (toolbars[t].scrollWidth > toolbars[t].clientWidth + 1) {
        bad("toolbar-overflow", toolbars[t],
          "scrollWidth=" + toolbars[t].scrollWidth +
          " clientWidth=" + toolbars[t].clientWidth);
      }
    }
    if (out.doc.sh > 650) bad("page-vscroll", document.body, "sh=" + out.doc.sh);
    if (out.doc.sw > 1024) bad("page-hscroll", document.body, "sw=" + out.doc.sw);

    var els = document.querySelectorAll(
      "button, input, select, textarea, th, td, label, .chip, .tab");
    for (var i = 0; i < els.length; i++) {
      (function (el) {
        if (!visible(el)) return;
        var tag = (el.tagName || "").toLowerCase();
        if (tag === "option") return;
        if (el.scrollWidth > el.clientWidth + 1) {
          bad("clip", el, "scrollWidth=" + el.scrollWidth +
            " clientWidth=" + el.clientWidth);
        }
        var h = el.offsetHeight;
        var isChip = el.classList && el.classList.contains("chip");
        if (isChip) {
          if (h !== 32) bad("height", el, "chip height=" + h);
          return;
        }
        if (tag === "button" || tag === "input" || tag === "select" ||
            (el.classList && el.classList.contains("tab")) ||
            (el.parentNode && el.parentNode.id === "dept-seg")) {
          if (tag === "textarea") return;
          if (h !== 48) bad("height", el, "height=" + h);
        }
      })(els[i]);
    }

    var rows = document.querySelectorAll("table.grid tbody tr");
    for (var r = 0; r < rows.length; r++) {
      if (!visible(rows[r])) continue;
      if (rows[r].offsetHeight < 52) {
        bad("row-height", rows[r], "height=" + rows[r].offsetHeight);
      }
    }

    /* Sibling buttons in one toolbar share one height. */
    var bars = document.querySelectorAll(
      "#actionbar, #datenav, .dlg-actions, .formfoot, .arch-nav");
    for (var b = 0; b < bars.length; b++) {
      if (!visible(bars[b])) continue;
      var hs = {};
      var btns = bars[b].querySelectorAll("button");
      for (var k = 0; k < btns.length; k++) {
        if (!visible(btns[k])) continue;
        hs[btns[k].offsetHeight] = true;
      }
      var keys = Object.keys(hs);
      if (keys.length > 1) {
        bad("siblings", bars[b], "heights=" + keys.join(","));
      }
    }
    return out;
  }

  function write(screen) {
    var res = run(screen);
    var pre = document.getElementById("uicheck-result");
    if (!pre) {
      pre = document.createElement("pre");
      pre.id = "uicheck-result";
      pre.style.display = "none";
      document.body.appendChild(pre);
    }
    /* Hidden text (not attribute) so --dump-dom captures it. */
    pre.textContent = "UICHECK-JSON:" + JSON.stringify(res);
    return res;
  }

  return { run: run, write: write };
})();
