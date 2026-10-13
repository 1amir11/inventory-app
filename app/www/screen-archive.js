/* screen-archive.js - split view: day list + read-only day detail. */
var KIOSK = KIOSK || {};

KIOSK.archiveScreen = (function () {
  var api = KIOSK.api, fmt = KIOSK.fmt, ui = KIOSK.ui;
  var days = [];
  var selDate = null;
  var filterY = 0, filterM = 0;

  function show(root) {
    document.getElementById("content").classList.remove("with-actionbar");
    document.getElementById("actionbar").classList.add("hidden");
    var now = KIOSK.dates.parse(KIOSK.app.date()) || new Date();
    filterY = now.getFullYear();
    filterM = now.getMonth() + 1;
    selDate = KIOSK.app.date();
    load(root);
  }

  function range() {
    return KIOSK.dates.monthRange(filterY, filterM);
  }

  function load(root) {
    ui.loading(root);
    var r = range();
    api.get("/api/days?from=" + r.from + "&to=" + r.to).then(function (body) {
      days = body.days || [];
      if (!days.some(function (d) { return d.date === selDate; }) && days.length) {
        selDate = days[days.length - 1].date;
      }
      render(root);
    });
  }

  function render(root) {
    var h = '<div class="screen screen-archive"><div class="arch-list">' +
      '<div class="formrow"><span>' + fmt.esc(STR.archive_month) + "</span>" +
      '<button type="button" data-mv="-1">&#9654;</button><b>' +
      fmt.esc(KIOSK.dates.monthLabel(filterY, filterM)) + "</b>" +
      '<button type="button" data-mv="1">&#9664;</button></div>' +
      '<div class="scroll">';
    if (!days.length) {
      h += '<div class="muted">' + fmt.esc(STR.empty_days) + "</div>";
    }
    days.forEach(function (d) {
      h += '<button type="button" class="dayitem' +
        (d.date === selDate ? " active" : "") + '" data-day="' + d.date + '">' +
        '<span class="num">' + fmt.esc(d.date) + "</span> " + ui.chip(d.status) +
        ' <span class="money num ' + (d.profit < 0 ? "neg" : "pos") + '">' +
        fmt.money(d.profit) + "</span></button>";
    });
    h += '</div></div><div class="arch-detail" id="arch-detail"></div></div>';
    root.innerHTML = h;
    var mv = root.querySelectorAll("[data-mv]");
    for (var i = 0; i < mv.length; i++) {
      (function (b) {
        b.onclick = function () {
          var n = parseInt(b.getAttribute("data-mv"), 10);
          filterM += n;
          if (filterM < 1) { filterM = 12; filterY--; }
          if (filterM > 12) { filterM = 1; filterY++; }
          load(root);
        };
      })(mv[i]);
    }
    var items = root.querySelectorAll("[data-day]");
    for (var k = 0; k < items.length; k++) {
      (function (b) {
        b.onclick = function () {
          selDate = b.getAttribute("data-day");
          render(root);
        };
      })(items[k]);
    }
    renderDetail(root);
  }

  function renderDetail(root) {
    var box = root.querySelector("#arch-detail");
    if (!selDate) { ui.empty(box); return; }
    ui.loading(box);
    api.get("/api/day?date=" + selDate).then(function (d) {
      var h = '<div class="arch-nav">' +
        '<button type="button" data-step="-1">' + fmt.esc(STR.archive_prev) + "</button>" +
        "<b>" + fmt.esc(KIOSK.dates.label(selDate)) + "</b> " + ui.chip(d.status) +
        '<button type="button" data-step="1">' + fmt.esc(STR.archive_next) + "</button>" +
        '<span style="flex:1"></span>' +
        '<button type="button" id="arch-rep">' +
        fmt.esc(STR.archive_open_report) + "</button></div>";
      h += '<div class="scroll">' + detailHtml(d) + "</div>";
      box.innerHTML = h;
      var steps = box.querySelectorAll("[data-step]");
      for (var i = 0; i < steps.length; i++) {
        (function (b) {
          b.onclick = function () {
            selDate = KIOSK.dates.addDays(selDate,
              parseInt(b.getAttribute("data-step"), 10));
            var r = range();
            if (selDate < r.from || selDate > r.to) {
              var p = KIOSK.dates.parse(selDate);
              filterY = p.getFullYear(); filterM = p.getMonth() + 1;
              load(root);
            } else { render(root); }
          };
        })(steps[i]);
      }
      document.getElementById("arch-rep").onclick = function () {
        KIOSK.app.setDate(selDate);
        KIOSK.app.go("report");
      };
    });
  }

  /* Read-only rendering of the day exactly as recorded. */
  function detailHtml(d) {
    var h = '<table class="grid t-arch"><colgroup><col><col class="c-n">' +
      '<col class="c-n"><col class="c-n"><col class="c-n"></colgroup>' +
      '<thead><tr><th class="c-name">' + fmt.esc(STR.col_material) +
      "</th><th>" + fmt.esc(STR.col_opening) + "</th><th>" +
      fmt.esc(STR.col_received) + "</th><th>" + fmt.esc(STR.col_closing) +
      "</th><th>" + fmt.esc(STR.col_consumed) + "</th></tr></thead><tbody>";
    var list = (d.counts || []).filter(function (c) {
      var f = KIOSK.app.dept();
      return f === "all" || c.department === f;
    });
    list.forEach(function (c, i) {
      var cnt = c.count || {};
      var open = (cnt.opening_base !== undefined && cnt.opening_base !== null)
        ? cnt.opening_base : c.opening_default_base;
      var close = (cnt.closing_base !== undefined && cnt.closing_base !== null)
        ? cnt.closing_base : null;
      h += '<tr class="' + (i % 2 ? "zebra" : "") + '">' +
        '<td class="c-name" title="' + fmt.esc(c.name) + '">' + fmt.esc(c.name) + "</td>" +
        '<td class="num">' + fmt.int(open) + '</td><td class="num">' +
        fmt.int(c.received_base) + '</td><td class="num">' +
        (close === null ? "-" : fmt.int(close)) + '</td><td class="num"><b>' +
        (close === null ? "-" : fmt.int(open + c.received_base - close)) +
        "</b></td></tr>";
    });
    h += "</tbody></table>";
    if (d.report) {
      h += '<div class="card" style="margin-top:8px"><div>' +
        fmt.esc(STR.revenue) + ": " + fmt.moneyHtml(d.report.total_revenue) +
        "</div><div>" + fmt.esc(STR.cost) + ": " +
        fmt.moneyHtml(d.report.total_cost) + "</div><div>" +
        fmt.esc(STR.profit) + ": " +
        fmt.moneyHtml(d.report.total_profit,
          d.report.total_profit < 0 ? "neg" : "pos") + "</div></div>";
    }
    return h;
  }

  function cleanup() { days = []; selDate = null; }

  return { show: show, cleanup: cleanup };
})();
