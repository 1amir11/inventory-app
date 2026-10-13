/* app.js - kiosk frontend. Vanilla JS, no frameworks.
   No alert/confirm/prompt (they hang the kiosk): in-page toast + modal. */
var state = { userId: null, date: "", materials: [], products: [] };

function $(id) { return document.getElementById(id); }

function toast(msg) {
  var t = $("toast");
  t.textContent = msg;
  t.className = "";
  setTimeout(function () { t.className = "hidden"; }, 4000);
}

function confirmReason(text) {
  return new Promise(function (resolve) {
    $("modal-text").textContent = text;
    $("modal-reason").value = "";
    $("modal-back").className = "";
    $("modal-ok").onclick = function () {
      var r = $("modal-reason").value.trim();
      if (!r) { toast("يلزم سبب مكتوب."); return; }
      $("modal-back").className = "hidden";
      resolve(r);
    };
    $("modal-cancel").onclick = function () {
      $("modal-back").className = "hidden";
      resolve(null);
    };
  });
}

function apiGet(path) {
  return fetch(path, { cache: "no-store" }).then(function (resp) {
    var ct = resp.headers.get("Content-Type") || "";
    if (ct.indexOf("json") >= 0) return resp.json();
    return resp.text();
  });
}

function apiPost(path, payload) {
  payload = payload || {};
  if (state.userId && payload.user_id === undefined) {
    payload.user_id = state.userId;
  }
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }).then(function (resp) {
    return resp.json().then(function (body) {
      if (!resp.ok && (body.error === "opening_reason_required" ||
                       body.error === "closing_reason_required")) {
        return confirmReason(body.message || "يلزم سبب مكتوب.").then(
          function (reason) {
            if (!reason) return body;
            payload.reason = reason;
            return apiPost(path, payload);
          });
      }
      if (!resp.ok) {
        toast(body.message || "خطأ");
      }
      body._status = resp.status;
      return body;
    });
  });
}

function egp(piasters) {
  var neg = piasters < 0 ? "-" : "";
  var a = Math.abs(piasters);
  return neg + Math.floor(a / 100) + "." + ("0" + (a % 100)).slice(-2);
}

function todayStr() {
  var d = new Date();
  function p(n) { return (n < 10 ? "0" : "") + n; }
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

/* -- session / users ------------------------------------------------ */

function loadSession() {
  return apiGet("/api/session").then(function (body) {
    var sel = $("user-select");
    sel.innerHTML = "";
    var ph = document.createElement("option");
    ph.value = "";
    ph.textContent = STR.user_pick;
    sel.appendChild(ph);
    body.users.forEach(function (u) {
      var o = document.createElement("option");
      o.value = u.id;
      o.textContent = u.name;
      sel.appendChild(o);
    });
    if (body.setup_required) {
      $("setup-box").className = "box";
    } else {
      $("setup-box").className = "hidden box";
    }
    if (body.users.length > 0 && !state.userId) {
      state.userId = body.users[0].id;
      sel.value = String(state.userId);
    }
  });
}

function loadSettings() {
  return apiGet("/api/settings").then(function (body) {
    if (body.settings && body.settings.demo === "1") {
      $("demo-badge").className = "";
    } else {
      $("demo-badge").className = "hidden";
    }
  });
}

/* -- day view -------------------------------------------------------- */

function unitOptions(units, selectedId) {
  return units.map(function (u) {
    var sel = (u.id === selectedId) ? ' selected' : '';
    return '<option value="' + u.id + '"' + sel + '>' +
      u.unit_name + '</option>';
  }).join("");
}

function loadDay() {
  if (!state.date) { toast("اختر التاريخ"); return Promise.resolve(); }
  return apiGet("/api/day?date=" + encodeURIComponent(state.date)).then(
    function (body) {
      $("day-label").textContent = body.date;
      $("day-status").textContent = body.status === "closed" ? STR.day_closed : "";
      var tb = $("counts-body");
      tb.innerHTML = "";
      body.counts.forEach(function (c) {
        var tr = document.createElement("tr");
        var cnt = c.count || {};
        var openingVal = (cnt.opening_qty_entered !== undefined &&
                          cnt.opening_qty_entered !== null)
          ? cnt.opening_qty_entered : "";
        var closingVal = (cnt.closing_qty_entered !== undefined &&
                          cnt.closing_qty_entered !== null)
          ? cnt.closing_qty_entered : "";
        var openBase = cnt.opening_base !== undefined ? cnt.opening_base
          : c.opening_default_base;
        var closeBase = (cnt.closing_base !== undefined &&
                         cnt.closing_base !== null) ? cnt.closing_base : null;
        var consumed = closeBase === null ? "-" :
          String(openBase + c.received_base - closeBase);
        tr.innerHTML =
          "<td>" + c.name + "<br><small>الافتراضي: " + c.opening_default_base +
          "</small></td>" +
          "<td><input data-m='" + c.material_id + "' data-f='opening' " +
          "  value='" + openingVal + "' type='number' min='0' step='any'>" +
          "<select data-mu='" + c.material_id + "' data-f='opening'>" +
          unitOptions(c.units, cnt.opening_unit_id) + "</select>" +
          "<button class='big' data-save='opening' data-m='" + c.material_id +
          "'>حفظ</button></td>" +
          "<td>" + c.received_base + "</td>" +
          "<td><input data-r='" + c.material_id + "' type='number' min='0' " +
          "  step='any' style='width:80px'>" +
          "<select data-ru='" + c.material_id + "'>" +
          unitOptions(c.units, null) + "</select>" +
          "<button class='big' data-add='" + c.material_id + "'>+</button></td>" +
          "<td><input data-m='" + c.material_id + "' data-f='closing' " +
          "  value='" + closingVal + "' type='number' min='0' step='any'>" +
          "<select data-mu='" + c.material_id + "' data-f='closing'>" +
          unitOptions(c.units, cnt.closing_unit_id) + "</select>" +
          "<button class='big' data-save='closing' data-m='" + c.material_id +
          "'>حفظ</button></td>" +
          "<td>" + consumed + "</td>";
        tb.appendChild(tr);
      });
      wireDayButtons();
      renderSales(body);
      renderReport(body.report);
    });
}

function rowQty(mid, field) {
  var inp = document.querySelector(
    "input[data-m='" + mid + "'][data-f='" + field + "']");
  var sel = document.querySelector(
    "select[data-mu='" + mid + "'][data-f='" + field + "']");
  return { qty: parseFloat(inp.value), unit: parseInt(sel.value, 10) };
}

function wireDayButtons() {
  var saves = document.querySelectorAll("button[data-save]");
  saves.forEach(function (b) {
    b.onclick = function () {
      var mid = parseInt(b.getAttribute("data-m"), 10);
      var field = b.getAttribute("data-save");
      var v = rowQty(mid, field);
      if (isNaN(v.qty) || v.qty < 0) { toast("كمية غير صالحة"); return; }
      apiPost("/api/day/count", {
        date: state.date, material_id: mid, field: field,
        qty_entered: v.qty, unit_id: v.unit
      }).then(function (body) {
        if (body._status === 200) {
          toast("تم الحفظ.");
          if (body.warnings && body.warnings.length) toast(body.warnings[0]);
          loadDay();
        }
      });
    };
  });
  var adds = document.querySelectorAll("button[data-add]");
  adds.forEach(function (b) {
    b.onclick = function () {
      var mid = parseInt(b.getAttribute("data-add"), 10);
      var q = document.querySelector("input[data-r='" + mid + "']");
      var s = document.querySelector("select[data-ru='" + mid + "']");
      var qty = parseFloat(q.value);
      if (isNaN(qty) || qty < 0) { toast("كمية غير صالحة"); return; }
      apiPost("/api/day/receipt", {
        date: state.date, material_id: mid,
        qty_entered: qty, unit_id: parseInt(s.value, 10)
      }).then(function (body) {
        if (body._status === 200) { toast("تم الحفظ."); loadDay(); }
      });
    };
  });
}

function renderSales(body) {
  var box = $("sales-box");
  box.innerHTML = "";
  var sales = {};
  body.sales.forEach(function (s) { sales[s.product_id] = s.qty_sold; });
  body.products.forEach(function (p) {
    if (p.sold_source !== "manual") return;
    var div = document.createElement("div");
    div.innerHTML = p.name +
      " <input data-sale='" + p.id + "' type='number' min='0' step='1' " +
      "  value='" + (sales[p.id] || 0) + "'>" +
      " <button class='big' data-savesale='" + p.id + "'>حفظ</button>";
    box.appendChild(div);
  });
  box.querySelectorAll("button[data-savesale]").forEach(function (b) {
    b.onclick = function () {
      var pid = parseInt(b.getAttribute("data-savesale"), 10);
      var q = document.querySelector("input[data-sale='" + pid + "']");
      var qty = parseInt(q.value, 10);
      if (isNaN(qty) || qty < 0) { toast("كمية غير صالحة"); return; }
      apiPost("/api/day/sale",
        { date: state.date, product_id: pid, qty_sold: qty }
      ).then(function (bd) {
        if (bd._status === 200) { toast("تم الحفظ."); loadDay(); }
      });
    };
  });
  // Coffee cross-check box.
  var cb = $("coffee-box");
  cb.innerHTML = "";
  var hasCoffee = body.products.some(function (p) {
    return p.sold_source === "derived_remainder_of_cup";
  });
  if (hasCoffee) {
    cb.innerHTML = "عد يدوي لأكواب السادة (اختياري، للمطابقة فقط) " +
      "<input id='coffee-counted' type='number' min='0' step='1'>" +
      " <button class='big' id='coffee-save'>حفظ</button>" +
      " <span id='coffee-info'></span>";
    $("coffee-save").onclick = function () {
      var v = parseInt($("coffee-counted").value, 10);
      if (isNaN(v) || v < 0) { toast("كمية غير صالحة"); return; }
      apiPost("/api/day/coffee-check",
        { date: state.date, counted_cups: v }).then(function (bd) {
        if (bd._status === 200) { toast("تم الحفظ."); loadDay(); }
      });
    };
  }
}

function renderReport(rep) {
  var box = $("report");
  if (!rep) { box.innerHTML = "-"; return; }
  var h = "<table><tr><th>المنتج</th><th>مباع</th><th>إيراد</th>" +
    "<th>تكلفة</th><th>ربح</th></tr>";
  rep.lines.forEach(function (ln) {
    h += "<tr><td>" + ln.name + "</td><td>" + ln.qty_sold + "</td><td>" +
      egp(ln.revenue) + "</td><td>" + egp(ln.cost) + "</td><td>" +
      egp(ln.profit) + "</td></tr>";
  });
  h += "</table>";
  h += "<p>الإجمالي: إيراد " + egp(rep.total_revenue) + " / تكلفة " +
    egp(rep.total_cost) + " / ربح " + egp(rep.total_profit) + "</p>";
  h += "<p>مطابقة الأكواب: مستهلك " + rep.reconciliation.cups_consumed +
    " / محسوب " + rep.reconciliation.cups_derived_total + " / الفرق " +
    rep.reconciliation.difference + "</p>";
  if (rep.yield) {
    h += "<p>القهوة: " + rep.yield.grams_per_cup.toFixed(1) +
      " جم/كوب، " + rep.yield.cups_per_bag.toFixed(1) + " كوب/كيس " +
      "(ثقة: " + rep.yield.confidence + "، أيام: " + rep.yield.days_used +
      "، أكواب: " + rep.yield.cups_used + ")</p>";
  }
  if (rep.coffee_check) {
    h += "<p class='" + (rep.coffee_check.ok ? "ok" : "warn") + "'>" +
      "مطابقة القهوة: محسوب " + rep.coffee_check.derived + " / معدود " +
      rep.coffee_check.counted + "</p>";
  }
  rep.warnings.forEach(function (w) { h += "<p class='warn'>" + w + "</p>"; });
  box.innerHTML = h;
}

/* -- items tab ---------------------------------------------------------- */

function loadItems() {
  return apiGet("/api/materials").then(function (body) {
    state.materials = body.materials;
    var ml = $("materials-list");
    ml.innerHTML = "";
    body.materials.forEach(function (m) {
      var d = document.createElement("div");
      d.textContent = m.name + " (" + m.department + ") وحدات: " +
        m.units.map(function (u) {
          return u.unit_name + "=" + u.factor_to_base;
        }).join(", ");
      ml.appendChild(d);
    });
  }).then(function () {
    return apiGet("/api/products");
  }).then(function (body) {
    state.products = body.products;
    var pl = $("products-list");
    pl.innerHTML = "";
    body.products.forEach(function (p) {
      var d = document.createElement("div");
      d.textContent = p.name + " (" + p.sold_source + ")";
      pl.appendChild(d);
    });
  });
}

/* -- reports tab --------------------------------------------------------- */

function loadRange() {
  var f = $("rep-from").value, t = $("rep-to").value;
  if (!f || !t) { toast("اختر المدة"); return; }
  $("csv-link").href = "/api/export.csv?from=" + encodeURIComponent(f) +
    "&to=" + encodeURIComponent(t);
  apiGet("/api/report?from=" + encodeURIComponent(f) +
         "&to=" + encodeURIComponent(t)).then(function (body) {
    var h = "<table><tr><th>اليوم</th><th>إيراد</th><th>تكلفة</th>" +
      "<th>ربح</th></tr>";
    (body.days || []).forEach(function (d) {
      h += "<tr><td>" + d.date + "</td><td>" + egp(d.revenue) + "</td><td>" +
        egp(d.cost) + "</td><td>" + egp(d.profit) + "</td></tr>";
    });
    h += "</table>";
    if (body.totals) {
      h += "<p>الإجمالي: " + egp(body.totals.revenue) + " / " +
        egp(body.totals.cost) + " / " + egp(body.totals.profit) + "</p>";
    }
    $("range-report").innerHTML = h;
  });
}

/* -- wiring -------------------------------------------------------------- */

function heartbeat() {
  fetch("/api/heartbeat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  }).catch(function () { /* server momentarily busy; next beat retries */ });
}

function init() {
  loadStrings();
  state.date = todayStr();
  $("day-input").value = state.date;
  $("m-date").value = state.date;
  $("rep-from").value = state.date;
  $("rep-to").value = state.date;
  loadSession().then(function () { return loadSettings(); }).then(
    function () { return loadDay(); }).then(function () { loadItems(); });

  document.querySelectorAll("#tabs .tab").forEach(function (b) {
    b.onclick = function () {
      document.querySelectorAll("#tabs .tab").forEach(function (x) {
        x.className = "big tab";
      });
      b.className = "big tab active";
      ["day", "items", "reports"].forEach(function (t) {
        $("tab-" + t).className = (t === b.getAttribute("data-tab")) ? "" : "hidden";
      });
      if (b.getAttribute("data-tab") === "items") loadItems();
    };
  });

  $("user-select").onchange = function () {
    state.userId = parseInt($("user-select").value, 10) || null;
  };
  $("load-day").onclick = function () {
    state.date = $("day-input").value;
    loadDay();
  };
  $("day-input").onchange = function () { state.date = $("day-input").value; };

  $("add-user-btn").onclick = function () {
    var name = $("new-user-name").value.trim();
    if (!name) { toast("اكتب الاسم"); return; }
    var payload = { name: name };
    if (state.userId) payload.user_id = state.userId;
    apiPost("/api/users", payload).then(function (body) {
      if (body._status === 200) {
        toast("تم الحفظ.");
        $("new-user-name").value = "";
        loadSession();
      }
    });
  };

  $("m-add").onclick = function () {
    var payload = {
      name: $("m-name").value.trim(),
      department: $("m-dept").value,
      base_unit: $("m-base").value,
      is_cup: $("m-cup").checked
    };
    var uname = $("m-unit").value.trim();
    if (uname) {
      payload.units = [{
        unit_name: uname,
        factor_to_base: parseInt($("m-factor").value, 10)
      }];
    }
    var cost = parseInt($("m-cost").value, 10);
    apiPost("/api/materials", payload).then(function (body) {
      if (body._status === 200) {
        toast("تم الحفظ.");
        // Attach the first cost to the new extra unit (if any).
        if (!isNaN(cost) && uname) {
          apiGet("/api/materials").then(function (mb) {
            var m = mb.materials.filter(function (x) {
              return x.id === body.id;
            })[0];
            var u = m.units.filter(function (x) {
              return x.unit_name === uname;
            })[0];
            return apiPost("/api/costs", {
              material_id: body.id, unit_id: u.id,
              price_piasters: cost, effective_date: state.date
            });
          }).then(function () { loadItems(); loadDay(); });
        } else { loadItems(); loadDay(); }
      }
    });
  };

  $("close-day-btn").onclick = function () {
    apiPost("/api/day/close", { date: state.date }).then(function (body) {
      if (body._status === 200) { toast("تم إغلاق اليوم."); loadDay(); }
    });
  };
  $("backup-btn").onclick = function () {
    apiPost("/api/backup", {}).then(function (body) {
      if (body._status === 200) toast("تم الحفظ.");
    });
  };
  $("rep-show").onclick = loadRange;
  $("quit-btn").onclick = function () {
    apiPost("/api/shutdown", {}).then(function () {
      toast("جارٍ إغلاق البرنامج...");
      try { window.close(); } catch (e) { /* kiosk closes via launcher */ }
    });
  };
  setInterval(heartbeat, 10000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
