/* format.js - number parsing and money formatting. Western digits always. */
var KIOSK = KIOSK || {};

KIOSK.fmt = (function () {
  /* Eastern Arabic digits (066x) AND Extended/Persian digits (06Fx), as
     escapes to keep sources ASCII. Both keyboards appear in the wild. */
  var AR_DIGITS = "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669" +
    "\u06F0\u06F1\u06F2\u06F3\u06F4\u06F5\u06F6\u06F7\u06F8\u06F9";
  var BASE_LABEL = { g: "unit_g", ml: "unit_ml", piece: "unit_piece" };

  /* Parse user-typed numbers: Arabic-Indic digits, Arabic decimal/thousands
     separators, comma/dot, spaces. Returns {ok, value} - never NaN. */
  function parseQty(text) {
    if (text === null || text === undefined) return { ok: false, value: 0 };
    var s = String(text).replace(/[\s ]/g, "");
    if (!s) return { ok: false, value: 0 };
    var out = "";
    for (var i = 0; i < s.length; i++) {
      var ch = s[i];
      var ar = AR_DIGITS.indexOf(ch);
      if (ar >= 0) { out += String(ar % 10); continue; }
      if (ch === "\u066B") { out += "."; continue; }
      if (ch === "\u066C" || ch === ",") { continue; }
      out += ch;
    }
    if (!/^[+-]?(\d+(\.\d*)?|\.\d+)$/.test(out)) {
      return { ok: false, value: 0 };
    }
    var v = parseFloat(out);
    if (!isFinite(v) || v < 0 || v > 100000) return { ok: false, value: 0 };
    return { ok: true, value: v };
  }

  function group(n) {
    var parts = String(n).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return parts.join(".");
  }

  /* Money: "1,234.50" plus the caller adds the EGP label. */
  function money(piasters) {
    var neg = piasters < 0;
    var a = Math.abs(Math.round(piasters));
    var s = Math.floor(a / 100) + "." + ("0" + (a % 100)).slice(-2);
    return (neg ? "-" : "") + group(s);
  }

  function moneyHtml(piasters, cls) {
    var c = cls || (piasters < 0 ? "neg" : "");
    return '<span class="money num ' + c + '">' + money(piasters) +
      ' <span class="muted small">' + esc(STR.egp) + "</span></span>";
  }

  function int(n) {
    return group(Math.round(n));
  }

  function baseLabel(base) {
    return STR[BASE_LABEL[base] || "unit_piece"];
  }

  /* Equivalent display: 2.5 carton = 2500 gram. factor>0. */
  function equiv(qty, unitName, factor, base) {
    var b = Math.round(qty * factor);
    return int(b) + " " + esc(baseLabel(base));
  }

  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  return {
    parseQty: parseQty, money: money, moneyHtml: moneyHtml, int: int,
    equiv: equiv, esc: esc, baseLabel: baseLabel
  };
})();
