/* screen-products.js - list + edit panel for materials and products. */
var KIOSK = KIOSK || {};

KIOSK.productsScreen = (function () {
  var api = KIOSK.api, fmt = KIOSK.fmt, ui = KIOSK.ui;
  var materials = [];
  var products = [];
  var sel = null; /* {kind:'mat'|'prod'|'newmat'|'newprod', id} */

  function uid() { return KIOSK.app.userId(); }
  function dept() { return KIOSK.app.dept(); }

  function show(root) {
    document.getElementById("content").classList.remove("with-actionbar");
    document.getElementById("actionbar").classList.add("hidden");
    load(root);
  }

  function load(root) {
    ui.loading(root);
    api.get("/api/materials").then(function (m) {
      materials = m.materials || [];
      return api.get("/api/products");
    }).then(function (p) {
      products = p.products || [];
      KIOSK.app.setCatalog(products);
      if (!sel) {
        var vis = visibleMats();
        sel = vis.length ? { kind: "mat", id: vis[0].id } : { kind: "newmat" };
      }
      render(root);
    });
  }

  function visibleMats() {
    return materials.filter(function (m) {
      return dept() === "all" || m.department === dept();
    });
  }

  function visibleProds() {
    return products.filter(function (p) {
      return dept() === "all" || p.department === dept();
    });
  }

  function deptTag(d) {
    return '<span class="dept-tag">' +
      fmt.esc(d === "kitchen" ? STR.dept_kitchen : STR.dept_cafeteria) +
      "</span>";
  }

  function render(root) {
    var h = '<div class="screen screen-products"><div class="prod-list">' +
      '<div class="formrow"><button type="button" data-new="mat">+ ' +
      fmt.esc(STR.mat_new) + '</button><button type="button" data-new="prod">+ ' +
      fmt.esc(STR.prod_new) + "</button></div>" +
      '<div class="scroll"><div class="small muted">' +
      fmt.esc(STR.prod_materials) + "</div>";
    var vm = visibleMats();
    if (!vm.length) h += '<div class="muted">' + fmt.esc(STR.empty) + "</div>";
    vm.forEach(function (m) {
      h += '<button type="button" class="prod-item' +
        (sel && sel.kind === "mat" && sel.id === m.id ? " active" : "") +
        '" data-sel="mat:' + m.id + '">' + fmt.esc(m.name) + deptTag(m.department) +
        "</button>";
    });
    h += '<div class="small muted" style="margin-top:8px">' +
      fmt.esc(STR.prod_products) + "</div>";
    var vp = visibleProds();
    if (!vp.length) h += '<div class="muted">' + fmt.esc(STR.empty) + "</div>";
    vp.forEach(function (p) {
      h += '<button type="button" class="prod-item' +
        (sel && sel.kind === "prod" && sel.id === p.id ? " active" : "") +
        '" data-sel="prod:' + p.id + '">' + fmt.esc(p.name) + deptTag(p.department) +
        "</button>";
    });
    h += '</div></div><div class="prod-edit" id="prod-edit"></div></div>';
    root.innerHTML = h;
    var news = root.querySelectorAll("[data-new]");
    for (var i = 0; i < news.length; i++) {
      (function (b) {
        b.onclick = function () {
          sel = b.getAttribute("data-new") === "mat"
            ? { kind: "newmat" } : { kind: "newprod" };
          render(root);
        };
      })(news[i]);
    }
    var items = root.querySelectorAll("[data-sel]");
    for (var k = 0; k < items.length; k++) {
      (function (b) {
        b.onclick = function () {
          var parts = b.getAttribute("data-sel").split(":");
          sel = { kind: parts[0], id: parseInt(parts[1], 10) };
          render(root);
        };
      })(items[k]);
    }
    renderEdit(root.querySelector("#prod-edit"));
  }

  /* ---------- edit panel ---------- */

  function renderEdit(box) {
    if (!sel) { ui.empty(box); return; }
    if (sel.kind === "newmat") { newMatForm(box); return; }
    if (sel.kind === "newprod") { newProdForm(box); return; }
    if (sel.kind === "mat") {
      ui.loading(box);
      api.get("/api/materials/" + sel.id).then(function (m) {
        matEdit(box, m);
      });
      return;
    }
    ui.loading(box);
    api.get("/api/products/" + sel.id).then(function (p) {
      prodEdit(box, p);
    });
  }

  function inactiveNote(active) {
    return active ? "" : ' <span class="chip new">' + fmt.esc(STR.inactive_tag) +
      "</span>";
  }

  function matEdit(box, m) {
    var h = '<div class="card"><h3>' + fmt.esc(m.name) +
      inactiveNote(m.active) + "</h3>";
    h += '<div class="formrow"><span>' + fmt.esc(STR.mat_name) + "</span>" +
      '<input type="text" id="pe-name" value="' + fmt.esc(m.name) +
      '" style="flex:1;min-width:200px">' +
      '<button type="button" id="pe-rename">' + fmt.esc(STR.rename) +
      "</button></div>";
    h += "<div>" + fmt.esc(STR.base_unit) + ": <b>" +
      fmt.esc(fmt.baseLabel(m.base_unit)) + "</b> " + deptTag(m.department) +
      (m.is_cup ? '<span class="dept-tag">' + fmt.esc(STR.is_cup) + "</span>" : "") +
      "</div></div>";
    h += '<div class="card"><h3>' + fmt.esc(STR.count_units) + "</h3>" +
      '<table class="grid"><tbody>';
    m.units.forEach(function (u, i) {
      h += '<tr class="' + (i % 2 ? "zebra" : "") + '"><td style="text-align:right">' +
        fmt.esc(u.unit_name) + '</td><td class="num">= ' + fmt.int(u.factor_to_base) +
        "</td></tr>";
    });
    h += "</tbody></table>" +
      '<div class="formrow" style="margin-top:8px"><input type="text" id="nu-name" placeholder="' +
      fmt.esc(STR.unit_name_ph) + '">' +
      '<input type="text" inputmode="decimal" id="nu-factor" class="qty" placeholder="' +
      fmt.esc(STR.factor_ph) + '">' +
      '<button type="button" id="nu-add">' + fmt.esc(STR.add) + "</button></div>" +
      '<div class="inline-err" id="nu-err"></div></div>';
    h += '<div class="card"><h3>' + fmt.esc(STR.cost_title) + "</h3>" +
      '<table class="grid"><tbody>';
    (m.costs || []).forEach(function (c, i) {
      h += '<tr class="' + (i % 2 ? "zebra" : "") + '"><td style="text-align:right">' +
        fmt.esc(c.unit_name) + '</td><td>' + fmt.moneyHtml(c.price_piasters) +
        '</td><td class="num">' + fmt.esc(c.effective_date) + "</td></tr>";
    });
    h += "</tbody></table>" +
      '<div class="formrow" style="margin-top:8px"><select id="nc-unit">' +
      m.units.map(function (u) {
        return '<option value="' + u.id + '">' + fmt.esc(u.unit_name) + "</option>";
      }).join("") + "</select>" +
      '<input type="text" inputmode="decimal" id="nc-price" class="qty" placeholder="' +
      fmt.esc(STR.cost_egp_ph) + '">' +
      '<input type="text" inputmode="numeric" id="nc-date" maxlength="10" placeholder="YYYY-MM-DD" class="num" value="' + fmt.esc(KIOSK.app.date()) + '">' +
      '<button type="button" id="nc-add" class="btn-primary">' + fmt.esc(STR.add) +
      "</button></div>" +
      '<div class="inline-err" id="nc-err"></div></div>';
    h += '<button type="button" id="pe-active" class="' +
      (m.active ? "" : "btn-primary") + '">' +
      fmt.esc(m.active ? STR.deactivate : STR.activate) + "</button>";
    box.innerHTML = h;
    document.getElementById("pe-rename").onclick = function () {
      var v = document.getElementById("pe-name").value.trim();
      api.post("/api/materials/" + m.id + "/rename",
        { name: v, user_id: uid() }).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        load(document.getElementById("content"));
      });
    };
    document.getElementById("nu-add").onclick = function () {
      var nm = document.getElementById("nu-name").value.trim();
      var fp = fmt.parseQty(document.getElementById("nu-factor").value);
      if (!nm || !fp.ok || Math.round(fp.value) !== fp.value || fp.value < 1) {
        document.getElementById("nu-err").textContent = STR.err_bad_number;
        return;
      }
      api.post("/api/units", {
        material_id: m.id, unit_name: nm,
        factor_to_base: Math.round(fp.value), user_id: uid()
      }).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        renderEdit(box);
        loadListsOnly();
      });
    };
    document.getElementById("nc-add").onclick = function () {
      var pr = fmt.parseQty(document.getElementById("nc-price").value);
      var dt = document.getElementById("nc-date").value.trim();
      if (!pr.ok) {
        document.getElementById("nc-err").textContent = STR.err_bad_number;
        return;
      }
      if (!KIOSK.dates.parse(dt)) {
        document.getElementById("nc-err").textContent = STR.err_bad_date;
        return;
      }
      api.post("/api/costs", {
        material_id: m.id,
        unit_id: parseInt(document.getElementById("nc-unit").value, 10),
        price_egp: pr.value, effective_date: dt, user_id: uid()
      }).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        renderEdit(box);
      });
    };
    document.getElementById("pe-active").onclick = function () {
      api.post("/api/materials/" + m.id + "/set_active",
        { active: m.active ? 0 : 1, user_id: uid() }).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        load(document.getElementById("content"));
      });
    };
  }

  function srcExplain(src) {
    if (src === "derived_from_material") return STR.src_sachet_hint;
    if (src === "derived_remainder_of_cup") return STR.src_remainder_hint;
    return STR.src_manual_hint;
  }

  function prodEdit(box, p) {
    var h = '<div class="card"><h3>' + fmt.esc(p.name) +
      inactiveNote(p.active) + "</h3>";
    h += '<div class="formrow"><span>' + fmt.esc(STR.prod_name) + "</span>" +
      '<input type="text" id="pe-name" value="' + fmt.esc(p.name) +
      '" style="flex:1;min-width:200px">' +
      '<button type="button" id="pe-rename">' + fmt.esc(STR.rename) +
      "</button></div>";
    h += "<div>" + deptTag(p.department) + "</div>";
    h += '<div class="formrow" style="margin-top:8px"><span>' +
      fmt.esc(STR.sold_source) + "</span>" +
      '<select id="pe-src" disabled>' +
      '<option value="derived_from_material"' +
      (p.sold_source === "derived_from_material" ? " selected" : "") + ">" +
      fmt.esc(STR.src_sachet) + "</option>" +
      '<option value="derived_remainder_of_cup"' +
      (p.sold_source === "derived_remainder_of_cup" ? " selected" : "") + ">" +
      fmt.esc(STR.src_remainder) + "</option>" +
      '<option value="manual"' +
      (p.sold_source === "manual" ? " selected" : "") + ">" +
      fmt.esc(STR.src_manual) + "</option></select></div>" +
      '<div class="small muted">' + fmt.esc(srcExplain(p.sold_source)) + "</div></div>";
    h += '<div class="card"><h3>' + fmt.esc(STR.recipe_title) + "</h3>" +
      '<table class="grid"><tbody>';
    (p.recipe || []).forEach(function (r, i) {
      h += '<tr class="' + (i % 2 ? "zebra" : "") + '"><td style="text-align:right">' +
        fmt.esc(r.material_name) + '</td><td class="num">' + fmt.int(r.qty_base) +
        '</td><td class="num">' + fmt.esc(r.effective_date) + "</td></tr>";
    });
    h += "</tbody></table>";
    var matOpts = materials.map(function (m) {
      return '<option value="' + m.id + '">' + fmt.esc(m.name) + "</option>";
    }).join("");
    h += '<div class="formrow" style="margin-top:8px"><select id="nr-mat">' +
      matOpts + "</select>" +
      '<input type="text" inputmode="decimal" id="nr-qty" class="qty" placeholder="' +
      fmt.esc(STR.recipe_qty_ph) + '">' +
      '<select id="nr-unit" class="unit"></select>' +
      '<input type="text" inputmode="numeric" id="nr-date" maxlength="10" placeholder="YYYY-MM-DD" class="num" value="' + fmt.esc(KIOSK.app.date()) + '">' +
      '<button type="button" id="nr-add">' + fmt.esc(STR.add) + "</button></div>" +
      '<div class="inline-err" id="nr-err"></div></div>';
    h += '<div class="card"><h3>' + fmt.esc(STR.price_title) + "</h3>" +
      '<table class="grid"><tbody>';
    (p.prices || []).forEach(function (pr, i) {
      h += '<tr class="' + (i % 2 ? "zebra" : "") + '"><td>' +
        fmt.moneyHtml(pr.price_piasters) + '</td><td class="num">' +
        fmt.esc(pr.effective_date) + "</td></tr>";
    });
    h += "</tbody></table>" +
      '<div class="formrow" style="margin-top:8px">' +
      '<input type="text" inputmode="decimal" id="np-price" class="qty" placeholder="' +
      fmt.esc(STR.price_egp_ph) + '">' +
      '<input type="text" inputmode="numeric" id="np-date" maxlength="10" placeholder="YYYY-MM-DD" class="num" value="' + fmt.esc(KIOSK.app.date()) + '">' +
      '<button type="button" id="np-add" class="btn-primary">' +
      fmt.esc(STR.add) + "</button></div>" +
      '<div class="inline-err" id="np-err"></div>' +
      '<div class="small muted">' + fmt.esc(STR.today_or_later) + "</div></div>";
    h += '<button type="button" id="pe-active" class="' +
      (p.active ? "" : "btn-primary") + '">' +
      fmt.esc(p.active ? STR.deactivate : STR.activate) + "</button>";
    box.innerHTML = h;

    var matSel = document.getElementById("nr-mat");
    function fillUnits() {
      var mid = parseInt(matSel.value, 10);
      var m = null;
      for (var i = 0; i < materials.length; i++) {
        if (materials[i].id === mid) m = materials[i];
      }
      document.getElementById("nr-unit").innerHTML = m ? m.units.map(function (u) {
        return '<option value="' + u.id + '">' + fmt.esc(u.unit_name) + "</option>";
      }).join("") : "";
    }
    matSel.onchange = fillUnits;
    fillUnits();

    document.getElementById("pe-rename").onclick = function () {
      var v = document.getElementById("pe-name").value.trim();
      api.post("/api/products/" + p.id + "/rename",
        { name: v, user_id: uid() }).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        load(document.getElementById("content"));
      });
    };
    document.getElementById("nr-add").onclick = function () {
      var qp = fmt.parseQty(document.getElementById("nr-qty").value);
      var dt = document.getElementById("nr-date").value.trim();
      if (!qp.ok) {
        document.getElementById("nr-err").textContent = STR.err_bad_number;
        return;
      }
      if (!KIOSK.dates.parse(dt)) {
        document.getElementById("nr-err").textContent = STR.err_bad_date;
        return;
      }
      api.post("/api/recipe", {
        product_id: p.id, material_id: parseInt(matSel.value, 10),
        qty_entered: qp.value,
        unit_id: parseInt(document.getElementById("nr-unit").value, 10),
        effective_date: document.getElementById("nr-date").value,
        user_id: uid()
      }).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        renderEdit(box);
      });
    };
    document.getElementById("np-add").onclick = function () {
      var pr = fmt.parseQty(document.getElementById("np-price").value);
      var dt = document.getElementById("np-date").value.trim();
      if (!pr.ok) {
        document.getElementById("np-err").textContent = STR.err_bad_number;
        return;
      }
      if (!KIOSK.dates.parse(dt) || dt < KIOSK.dates.todayLocal()) {
        document.getElementById("np-err").textContent = STR.today_or_later;
        return;
      }
      api.post("/api/prices", {
        product_id: p.id, price_egp: pr.value,
        effective_date: dt, user_id: uid()
      }).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        renderEdit(box);
      });
    };
    document.getElementById("pe-active").onclick = function () {
      api.post("/api/products/" + p.id + "/set_active",
        { active: p.active ? 0 : 1, user_id: uid() }).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        load(document.getElementById("content"));
      });
    };
  }

  function newMatForm(box) {
    box.innerHTML = '<div class="card"><h3>' + fmt.esc(STR.mat_new) + "</h3>" +
      '<div class="formrow"><span>' + fmt.esc(STR.mat_name) + "</span>" +
      '<input type="text" id="nm-name" style="flex:1"></div>' +
      '<div class="formrow"><span>' + fmt.esc(STR.base_unit) + "</span>" +
      '<select id="nm-base"><option value="g">' + fmt.esc(STR.unit_g) +
      '</option><option value="ml">' + fmt.esc(STR.unit_ml) +
      '</option><option value="piece">' + fmt.esc(STR.unit_piece) +
      "</option></select>" +
      '<label><input type="checkbox" id="nm-cup" style="min-height:24px"> ' +
      fmt.esc(STR.is_cup) + "</label></div>" +
      '<div class="formrow"><input type="text" id="nm-unit" placeholder="' +
      fmt.esc(STR.unit_name_ph) + '">' +
      '<input type="text" inputmode="decimal" id="nm-factor" class="qty" placeholder="' +
      fmt.esc(STR.factor_ph) + '">' +
      '<input type="text" inputmode="decimal" id="nm-cost" class="qty" placeholder="' +
      fmt.esc(STR.cost_egp_ph) + '"></div>' +
      '<div class="inline-err" id="nm-err"></div>' +
      '<button type="button" id="nm-add" class="btn-primary">' +
      fmt.esc(STR.add) + "</button></div>";
    document.getElementById("nm-add").onclick = function () {
      var name = document.getElementById("nm-name").value.trim();
      if (!name) {
        document.getElementById("nm-err").textContent = STR.err_bad_number;
        return;
      }
      var payload = {
        name: name, department: dept() === "all" ? "cafeteria" : dept(),
        base_unit: document.getElementById("nm-base").value,
        is_cup: document.getElementById("nm-cup").checked, user_id: uid()
      };
      var un = document.getElementById("nm-unit").value.trim();
      var fp = fmt.parseQty(document.getElementById("nm-factor").value);
      var cp = fmt.parseQty(document.getElementById("nm-cost").value);
      var hasUnit = un && fp.ok;
      if (un || document.getElementById("nm-factor").value) {
        if (!hasUnit || Math.round(fp.value) !== fp.value) {
          document.getElementById("nm-err").textContent = STR.err_bad_number;
          return;
        }
        payload.units = [{ unit_name: un, factor_to_base: Math.round(fp.value) }];
      }
      api.post("/api/materials", payload).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        var done = function () {
          ui.toast(STR.saved);
          sel = { kind: "mat", id: body.id };
          load(document.getElementById("content"));
        };
        if (hasUnit && cp.ok && document.getElementById("nm-cost").value) {
          api.get("/api/materials").then(function (mb) {
            var found = null;
            mb.materials.forEach(function (x) {
              if (x.id === body.id) found = x;
            });
            var u = null;
            if (found) found.units.forEach(function (x) {
              if (x.unit_name === un) u = x;
            });
            if (!u) { done(); return; }
            api.post("/api/costs", {
              material_id: body.id, unit_id: u.id, price_egp: cp.value,
              effective_date: KIOSK.app.date(), user_id: uid()
            }).then(function () { done(); });
          });
        } else { done(); }
      });
    };
  }

  function newProdForm(box) {
    var matOpts = materials.map(function (m) {
      return '<option value="' + m.id + '">' + fmt.esc(m.name) + "</option>";
    }).join("");
    box.innerHTML = '<div class="card"><h3>' + fmt.esc(STR.prod_new) + "</h3>" +
      '<div class="formrow"><span>' + fmt.esc(STR.prod_name) + "</span>" +
      '<input type="text" id="np-name" style="flex:1"></div>' +
      '<div class="formrow"><span>' + fmt.esc(STR.sold_source) + "</span>" +
      '<select id="np-src"><option value="derived_from_material">' +
      fmt.esc(STR.src_sachet) + '</option><option value="derived_remainder_of_cup">' +
      fmt.esc(STR.src_remainder) + '</option><option value="manual">' +
      fmt.esc(STR.src_manual) + "</option></select></div>" +
      '<div class="small muted" id="np-src-hint"></div>' +
      '<div class="formrow" id="np-sachet-row"><span>' +
      fmt.esc(STR.source_material) + '</span><select id="np-smat">' + matOpts +
      '</select><input type="text" inputmode="decimal" id="np-sqty" class="qty" placeholder="' +
      fmt.esc(STR.recipe_qty_cup) + '"></div>' +
      '<div class="formrow hidden" id="np-coffee-row"><span>' +
      fmt.esc(STR.coffee_material) + '</span><select id="np-cmat">' + matOpts +
      "</select></div>" +
      '<div class="formrow"><label><input type="checkbox" id="np-cup" style="min-height:24px"> ' +
      fmt.esc(STR.uses_cup) + "</label>" +
      '<input type="text" inputmode="decimal" id="np-price" class="qty" placeholder="' +
      fmt.esc(STR.price_egp_ph) + '"></div>' +
      '<div class="inline-err" id="np-err"></div>' +
      '<button type="button" id="np-add" class="btn-primary">' +
      fmt.esc(STR.add) + "</button></div>";
    var srcSel = document.getElementById("np-src");
    function hint() {
      var v = srcSel.value;
      document.getElementById("np-src-hint").textContent = srcExplain(v);
      document.getElementById("np-sachet-row").classList.toggle("hidden",
        v !== "derived_from_material");
      document.getElementById("np-coffee-row").classList.toggle("hidden",
        v !== "derived_remainder_of_cup");
    }
    srcSel.onchange = hint;
    hint();
    document.getElementById("np-add").onclick = function () {
      var name = document.getElementById("np-name").value.trim();
      var src = srcSel.value;
      var pr = fmt.parseQty(document.getElementById("np-price").value);
      if (!name || !pr.ok) {
        document.getElementById("np-err").textContent = STR.err_bad_number;
        return;
      }
      var payload = {
        name: name, department: dept() === "all" ? "cafeteria" : dept(),
        sold_source: src, uses_cup: document.getElementById("np-cup").checked,
        first_price: { price_egp: pr.value,
          effective_date: KIOSK.app.date() }, user_id: uid()
      };
      if (src === "derived_from_material") {
        var smid = parseInt(document.getElementById("np-smat").value, 10);
        var sq = fmt.parseQty(document.getElementById("np-sqty").value);
        if (!sq.ok || sq.value <= 0) {
          document.getElementById("np-err").textContent = STR.err_bad_number;
          return;
        }
        /* Per-cup qty entered in the source material's base unit. */
        var m = null;
        materials.forEach(function (x) { if (x.id === smid) m = x; });
        var baseUnit = null;
        if (m) m.units.forEach(function (u) {
          if (u.is_base_unit) baseUnit = u;
        });
        if (!baseUnit) {
          document.getElementById("np-err").textContent = STR.err_bad_number;
          return;
        }
        payload.source_material_id = smid;
        payload.recipe_qty_entered = sq.value;
        payload.recipe_unit_id = baseUnit.id;
      } else if (src === "derived_remainder_of_cup") {
        payload.coffee_material_id =
          parseInt(document.getElementById("np-cmat").value, 10);
      }
      api.post("/api/products", payload).then(function (body) {
        if (body._status !== 200) { api.failToast(body); return; }
        ui.toast(STR.saved);
        sel = { kind: "prod", id: body.id };
        load(document.getElementById("content"));
      });
    };
  }

  function loadListsOnly() {
    api.get("/api/materials").then(function (m) {
      materials = m.materials || [];
      return api.get("/api/products");
    }).then(function (p) {
      products = p.products || [];
      KIOSK.app.setCatalog(products);
    });
  }

  function cleanup() {
    materials = []; products = []; sel = null;
  }

  return { show: show, cleanup: cleanup };
})();
