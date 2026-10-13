/* dates.js - Gregorian dates with Arabic weekday/month names from STR.
   The OS clock may be wrong: the date is always chosen explicitly. */
var KIOSK = KIOSK || {};

KIOSK.dates = (function () {
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function toStr(y, m, d) { return y + "-" + pad(m) + "-" + pad(d); }

  function parse(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    if (d.getFullYear() !== +m[1] || d.getMonth() !== +m[2] - 1 ||
        d.getDate() !== +m[3]) return null;
    return d;
  }

  function todayLocal() {
    var d = new Date();
    return toStr(d.getFullYear(), d.getMonth() + 1, d.getDate());
  }

  function addDays(s, n) {
    var d = parse(s);
    if (!d) return s;
    d.setDate(d.getDate() + n);
    return toStr(d.getFullYear(), d.getMonth() + 1, d.getDate());
  }

  /* Weekday + day + month + year label, Western digits. */
  function label(s) {
    var d = parse(s);
    if (!d) return s;
    return STR.weekdays[d.getDay()] + " " + d.getDate() + " " +
      STR.months[d.getMonth()] + " " + d.getFullYear();
  }

  function monthLabel(y, m) { return STR.months[m - 1] + " " + y; }

  function monthRange(y, m) {
    var last = new Date(y, m, 0).getDate();
    return { from: toStr(y, m, 1), to: toStr(y, m, last) };
  }

  /* Builds a month calendar popup into rootEl. onPick(iso) on day click. */
  function calendar(rootEl, initial, onPick, onClose) {
    var cur = parse(initial) || parse(todayLocal());
    var y = cur.getFullYear(), m = cur.getMonth() + 1;
    var sel = initial;

    function render() {
      var first = new Date(y, m - 1, 1).getDay();
      var days = new Date(y, m, 0).getDate();
      var h = '<div class="cal-head"><button type="button" data-c="prev">&#9654;</button>' +
        "<b>" + KIOSK.fmt.esc(monthLabel(y, m)) + "</b>" +
        '<button type="button" data-c="next">&#9664;</button></div>';
      h += "<table><tr>";
      /* Grid starts on Sunday to match Date.getDay(). */
      for (var i = 0; i < 7; i++) {
        h += "<th>" + KIOSK.fmt.esc(STR.weekdays[i]) + "</th>";
      }
      h += "</tr><tr>";
      var cell = 0;
      for (var b = 0; b < first; b++) { h += "<td></td>"; cell++; }
      for (var d = 1; d <= days; d++) {
        var iso = toStr(y, m, d);
        h += '<td><button type="button" data-d="' + iso + '"' +
          (iso === sel ? ' class="sel"' : "") + ">" + d + "</button></td>";
        cell++;
        if (cell % 7 === 0 && d < days) h += "</tr><tr>";
      }
      h += "</tr></table>";
      rootEl.innerHTML = '<div class="cal">' + h + "</div>";
      var btns = rootEl.querySelectorAll("button");
      for (var k = 0; k < btns.length; k++) {
        (function (b) {
          b.onclick = function () {
            if (b.getAttribute("data-d")) { onPick(b.getAttribute("data-d")); return; }
            if (b.getAttribute("data-c") === "prev") {
              m--; if (m < 1) { m = 12; y--; }
            } else {
              m++; if (m > 12) { m = 1; y++; }
            }
            render();
          };
        })(btns[k]);
      }
    }
    render();
  }

  return {
    parse: parse, todayLocal: todayLocal, addDays: addDays, label: label,
    monthLabel: monthLabel, monthRange: monthRange, calendar: calendar
  };
})();
