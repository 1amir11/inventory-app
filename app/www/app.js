/* app.js - shell: tabs, user, department filter, date navigator, heartbeat. */
var KIOSK = KIOSK || {};

KIOSK.app = (function () {
  var api = KIOSK.api, fmt = KIOSK.fmt, ui = KIOSK.ui;
  var state = {
    tab: "close", userId: null, users: [], dept: "all",
    date: KIOSK.dates.todayLocal(), catalog: [], dayStatus: "new"
  };
  var screens = null;
  var hbTimer = null;

  function $(id) { return document.getElementById(id); }

  function userId() { return state.userId; }
  function dept() { return state.dept; }
  function date() { return state.date; }
  function setCatalog(products) { state.catalog = products || []; }
  function productDept(pid) {
    for (var i = 0; i < state.catalog.length; i++) {
      if (state.catalog[i].id === pid) return state.catalog[i].department;
    }
    return null;
  }

  function setDate(d) {
    if (!KIOSK.dates.parse(d)) return;
    state.date = d;
    paintChrome();
    if (state.tab === "close") KIOSK.closeScreen.show($("content"));
    else if (state.tab === "report") KIOSK.reportScreen.show($("content"));
  }

  function paintChrome() {
    $("day-label").textContent = KIOSK.dates.label(state.date);
    var chip = $("day-chip");
    chip.innerHTML = ui.chip(state.dayStatus);
  }

  function refreshChrome(day) {
    if (day && day.date === state.date && day.status) {
      state.dayStatus = day.status;
    }
    paintChrome();
    audit();
  }

  function go(tab) {
    if (screens && screens[state.tab] && screens[state.tab].cleanup) {
      try { screens[state.tab].cleanup(); } catch (e) { /* noop */ }
    }
    state.tab = tab;
    var tabs = document.querySelectorAll("#tabbar .tab");
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].classList.toggle("active",
        tabs[i].getAttribute("data-tab") === tab);
    }
    ui.close();
    closeCal();
    if (location.hash !== "#/" + tab) location.hash = "#/" + tab;
    showTab();
  }

  function showTab() {
    var root = $("content");
    if (!state.users.length || !state.userId) {
      setupView(root);
      return;
    }
    screens[state.tab].show(root);
    /* ?show=calendar auto-opens the date picker (visual test hook). */
    if (/(?:^|[?&])show=calendar(?:&|$)/.test(location.search || "")) {
      setTimeout(toggleCal, 300);
    }
    /* ?uicheck=1 runs the layout self-check for tests/ui_check.js. */
    if (/(?:^|[?&])uicheck=1(?:&|$)/.test(location.search || "")) {
      setTimeout(function () { KIOSK.uicheck.write(state.tab); }, 2500);
    }
  }

  /* First-run setup: create the named users, then continue. */
  function setupView(root) {
    document.getElementById("actionbar").classList.add("hidden");
    var h = '<div class="screen"><div class="setup-box"><h2 class="sec">' +
      fmt.esc(STR.setup_title) + "</h2>" +
      '<div class="muted" style="margin-bottom:8px">' +
      fmt.esc(STR.setup_hint) + "</div>" +
      '<div class="formrow"><input type="text" id="su-name" placeholder="' +
      fmt.esc(STR.setup_user_ph) + '" style="flex:1" maxlength="100">' +
      '<button type="button" id="su-add" class="btn-primary">' +
      fmt.esc(STR.setup_add_user) + "</button></div>" +
      '<div class="inline-err" id="su-err"></div>' +
      '<div id="su-list" style="margin-bottom:8px"></div>' +
      '<div class="small muted">' + fmt.esc(STR.setup_next) + "</div></div></div>";
    root.innerHTML = h;
    paintUsers();
    $("su-add").onclick = function () {
      var name = $("su-name").value.trim();
      if (!name) {
        $("su-err").textContent = STR.err_bad_number;
        return;
      }
      var payload = { name: name };
      if (state.userId) payload.user_id = state.userId;
      api.post("/api/users", payload).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        $("su-name").value = "";
        loadSession(true);
      });
    };
  }

  function paintUsers() {
    var box = $("su-list");
    if (!box) return;
    box.textContent = state.users.map(function (u) { return u.name; }).join(", ");
  }

  function loadSession(keepTab) {
    return api.get("/api/session").then(function (body) {
      state.users = body.users || [];
      var sel = $("user-select");
      sel.innerHTML = "";
      var ph = document.createElement("option");
      ph.value = "";
      ph.textContent = STR.user_pick;
      sel.appendChild(ph);
      state.users.forEach(function (u) {
        var o = document.createElement("option");
        o.value = u.id;
        o.textContent = u.name;
        sel.appendChild(o);
      });
      if (!state.userId && state.users.length) {
        /* Prefer the last used user so the dropdown never idles on the
           placeholder; fall back to the first user. */
        var last = null;
        try { last = window.localStorage.getItem("ki_user"); } catch (e) { /* noop */ }
        var found = false;
        if (last) {
          for (var i = 0; i < state.users.length; i++) {
            if (String(state.users[i].id) === String(last)) {
              state.userId = state.users[i].id;
              found = true;
            }
          }
        }
        if (!found) state.userId = state.users[0].id;
      }
      sel.value = state.userId ? String(state.userId) : "";
      paintUsers();
      if (!keepTab) showTab();
      else if (!state.users.length) showTab();
      else if (state.users.length && document.getElementById("su-name")) {
        showTab();
      }
      return api.get("/api/settings");
    }).then(function (s) {
      var badge = $("demo-badge");
      if (s && s.settings && s.settings.demo === "1") {
        badge.textContent = STR.demo_badge;
        badge.classList.remove("hidden");
      } else { badge.classList.add("hidden"); }
    });
  }

  /* ---------- date navigator + calendar ---------- */

  function closeCal() { $("cal-root").innerHTML = ""; }

  function toggleCal() {
    var root = $("cal-root");
    if (root.innerHTML) { closeCal(); return; }
    var label = $("day-label");
    var r = label.getBoundingClientRect();
    var app = $("app").getBoundingClientRect();
    var wrap = document.createElement("div");
    wrap.style.position = "absolute";
    wrap.style.top = (r.bottom - app.top + 4) + "px";
    wrap.style.right = Math.max(8, app.right - r.right) + "px";
    root.appendChild(wrap);
    KIOSK.dates.calendar(wrap, state.date, function (iso) {
      closeCal();
      setDate(iso);
    });
  }

  /* ---------- heartbeat + quit ---------- */

  function heartbeat() {
    fetch("/api/heartbeat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    }).catch(function () { /* next beat retries */ });
  }

  function quit() {
    ui.dialog(STR.quit_confirm_title,
      "<div>" + fmt.esc(STR.quit_confirm_text) + "</div>", {
        okText: STR.quit_program,
        okClass: "btn-danger",
        onOk: function () {
          api.post("/api/shutdown", { user_id: state.userId }).then(
            function () {
              ui.toast(STR.quit_confirm_text);
              try { window.close(); } catch (e) { /* launcher closes */ }
            });
        }
      });
  }

  /* ---------- audit badge (?audit=1): proves no page scroll ---------- */

  function audit() {
    if (location.search.indexOf("audit=1") < 0) return;
    var badge = $("audit-badge");
    badge.classList.remove("hidden");
    var de = document.documentElement;
    var over = de.scrollHeight > 650 || de.scrollWidth > 1024;
    badge.textContent = "scroll " + de.scrollWidth + "x" + de.scrollHeight +
      (over ? " OVERFLOW" : " OK") + " | " + state.tab + " " + state.date;
    badge.style.background = over ? "#C62828" : "#1E8E4E";
  }

  /* ---------- init ---------- */

  function paintStatic() {
    document.title = STR.app_title;
    $("app-title").textContent = STR.app_title;
    $("user-label").textContent = STR.user;
    $("quit-btn").textContent = STR.quit_program;
    var tabs = {
      close: STR.tab_close, report: STR.tab_report, archive: STR.tab_archive,
      products: STR.tab_products, backup: STR.tab_backup
    };
    var btns = document.querySelectorAll("#tabbar .tab");
    for (var i = 0; i < btns.length; i++) {
      btns[i].textContent = tabs[btns[i].getAttribute("data-tab")];
    }
    var seg = {
      kitchen: STR.dept_kitchen, cafeteria: STR.dept_cafeteria, all: STR.dept_all
    };
    var sg = document.querySelectorAll("#dept-seg button");
    for (var k = 0; k < sg.length; k++) {
      sg[k].textContent = seg[sg[k].getAttribute("data-dept")];
    }
    $("day-prev").title = STR.day_prev;
    $("day-next").title = STR.day_next;
  }

  function init() {
    screens = {
      close: KIOSK.closeScreen, report: KIOSK.reportScreen,
      archive: KIOSK.archiveScreen, products: KIOSK.productsScreen,
      backup: KIOSK.backupScreen
    };
    /* ?date=YYYY-MM-DD presets the business date (demo/review hook). */
    var dq = /[?&]date=(\d{4}-\d{2}-\d{2})/.exec(location.search || "");
    if (dq && KIOSK.dates.parse(dq[1])) state.date = dq[1];
    /* ?failtest=1 fires one bogus write to prove the error toast. */
    var failtest = /(?:^|[?&])failtest=1(?:&|$)/.test(location.search || "");
    paintStatic();
    var tabs = document.querySelectorAll("#tabbar .tab");
    for (var i = 0; i < tabs.length; i++) {
      (function (b) {
        b.onclick = function () { go(b.getAttribute("data-tab")); };
      })(tabs[i]);
    }
    var m = /^#\/(\w+)$/.exec(location.hash || "");
    if (m && screens[m[1]]) state.tab = m[1];
    var tabs0 = document.querySelectorAll("#tabbar .tab");
    for (var t = 0; t < tabs0.length; t++) {
      tabs0[t].classList.toggle("active",
        tabs0[t].getAttribute("data-tab") === state.tab);
    }
    window.addEventListener("hashchange", function () {
      var mm = /^#\/(\w+)$/.exec(location.hash || "");
      if (mm && screens[mm[1]] && mm[1] !== state.tab) go(mm[1]);
    });
    var sg = document.querySelectorAll("#dept-seg button");
    for (var k = 0; k < sg.length; k++) {
      (function (b) {
        b.onclick = function () {
          state.dept = b.getAttribute("data-dept");
          for (var j = 0; j < sg.length; j++) {
            sg[j].classList.toggle("active", sg[j] === b);
          }
          showTab();
        };
      })(sg[k]);
    }
    for (var a = 0; a < sg.length; a++) {
      sg[a].classList.toggle("active",
        sg[a].getAttribute("data-dept") === "all");
    }
    $("user-select").onchange = function () {
      state.userId = parseInt($("user-select").value, 10) || null;
      try {
        if (state.userId) {
          window.localStorage.setItem("ki_user", String(state.userId));
        }
      } catch (e) { /* private mode etc: selection just doesn't persist */ }
    };
    $("day-prev").onclick = function () {
      setDate(KIOSK.dates.addDays(state.date, -1));
    };
    $("day-next").onclick = function () {
      setDate(KIOSK.dates.addDays(state.date, 1));
    };
    $("day-label").onclick = toggleCal;
    $("quit-btn").onclick = quit;
    paintChrome();
    loadSession();
    if (failtest) {
      api.post("/api/does-not-exist", {}).then(function (body) {
        api.failToast(body);
      });
    }
    if (hbTimer) clearInterval(hbTimer);
    hbTimer = setInterval(heartbeat, 10000);
  }

  return {
    init: init, go: go, userId: userId, dept: dept, date: date,
    setDate: setDate, setCatalog: setCatalog, productDept: productDept,
    refreshChrome: refreshChrome
  };
})();

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", KIOSK.app.init);
} else {
  KIOSK.app.init();
}
