/* screen-report.js - daily report: cards, drink bars, yield, tables. */
var KIOSK = KIOSK || {};

KIOSK.reportScreen = (function () {
  var api = KIOSK.api, fmt = KIOSK.fmt, ui = KIOSK.ui;

  function dept() { return KIOSK.app.dept(); }

  function show(root) {
    ui.loading(root);
    document.getElementById("content").classList.remove("with-actionbar");
    document.getElementById("actionbar").classList.add("hidden");
    api.get("/api/day?date=" + KIOSK.app.date()).then(function (d) {
      render(root, d);
      KIOSK.app.refreshChrome(d);
    });
  }

  function render(root, d) {
    var rep = d.report;
    if (!rep) {
      root.innerHTML = '<div class="screen"><div class="muted">' +
        fmt.esc(STR.empty) + "</div></div>";
      return;
    }
    /* Department filter applies to product lines; cards recompute. */
    var lines = rep.lines.filter(function (ln) {
      if (dept() === "all") return true;
      var pd = KIOSK.app.productDept(ln.product_id);
      return !pd || pd === dept();
    });
    var tRev = 0, tCost = 0, tProfit = 0, tCups = 0;
    lines.forEach(function (ln) {
      tRev += ln.revenue; tCost += ln.cost; tProfit += ln.profit;
    });
    rep.cups_by_drink.forEach(function (c) {
      var keep = lines.some(function (ln) { return ln.product_id === c.product_id; });
      if (keep) tCups += c.cups;
    });
    var h = '<div class="screen"><div class="rep-cards">' +
      card(STR.revenue, fmt.moneyHtml(tRev)) +
      card(STR.cost, fmt.moneyHtml(tCost)) +
      card(STR.profit, fmt.moneyHtml(tProfit, tProfit < 0 ? "neg" : "pos")) +
      card(STR.total_cups, '<span class="bignum num">' + fmt.int(tCups) +
        "</span>") +
      "</div>";
    var maxCups = 1;
    var keptIds = {};
    lines.forEach(function (ln) { keptIds[ln.product_id] = true; });
    var drinks = rep.cups_by_drink.filter(function (c) {
      return keptIds[c.product_id];
    });
    drinks.forEach(function (c) {
      if (c.cups > maxCups) maxCups = c.cups;
    });
    var bars = "";
    drinks.forEach(function (c) {
      var w = Math.round(100 * c.cups / maxCups);
      bars += '<div class="bar-row"><span class="bar-name">' +
        fmt.esc(c.name) + '</span><div class="bar-track"><div class="bar-fill" style="width:' +
        w + '%"></div></div><span class="bar-val num">' + fmt.int(c.cups) +
        "</span></div>";
    });
    var rec = rep.reconciliation;
    bars += '<div class="small" style="margin-top:8px">' +
      (rec.difference === 0
        ? '<span class="chip closed">' + fmt.esc(STR.check) + " " +
          fmt.esc(STR.reconcile_ok) + "</span>"
        : '<span class="chip open">' + fmt.esc(STR.reconcile_diff) +
          ': <span class="num">' + fmt.int(rec.difference) + "</span></span>") +
      "</div>";
    var y = rep.yield || {};
    var confKey = { high: "conf_high", medium: "conf_medium", low: "conf_low",
      none: "conf_none" }[y.confidence] || "conf_none";
    var perBag = y.cups_per_bag || 0;
    var yieldHtml = '<div class="bignum num">~' +
      (Math.round(perBag * 10) / 10).toFixed(1) + " " +
      fmt.esc(STR.yield_per_bag) + "</div>" +
      "<div>" + fmt.esc(STR.grams_per_cup) + ': <b class="num">' +
      (y.grams_per_cup ? y.grams_per_cup.toFixed(1) : "-") + "</b></div>" +
      '<div><span class="chip ' +
      (y.confidence === "high" ? "closed" : y.confidence === "none" ? "new" : "open") +
      '">' + fmt.esc(STR[confKey]) + "</span></div>" +
      '<div class="small muted">' + fmt.esc(STR.yield_based_on) + ' <span class="num">' +
      fmt.int(y.days_used || 0) + "</span> " + fmt.esc(STR.yield_days) +
      ' <span class="num">' + fmt.int(y.cups_used || 0) + "</span> " +
      fmt.esc(STR.yield_cups) + "</div>";
    if (y.source === "estimate") {
      yieldHtml += '<div class="small muted">' +
        fmt.esc(STR.yield_estimate_note) + "</div>";
    }
    var tablesH = '<div class="rep-tables"><div class="card"><h3>' +
      fmt.esc(STR.col_product) + "</h3>" + productTable(lines) + "</div>" +
      '<div class="card"><h3>' + fmt.esc(STR.variance_title) + "</h3>" +
      varianceTable(rep, d) + "</div></div>";
    if (rep.coffee_check) {
      tablesH += '<div class="card">' +
        (rep.coffee_check.ok
          ? '<span class="chip closed">' + fmt.esc(STR.check) + " " +
            fmt.esc(STR.coffee_check_ok) + "</span>"
          : '<span class="chip open">' + fmt.esc(STR.coffee_check_bad) +
            ' <span class="num">' + fmt.int(rep.coffee_check.derived) +
            " / " + fmt.int(rep.coffee_check.counted) + "</span></span>") +
        "</div>";
    }
    (rep.warnings || []).forEach(function (w) {
      tablesH += '<div class="banner warn">' + fmt.esc(w) + "</div>";
    });
    h += '<div class="rep-scroll" style="height:408px"><div class="rep-cols">' +
      '<div class="card"><h3>' + fmt.esc(STR.cups_by_drink) + "</h3>" + bars +
      "</div>" +
      '<div class="card"><h3>' + fmt.esc(STR.yield_title) + "</h3>" + yieldHtml +
      "</div></div>" + tablesH + "</div></div>";
    root.innerHTML = h;
  }

  function card(label, valueHtml) {
    return '<div class="card"><div class="lbl">' + fmt.esc(label) + "</div>" +
      '<div class="bignum">' + valueHtml + "</div></div>";
  }

  function productTable(lines) {
    var h = '<table class="grid t-repprod"><colgroup><col><col class="c-qty">' +
      '<col class="c-money"><col class="c-money"><col class="c-money"></colgroup>' +
      '<thead><tr><th class="c-name">' + fmt.esc(STR.col_product) +
      "</th><th>" + fmt.esc(STR.col_qty) + "</th><th>" + fmt.esc(STR.revenue) +
      "</th><th>" + fmt.esc(STR.cost) + "</th><th>" + fmt.esc(STR.profit) +
      "</th></tr></thead><tbody>";
    lines.forEach(function (ln, i) {
      h += '<tr class="' + (i % 2 ? "zebra" : "") + '"><td class="c-name" title="' +
        fmt.esc(ln.name) + '">' + fmt.esc(ln.name) +
        '</td><td class="num">' + fmt.int(ln.qty_sold) +
        "</td><td>" + fmt.moneyHtml(ln.revenue) + "</td><td>" +
        fmt.moneyHtml(ln.cost) + "</td><td>" +
        fmt.moneyHtml(ln.profit, ln.profit < 0 ? "neg" : "pos") + "</td></tr>";
    });
    return h + "</tbody></table>";
  }

  function varianceTable(rep, d) {
    var rows = (rep.variance || []).filter(function (v) {
      if (dept() === "all") return true;
      for (var i = 0; i < (d.counts || []).length; i++) {
        if (d.counts[i].material_id === v.material_id) {
          return d.counts[i].department === dept();
        }
      }
      return true;
    });
    if (!rows.length) {
      return '<div class="muted">' + fmt.esc(STR.empty) + "</div>";
    }
    var h = '<table class="grid t-var"><colgroup><col><col class="c-money">' +
      '<col class="c-money"></colgroup><thead><tr><th class="c-name">' +
      fmt.esc(STR.col_material) +
      "</th><th>" + fmt.esc(STR.col_diff_base) + "</th><th>" +
      fmt.esc(STR.col_diff_egp) + "</th></tr></thead><tbody>";
    rows.forEach(function (v, i) {
      h += '<tr class="' + (i % 2 ? "zebra" : "") + '"><td class="c-name" title="' +
        fmt.esc(v.material_name || ("#" + v.material_id)) + '">' +
        fmt.esc(v.material_name || ("#" + v.material_id)) +
        '</td><td class="num ' + (v.variance_base < 0 ? "neg" : "") + '">' +
        fmt.int(v.variance_base) + '</td><td>' +
        fmt.moneyHtml(v.variance_piasters,
          v.variance_piasters < 0 ? "neg" : v.variance_piasters > 0 ? "pos" : "") +
        "</td></tr>";
    });
    return h + "</tbody></table>";
  }

  function cleanup() { /* stateless */ }

  return { show: show, cleanup: cleanup, render: render };
})();
