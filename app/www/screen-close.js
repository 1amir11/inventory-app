/* screen-close.js - the main daily entry screen. */
var KIOSK = KIOSK || {};

KIOSK.closeScreen = (function () {
  var api = KIOSK.api, fmt = KIOSK.fmt, ui = KIOSK.ui;
  var day = null;               /* last /api/day payload */
  var draft = null;             /* unsaved typed values */
  var saveTimer = null;
  var rowOrder = [];

  function blankDraft() {
    return { closing: {}, sales: {}, coffee: null, receipt: {} };
  }

  function uid() { return KIOSK.app.userId(); }
  function dept() { return KIOSK.app.dept(); }

  function visibleCounts() {
    if (!day) return [];
    return day.counts.filter(function (c) {
      return dept() === "all" || c.department === dept();
    });
  }

  /* ---------- render ---------- */

  function render(root) {
    rowOrder = [];
    if (!draft) draft = blankDraft();
    if (!day) { ui.loading(root); return; }
    var closed = day.status === "closed";
    var h = '<div class="screen-close"><div class="close-main">';
    if (closed) {
      h += '<div class="banner closed">' + fmt.esc(STR.lock) + " " +
        fmt.esc(STR.closed_banner) + "</div>";
    }
    h += '<div class="table-wrap"><table class="grid t-close"><colgroup>' +
      "<col><col class='c-open'><col class='c-rec'><col class='c-close'>" +
      "<col class='c-cons'></colgroup><thead><tr>" +
      '<th class="c-name">' + fmt.esc(STR.col_material) + "</th>" +
      '<th class="c-num">' + fmt.esc(STR.col_opening) + "</th>" +
      '<th class="c-num">' + fmt.esc(STR.col_received) + "</th>" +
      '<th>' + fmt.esc(STR.col_closing) + "</th>" +
      '<th class="c-num">' + fmt.esc(STR.col_consumed) + "</th>" +
      "</tr></thead><tbody>";
    var list = visibleCounts();
    if (!list.length) {
      h += '<tr><td colspan="5" class="muted">' +
        fmt.esc(STR.empty_materials) + "</td></tr>";
    }
    list.forEach(function (c, i) {
      rowOrder.push(c.material_id);
      h += rowHtml(c, i, closed);
    });
    h += "</tbody></table></div></div>";
    h += '<div class="close-side">' + sideHtml(closed) + "</div></div>";
    root.innerHTML = h;
    wire(root, closed);
    refreshDerived(root);
  }

  function unitOpts(c, selId) {
    return c.units.map(function (u) {
      return '<option value="' + u.id + '"' +
        (u.id === selId ? " selected" : "") + ">" +
        fmt.esc(u.unit_name) + "</option>";
    }).join("");
  }

  function rowHtml(c, i, closed) {
    var cnt = c.count || {};
    var openBase = (cnt.opening_base !== undefined && cnt.opening_base !== null)
      ? cnt.opening_base : c.opening_default_base;
    var d = draft.closing[c.material_id] || {};
    var closeQty = d.qty !== undefined ? d.qty :
      (cnt.closing_qty_entered !== undefined && cnt.closing_qty_entered !== null
        ? String(cnt.closing_qty_entered) : "");
    var closeUnit = d.unit !== undefined ? d.unit :
      (cnt.closing_unit_id || baseUnitId(c) || (c.units[0] && c.units[0].id));
    var cls = "", msg = "";
    var st = rowState(c, openBase, closeQty, closeUnit);
    if (st.level === "warn") { cls = " warnrow"; msg = st.text; }
    if (st.level === "err") { cls = " errrow"; msg = st.text; }
    var h = '<tr class="' + (i % 2 ? "zebra" : "") + cls +
      '" data-row="' + c.material_id + '">' +
      '<td class="c-name" title="' + fmt.esc(c.name) + '"><b>' +
      fmt.esc(c.name) + "</b>" +
      '<span class="dept-tag">' + fmt.esc(deptName(c.department)) + "</span>" +
      '<div class="savedot" id="sv-' + c.material_id + '"></div></td>' +
      '<td class="c-num num">' + fmt.int(openBase) +
      '<div class="base-equiv">' + fmt.esc(STR.opening_default_note) + "</div></td>" +
      '<td class="c-num num cell-rec" id="rec-' + c.material_id + '">' +
      fmt.int(c.received_base) +
      (closed ? "" : '<button type="button" data-recbtn="' + c.material_id + '">' +
        fmt.esc(STR.add_receipt) + "</button>") + "</td>" +
      '<td class="cell-close"><input type="text" inputmode="decimal" class="qty num" data-close="' +
      c.material_id + '" value="' + fmt.esc(closeQty) + '"' +
      (closed ? " disabled" : "") + ">" +
      '<select class="unit" data-closeunit="' + c.material_id + '"' +
      (closed ? " disabled" : "") + ">" + unitOpts(c, closeUnit) + "</select>" +
      '<div class="base-equiv" id="eq-' + c.material_id + '"></div>' +
      '<div class="inline-err" id="er-' + c.material_id + '"></div></td>' +
      '<td class="c-num num"><b id="con-' + c.material_id + '"></b></td></tr>';
    if (msg) {
      h += '<tr class="' + (i % 2 ? "zebra" : "") + cls + '"><td colspan="5">' +
        '<div class="rowmsg ' + st.level + '">' + fmt.esc(msg) + "</div></td></tr>";
    }
    h += '<tr class="hidden" id="recrow-' + c.material_id + '"><td colspan="5">' +
      '<div class="recform">' +
      "<span>" + fmt.esc(STR.receipt_qty) + "</span>" +
      '<input type="text" inputmode="decimal" class="num" data-recqty="' +
      c.material_id + '"' + (closed ? " disabled" : "") + ">" +
      '<select data-recunit="' + c.material_id + '">' +
      unitOpts(c, null) + "</select>" +
      '<button type="button" class="btn-primary" data-recadd="' +
      c.material_id + '">' + fmt.esc(STR.add) + "</button>" +
      '<div class="inline-err" id="recerr-' + c.material_id + '"></div>' +
      "</div></td></tr>";
    return h;
  }

  function deptName(d) {
    return d === "kitchen" ? STR.dept_kitchen : STR.dept_cafeteria;
  }

  function baseUnitId(c) {
    for (var i = 0; i < c.units.length; i++) {
      if (c.units[i].is_base_unit) return c.units[i].id;
    }
    return null;
  }

  function factorOf(c, unitId) {
    for (var i = 0; i < c.units.length; i++) {
      if (c.units[i].id === unitId) return c.units[i].factor_to_base;
    }
    return 1;
  }

  function byId(mid) {
    for (var i = 0; i < day.counts.length; i++) {
      if (day.counts[i].material_id === mid) return day.counts[i];
    }
    return null;
  }

  /* warn/err level for a row from current input values. */
  function rowState(c, openBase, closeQtyText, closeUnit) {
    var p = fmt.parseQty(closeQtyText);
    if (closeQtyText !== "" && !p.ok) {
      return { level: "err", text: STR.err_bad_number };
    }
    if (closeQtyText === "") return { level: "", text: "" };
    var closeBase = Math.round(p.value * factorOf(c, closeUnit));
    if (closeBase > openBase + c.received_base) {
      return { level: "warn", text: STR.warn_over_close };
    }
    if (c.avg14 > 0 && closeBase > 10 * c.avg14) {
      return { level: "warn", text: STR.warn_spike };
    }
    return { level: "", text: "" };
  }

  /* ---------- side panel ---------- */

  function cupMaterial() {
    for (var i = 0; i < day.counts.length; i++) {
      if (day.counts[i].is_cup) return day.counts[i];
    }
    return null;
  }

  function manualProducts() {
    return day.products.filter(function (p) {
      return p.sold_source === "manual";
    });
  }

  function coffeeProduct() {
    for (var i = 0; i < day.products.length; i++) {
      if (day.products[i].sold_source === "derived_remainder_of_cup") {
        return day.products[i];
      }
    }
    return null;
  }

  function saleOf(pid) {
    for (var i = 0; i < day.sales.length; i++) {
      if (day.sales[i].product_id === pid) return day.sales[i].qty_sold;
    }
    return 0;
  }

  function sideHtml(closed) {
    var h = "";
    var cup = cupMaterial();
    var cof = coffeeProduct();
    if (cup && cof) {
      var counted = (day.report && day.report.coffee_check)
        ? day.report.coffee_check.counted : "";
      if (draft.coffee !== null && draft.coffee !== undefined) {
        counted = draft.coffee;
      }
      h += '<div class="card"><h3>' + fmt.esc(STR.card_cups) + "</h3>" +
        "<div>" + fmt.esc(STR.cups_consumed) + ': <b class="num" id="cup-consumed"></b></div>' +
        "<div>" + fmt.esc(STR.coffee_derived) + ': <b class="num" id="coffee-derived"></b></div>' +
        '<div style="margin-top:8px"><div class="small muted">' +
        fmt.esc(STR.coffee_counted) + " (" + fmt.esc(STR.coffee_counted_hint) + ")</div>" +
        '<div class="coffeerow"><input type="text" inputmode="decimal" class="num" id="coffee-in" value="' +
        fmt.esc(counted) + '"' + (closed ? " disabled" : "") + ">" +
        (closed ? "" : '<button type="button" id="coffee-save">' +
          fmt.esc(STR.save) + "</button>") + "</div>" +
        '<div class="inline-err" id="coffee-err"></div></div></div>';
    }
    var dishes = manualProducts();
    if (dishes.length) {
      h += '<div class="card"><h3>' + fmt.esc(STR.card_dishes) + "</h3>";
      dishes.forEach(function (p) {
        var v = draft.sales[p.id] !== undefined ? draft.sales[p.id] : saleOf(p.id);
        h += '<div class="dishrow">' +
          '<span title="' + fmt.esc(p.name) + '">' + fmt.esc(p.name) + "</span>" +
          '<input type="text" inputmode="decimal" class="num" data-sale="' +
          p.id + '" value="' + fmt.esc(v) + '"' +
          (closed ? " disabled" : "") + ">" +
          '<div class="savedot" id="svs-' + p.id + '"></div></div>' +
          '<div class="inline-err" id="ers-' + p.id + '"></div>';
      });
      h += "</div>";
    }
    h += '<div class="card"><h3>' + fmt.esc(STR.card_summary) + "</h3>" +
      '<div id="live-summary">' + summaryHtml() + "</div></div>";
    if (closed) {
      h += '<button type="button" id="adjust-btn" style="width:100%">' +
        fmt.esc(STR.add_adjust) + "</button>";
    }
    return h;
  }

  function summaryHtml() {
    var rep = day.report;
    if (!rep) {
      return '<div class="muted">' + fmt.esc(STR.empty) + "</div>";
    }
    var rec = rep.reconciliation;
    var recHtml = rec.difference === 0
      ? '<span class="chip closed">' + fmt.esc(STR.check) + " " +
        fmt.esc(STR.reconcile_ok) + "</span>"
      : '<span class="chip open">' + fmt.esc(STR.reconcile_diff) + ': <span class="num">' +
        fmt.int(rec.difference) + "</span></span>";
    return "<div>" + fmt.esc(STR.revenue) + ": " +
      fmt.moneyHtml(rep.total_revenue) + "</div>" +
      "<div>" + fmt.esc(STR.cost) + ": " + fmt.moneyHtml(rep.total_cost) + "</div>" +
      "<div>" + fmt.esc(STR.profit) + ": " +
      fmt.moneyHtml(rep.total_profit, rep.total_profit < 0 ? "neg" : "pos") + "</div>" +
      "<div>" + fmt.esc(STR.total_cups) + ': <b class="num">' +
      fmt.int(rep.total_cups) + "</b></div><div>" + recHtml + "</div>";
  }

  /* ---------- live derived numbers ---------- */

  function refreshDerived(root) {
    root = root || document.getElementById("content");
    visibleCounts().forEach(function (c) {
      var inp = root.querySelector('input[data-close="' + c.material_id + '"]');
      var sel = root.querySelector('select[data-closeunit="' + c.material_id + '"]');
      if (!inp || !sel) return;
      var cnt = c.count || {};
      var openBase = (cnt.opening_base !== undefined && cnt.opening_base !== null)
        ? cnt.opening_base : c.opening_default_base;
      var p = fmt.parseQty(inp.value);
      var unit = parseInt(sel.value, 10);
      var eq = root.querySelector("#eq-" + c.material_id);
      var con = root.querySelector("#con-" + c.material_id);
      if (p.ok && inp.value !== "") {
        var closeBase = Math.round(p.value * factorOf(c, unit));
        if (eq) eq.textContent = "= " + fmt.equiv(p.value, "", factorOf(c, unit), c.base_unit);
        if (con) con.textContent = fmt.int(openBase + c.received_base - closeBase);
      } else {
        if (eq) eq.textContent = "";
        if (con) con.textContent = "-";
      }
    });
    var cup = cupMaterial();
    var cc = document.getElementById("cup-consumed");
    if (cup && cc) {
      var st = consumedOf(cup);
      cc.textContent = fmt.int(st);
    }
    var cd = document.getElementById("coffee-derived");
    if (cd) cd.textContent = derivedCoffee();
  }

  function consumedOf(c) {
    var cnt = c.count || {};
    var openBase = (cnt.opening_base !== undefined && cnt.opening_base !== null)
      ? cnt.opening_base : c.opening_default_base;
    var d = draft.closing[c.material_id];
    var closeBase = cnt.closing_base;
    if (d && d.qty !== undefined && d.qty !== "") {
      var p = fmt.parseQty(d.qty);
      if (p.ok) closeBase = Math.round(p.value * factorOf(c, d.unit));
    }
    if (closeBase === undefined || closeBase === null) return null;
    return openBase + c.received_base - closeBase;
  }

  function derivedCoffee() {
    if (day.report) {
      for (var i = 0; i < day.report.lines.length; i++) {
        var ln = day.report.lines[i];
        if (ln.method === "derived_remainder_of_cup") return fmt.int(ln.qty_sold);
      }
    }
    return "-";
  }

  /* ---------- wiring ---------- */

  function wire(root, closed) {
    if (closed) {
      var ab = document.getElementById("adjust-btn");
      if (ab) ab.onclick = adjustFlow;
      return;
    }
    var inputs = root.querySelectorAll("input[data-close]");
    for (var i = 0; i < inputs.length; i++) {
      (function (inp) {
        var mid = parseInt(inp.getAttribute("data-close"), 10);
        inp.addEventListener("focus", function () {
          try { inp.select(); } catch (e) { /* noop */ }
        });
        inp.addEventListener("input", function () {
          setDraftClosing(mid);
          refreshDerived(root);
          scheduleSave();
        });
        inp.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter") {
            ev.preventDefault();
            saveNow();
            moveRow(mid, ev.shiftKey ? -1 : 1);
          }
        });
        inp.addEventListener("blur", function () { scheduleSave(); });
      })(inputs[i]);
    }
    var units = root.querySelectorAll("select[data-closeunit]");
    for (var u = 0; u < units.length; u++) {
      (function (sel) {
        sel.addEventListener("change", function () {
          setDraftClosing(parseInt(sel.getAttribute("data-closeunit"), 10));
          refreshDerived(root);
          scheduleSave();
        });
      })(units[u]);
    }
    var recbtns = root.querySelectorAll("[data-recbtn]");
    for (var r = 0; r < recbtns.length; r++) {
      (function (b) {
        b.onclick = function () {
          var mid = b.getAttribute("data-recbtn");
          var row = document.getElementById("recrow-" + mid);
          row.classList.toggle("hidden");
          var q = row.querySelector("input");
          if (q && !row.classList.contains("hidden")) {
            try { q.focus(); } catch (e) { /* noop */ }
          }
        };
      })(recbtns[r]);
    }
    var recadds = root.querySelectorAll("[data-recadd]");
    for (var a = 0; a < recadds.length; a++) {
      (function (b) {
        b.onclick = function () { addReceipt(parseInt(b.getAttribute("data-recadd"), 10)); };
      })(recadds[a]);
    }
    var sales = root.querySelectorAll("input[data-sale]");
    for (var s = 0; s < sales.length; s++) {
      (function (inp) {
        var pid = parseInt(inp.getAttribute("data-sale"), 10);
        inp.addEventListener("focus", function () {
          try { inp.select(); } catch (e) { /* noop */ }
        });
        inp.addEventListener("input", function () {
          draft.sales[pid] = inp.value;
          scheduleSave();
        });
        inp.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter") { ev.preventDefault(); saveNow(); }
        });
        inp.addEventListener("blur", function () { scheduleSave(); });
      })(sales[s]);
    }
    var cs = document.getElementById("coffee-save");
    if (cs) {
      cs.onclick = function () {
        var inp = document.getElementById("coffee-in");
        var p = fmt.parseQty(inp.value);
        if (!p.ok || Math.round(p.value) !== p.value) {
          document.getElementById("coffee-err").textContent = STR.err_bad_number;
          return;
        }
        document.getElementById("coffee-err").textContent = "";
        api.post("/api/day/coffee-check", {
          date: day.date, counted_cups: Math.round(p.value), user_id: uid()
        }).then(function (body) {
          if (body._status !== 200) { api.failToast(body); return; }
          draft.coffee = null;
          reload();
        });
      };
    }
    document.addEventListener("keydown", ctrlSave);
  }

  function ctrlSave(ev) {
    if ((ev.ctrlKey || ev.metaKey) && (ev.key === "s" || ev.key === "S")) {
      ev.preventDefault();
      saveNow();
    }
  }

  function setDraftClosing(mid) {
    var root = document.getElementById("content");
    var inp = root.querySelector('input[data-close="' + mid + '"]');
    var sel = root.querySelector('select[data-closeunit="' + mid + '"]');
    if (!inp || !sel) return;
    draft.closing[mid] = { qty: inp.value, unit: parseInt(sel.value, 10) };
    var mark = document.getElementById("sv-" + mid);
    if (mark) mark.textContent = "";
  }

  function moveRow(mid, dir) {
    var i = rowOrder.indexOf(mid) + dir;
    if (i < 0 || i >= rowOrder.length) return;
    var next = document.querySelector(
      'input[data-close="' + rowOrder[i] + '"]');
    if (next) { try { next.focus(); next.select(); } catch (e) { /* noop */ } }
  }

  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 900);
  }

  /* Save every dirty draft field, one endpoint call each. Typed values stay
     in the draft on failure and the row shows the error. */
  function saveNow() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    if (!day || day.status === "closed") return;
    var jobs = [];
    Object.keys(draft.closing).forEach(function (mid) {
      jobs.push(saveClosing(parseInt(mid, 10)));
    });
    Object.keys(draft.sales).forEach(function (pid) {
      jobs.push(saveSale(parseInt(pid, 10)));
    });
    if (!jobs.length) return;
    Promise.all(jobs).then(function (results) {
      var failed = results.filter(function (r) { return !r; }).length;
      if (!failed) reload();
    });
  }

  function saveClosing(mid) {
    var d = draft.closing[mid];
    if (!d) return Promise.resolve(true);
    var errEl = document.getElementById("er-" + mid);
    var p = fmt.parseQty(d.qty);
    if (d.qty === "") { delete draft.closing[mid]; return Promise.resolve(true); }
    if (!p.ok) {
      if (errEl) errEl.textContent = STR.err_bad_number;
      return Promise.resolve(false);
    }
    if (errEl) errEl.textContent = "";
    return api.post("/api/day/count", {
      date: day.date, material_id: mid, field: "closing",
      qty_entered: p.value, unit_id: d.unit, user_id: uid()
    }).then(function (body) {
      if (body._status === 200) {
        delete draft.closing[mid];
        var mark = document.getElementById("sv-" + mid);
        if (mark) mark.textContent = STR.saved;
        if (body.warnings && body.warnings.length) ui.toast(body.warnings[0]);
        return true;
      }
      if (body.error === "closing_reason_required") {
        askReason(mid, d, p.value);
        return true; /* handled via dialog; keep draft */
      }
      api.failToast(body);
      return false;
    });
  }

  function askReason(mid, d, qty) {
    ui.reasonDialog(STR.reason_title, STR.warn_over_close, STR.confirm,
      function (reason) {
        api.post("/api/day/count", {
          date: day.date, material_id: mid, field: "closing",
          qty_entered: qty, unit_id: d.unit, user_id: uid(), reason: reason
        }).then(function (body) {
          if (body._status !== 200) { api.failToast(body); return; }
          delete draft.closing[mid];
          reload();
        });
      });
  }

  function saveSale(pid) {
    if (draft.sales[pid] === undefined) return Promise.resolve(true);
    var errEl = document.getElementById("ers-" + pid);
    var p = fmt.parseQty(draft.sales[pid]);
    if (!p.ok || Math.round(p.value) !== p.value) {
      if (errEl) errEl.textContent = STR.err_bad_number;
      return Promise.resolve(false);
    }
    if (errEl) errEl.textContent = "";
    return api.post("/api/day/sale", {
      date: day.date, product_id: pid, qty_sold: Math.round(p.value),
      user_id: uid()
    }).then(function (body) {
      if (body._status !== 200) { api.failToast(body); return false; }
      delete draft.sales[pid];
      var mark = document.getElementById("svs-" + pid);
      if (mark) mark.textContent = STR.saved;
      return true;
    });
  }

  function addReceipt(mid) {
    var root = document.getElementById("content");
    var q = root.querySelector('input[data-recqty="' + mid + '"]');
    var s = root.querySelector('select[data-recunit="' + mid + '"]');
    var errEl = document.getElementById("recerr-" + mid);
    var p = fmt.parseQty(q.value);
    if (!p.ok || p.value <= 0) {
      if (errEl) errEl.textContent = STR.err_bad_number;
      return;
    }
    if (errEl) errEl.textContent = "";
    api.post("/api/day/receipt", {
      date: day.date, material_id: mid, qty_entered: p.value,
      unit_id: parseInt(s.value, 10), user_id: uid()
    }).then(function (body) {
      if (body._status !== 200) { api.failToast(body); return; }
      reload();
    });
  }

  function adjustFlow() {
    var mats = visibleCounts().map(function (c) {
      return '<option value="' + c.material_id + '">' +
        fmt.esc(c.name) + "</option>";
    }).join("");
    var body = '<div class="formrow"><span>' + fmt.esc(STR.col_material) +
      '</span><select id="adj-mid">' + mats + "</select></div>" +
      '<div class="formrow"><span>' + fmt.esc(STR.adjust_delta) + "</span>" +
      '<input type="text" inputmode="decimal" class="qty num" id="adj-delta"></div>' +
      '<div class="small muted">' + fmt.esc(STR.adjust_hint) + "</div>" +
      '<div class="formrow"><span>' + fmt.esc(STR.reason_title) + "</span>" +
      '<textarea id="adj-reason" rows="2" style="flex:1"></textarea></div>' +
      '<div class="inline-err" id="adj-err"></div>';
    ui.dialog(STR.adjust_title, body, {
      okText: STR.confirm,
      onOk: function () {
        var mid = parseInt(document.getElementById("adj-mid").value, 10);
        var dp = fmt.parseQty(document.getElementById("adj-delta").value);
        var reason = document.getElementById("adj-reason").value.trim();
        if (!dp.ok || dp.value === 0 || !reason) {
          document.getElementById("adj-err").textContent =
            !reason ? STR.reason_required : STR.err_bad_number;
          return;
        }
        /* Signed delta: allow a leading minus typed by staff. */
        var raw = document.getElementById("adj-delta").value.trim();
        var delta = raw.charAt(0) === "-" ? -Math.round(dp.value)
          : Math.round(dp.value);
        api.post("/api/day/adjust", {
          date: day.date, material_id: mid, delta_base: delta,
          reason: reason, user_id: uid()
        }).then(function (resp) {
          if (resp._status !== 200) { api.failToast(resp); return; }
          ui.close();
          reload();
        });
      }
    });
  }

  /* ---------- action bar ---------- */

  function actionbar(root) {
    var bar = document.getElementById("actionbar");
    if (!day || day.status === "closed") {
      bar.classList.add("hidden");
      document.getElementById("content").classList.remove("with-actionbar");
      return;
    }
    document.getElementById("content").classList.add("with-actionbar");
    bar.classList.remove("hidden");
    bar.innerHTML = "";
    var sv = document.createElement("button");
    sv.type = "button";
    sv.className = "btn-secondary";
    sv.textContent = STR.save_draft;
    sv.onclick = saveNow;
    var cl = document.createElement("button");
    cl.type = "button";
    cl.className = "btn-primary";
    cl.textContent = STR.close_day;
    cl.onclick = closeFlow;
    bar.appendChild(sv);
    bar.appendChild(cl);
  }

  function closeFlow() {
    saveNow();
    api.get("/api/day?date=" + day.date).then(function (fresh) {
      var rep = fresh.report;
      var h = "";
      if (rep) {
        h += "<div>" + fmt.esc(STR.revenue) + ": " +
          fmt.moneyHtml(rep.total_revenue) + "</div>";
        h += "<div>" + fmt.esc(STR.cost) + ": " +
          fmt.moneyHtml(rep.total_cost) + "</div>";
        h += "<div>" + fmt.esc(STR.profit) + ": " +
          fmt.moneyHtml(rep.total_profit,
            rep.total_profit < 0 ? "neg" : "pos") + "</div>";
        h += "<div>" + fmt.esc(STR.total_cups) + ': <b class="num">' +
          fmt.int(rep.total_cups) + "</b></div>";
        if (rep.warnings && rep.warnings.length) {
          h += "<div style='margin-top:8px'><b>" + fmt.esc(STR.warn_icon) +
            "</b><ul>";
          rep.warnings.forEach(function (w) {
            h += "<li>" + fmt.esc(w) + "</li>";
          });
          h += "</ul></div>";
        }
        var missing = missingClosings(fresh);
        if (missing.length) {
          h += '<div class="banner warn">' + fmt.esc(STR.close_missing) +
            ": " + fmt.esc(missing.join(", ")) + "</div>";
        }
      }
      ui.dialog(STR.close_review_title, h, {
        okText: STR.confirm,
        onOk: function () {
          api.post("/api/day/close", { date: day.date, user_id: uid() })
            .then(function (body) {
              if (body._status !== 200) { api.failToast(body); return; }
              ui.close();
              ui.toast(STR.saved);
              reload();
            });
        }
      });
    });
  }

  function missingClosings(d) {
    return d.counts.filter(function (c) {
      return !c.count || c.count.closing_base === null ||
        c.count.closing_base === undefined;
    }).map(function (c) { return c.name; });
  }

  /* ---------- entry ---------- */

  function reload() {
    var root = document.getElementById("content");
    /* Keep typed values across the rebuild. */
    captureDraft(root);
    api.get("/api/day?date=" + KIOSK.app.date()).then(function (d) {
      day = d;
      render(root);
      actionbar(root);
      KIOSK.app.refreshChrome(d);
    });
  }

  function captureDraft(root) {
    if (!root) return;
    var inputs = root.querySelectorAll("input[data-close]");
    for (var i = 0; i < inputs.length; i++) {
      var mid = parseInt(inputs[i].getAttribute("data-close"), 10);
      var sel = root.querySelector(
        'select[data-closeunit="' + mid + '"]');
      var unit = sel ? parseInt(sel.value, 10) : null;
      var server = serverClosing(mid);
      /* Keep only values that differ from what the server has: a plain
         rebuild after a successful save must not re-mark rows dirty. */
      if (server && inputs[i].value === server.qty && unit === server.unit) {
        delete draft.closing[mid];
      } else if (inputs[i].value !== "" || draft.closing[mid]) {
        draft.closing[mid] = { qty: inputs[i].value, unit: unit };
      }
    }
    var sales = root.querySelectorAll("input[data-sale]");
    for (var s = 0; s < sales.length; s++) {
      draft.sales[parseInt(sales[s].getAttribute("data-sale"), 10)] =
        sales[s].value;
    }
    var ci = document.getElementById("coffee-in");
    if (ci && ci.value !== "") draft.coffee = ci.value;
  }

  function serverClosing(mid) {
    if (!day) return null;
    for (var i = 0; i < day.counts.length; i++) {
      var c = day.counts[i];
      if (c.material_id !== mid || !c.count) continue;
      if (c.count.closing_qty_entered === null ||
          c.count.closing_qty_entered === undefined) return null;
      return { qty: String(c.count.closing_qty_entered),
               unit: c.count.closing_unit_id };
    }
    return null;
  }

  function show(root) {
    draft = blankDraft();
    day = null;
    render(root);
    actionbar(root);
    reload();
  }

  function cleanup() {
    document.removeEventListener("keydown", ctrlSave);
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
    draft = blankDraft();
    day = null;
  }

  return { show: show, cleanup: cleanup, saveNow: saveNow };
})();
