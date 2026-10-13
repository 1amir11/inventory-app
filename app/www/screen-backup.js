/* screen-backup.js - manual backup, backup list, CSV export. */
var KIOSK = KIOSK || {};

KIOSK.backupScreen = (function () {
  var api = KIOSK.api, fmt = KIOSK.fmt, ui = KIOSK.ui;

  function show(root) {
    document.getElementById("content").classList.remove("with-actionbar");
    document.getElementById("actionbar").classList.add("hidden");
    load(root);
  }

  function load(root) {
    ui.loading(root);
    api.get("/api/backups").then(function (body) {
      render(root, body.backups || []);
    });
  }

  function fmtSize(b) {
    if (b >= 1048576) {
      return (Math.round(b / 10485.76) / 100) + " MB";
    }
    return (Math.round(b / 10.24) / 100) + " KB";
  }

  function fmtTime(ts) {
    if (!ts) return "-";
    var d = new Date(ts * 1000);
    function p(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) +
      " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function render(root, backups) {
    var h = '<div class="screen screen-backup"><div class="scroll">' +
      '<div class="card"><button type="button" id="bk-now" class="btn-primary">' +
      fmt.esc(STR.backup_now) + "</button></div>" +
      '<div class="card"><h3>' + fmt.esc(STR.backup_list) + "</h3>" +
      '<table class="grid"><thead><tr><th>' + fmt.esc(STR.col_time) +
      "</th><th>" + fmt.esc(STR.col_size) + "</th></tr></thead><tbody>";
    if (!backups.length) {
      h += '<tr><td colspan="2" class="muted">' + fmt.esc(STR.empty) + "</td></tr>";
    }
    backups.slice().reverse().forEach(function (b, i) {
      h += '<tr class="' + (i % 2 ? "zebra" : "") + '"><td class="num">' +
        fmt.esc(fmtTime(b.mtime)) + '</td><td class="num">' +
        fmt.esc(fmtSize(b.size_bytes || 0)) + "</td></tr>";
    });
    h += "</tbody></table></div>" +
      '<div class="card"><h3>' + fmt.esc(STR.csv_title) + "</h3>" +
      '<div class="formrow"><span>' + fmt.esc(STR.csv_from) + "</span>" +
      '<input type="text" inputmode="numeric" id="csv-from" maxlength="10" placeholder="YYYY-MM-DD" class="num" value="' + fmt.esc(KIOSK.app.date()) + '">' +
      "<span>" + fmt.esc(STR.csv_to) + "</span>" +
      '<input type="text" inputmode="numeric" id="csv-to" maxlength="10" placeholder="YYYY-MM-DD" class="num" value="' + fmt.esc(KIOSK.app.date()) + '">' +
      '<a class="btn btn-primary" id="csv-go" href="#">' + fmt.esc(STR.csv_go) +
      "</a></div><div class='inline-err' id='csv-err'></div></div></div></div>";
    root.innerHTML = h;
    document.getElementById("bk-now").onclick = function () {
      api.post("/api/backup", { user_id: KIOSK.app.userId() }).then(
        function (body) {
          if (body._status !== 200) { api.failToast(body); return; }
          ui.toast(STR.backup_done);
          load(root);
        });
    };
    function csvHref() {
      var f = document.getElementById("csv-from").value.trim();
      var t = document.getElementById("csv-to").value.trim();
      var err = document.getElementById("csv-err");
      if (!KIOSK.dates.parse(f) || !KIOSK.dates.parse(t)) {
        err.textContent = STR.err_bad_date;
        document.getElementById("csv-go").href = "#";
        return;
      }
      err.textContent = "";
      document.getElementById("csv-go").href =
        "/api/export.csv?from=" + encodeURIComponent(f) +
        "&to=" + encodeURIComponent(t);
    }
    document.getElementById("csv-from").onchange = csvHref;
    document.getElementById("csv-to").onchange = csvHref;
    csvHref();
  }

  function cleanup() { /* stateless */ }

  return { show: show, cleanup: cleanup };
})();
