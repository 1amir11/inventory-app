// tests/ui_check.js - automated frontend layout check.
// Loads every screen at exactly 1024x650 with demo data + a long-name case
// and asserts: no clipped text, exact control heights, 120px header, no page
// scroll, uniform sibling buttons. Prints every violation, exits 1 if any.
//
// Needs: node, headless Chrome (CHROME_BIN or the default install path),
// python on PATH (to seed the demo DB and spawn the app server).
// Usage:  node tests/ui_check.js
// Screenshots land in docs/screenshots/.

var fs = require("fs");
var os = require("os");
var path = require("path");
var cp = require("child_process");
var http = require("http");

var ROOT = path.dirname(__dirname);
var APP = path.join(ROOT, "app");
var SHOTS = path.join(ROOT, "docs", "screenshots");
var TMP = fs.mkdtempSync(path.join(os.tmpdir(), "kitchen_uicheck_"));
var PORT = 8001;

function sh(cmd, args, opts) {
  var r = cp.spawnSync(cmd, args, opts || { encoding: "utf8" });
  if (r.status !== 0) {
    throw new Error(cmd + " failed: " + (r.stderr || r.stdout || r.error));
  }
  return r.stdout;
}

function ensureDemo() {
  var demo = path.join(APP, "data_demo", "kitchen.db");
  if (!fs.existsSync(demo)) {
    console.log("seeding demo data...");
    sh("python", [path.join(APP, "seed_demo.py")], { cwd: APP });
  }
  var dest = path.join(TMP, "kitchen.db");
  fs.copyFileSync(demo, dest);
  var fix = "import sqlite3\n" +
    "c = sqlite3.connect(r'''" + dest + "''')\n" +
    "c.execute(\"INSERT INTO materials (name, department, base_unit,\" +\n" +
    "  \" created_by, created_at)\" +\n" +
    "  \" VALUES ('LONG_MAT','kitchen','g',1,'t')\")\n" +
    "mid = c.execute('SELECT last_insert_rowid()').fetchone()[0]\n" +
    "c.execute('INSERT INTO count_units (material_id, unit_name,' +\n" +
    "  ' factor_to_base, is_base_unit, created_by, created_at)' +\n" +
    "  ' VALUES (%d,\\'g\\',1,1,1,\\'t\\')' % mid)\n" +
    "c.execute('INSERT INTO count_units (material_id, unit_name,' +\n" +
    "  ' factor_to_base, created_by, created_at)' +\n" +
    "  ' VALUES (%d,\\'bulk\\',100,1,\\'t\\')' % mid)\n" +
    "bulk = c.execute('SELECT id FROM count_units' +\n" +
    "  ' WHERE material_id=%d AND is_base_unit=0' % mid).fetchone()[0]\n" +
    "c.execute('INSERT INTO material_costs (material_id, count_unit_id,' +\n" +
    "  ' price_piasters, effective_date, created_by, created_at)' +\n" +
    "  ' VALUES (%d,%d,1500,\\'2026-01-01\\',1,\\'t\\')'\n" +
    "  % (mid, bulk))\n" +
    "c.execute(\"INSERT INTO products (name, department, sold_source,\" +\n" +
    "  \" created_by, created_at)\" +\n" +
    "  \" VALUES ('LONG_DISH','kitchen','manual',1,'t')\")\n" +
    "pid = c.execute('SELECT last_insert_rowid()').fetchone()[0]\n" +
    "c.execute('INSERT INTO product_prices (product_id, price_piasters,' +\n" +
    "  ' effective_date, created_by, created_at)' +\n" +
    "  ' VALUES (%d,6000,\\'2026-01-01\\',1,\\'t\\')' % pid)\n" +
    "c.execute('INSERT INTO recipe_lines (product_id, material_id,' +\n" +
    "  ' qty_base, effective_date, created_by, created_at)' +\n" +
    "  ' VALUES (%d,%d,250,\\'2026-01-01\\',1,\\'t\\')' % (pid, mid))\n" +
    "c.execute(\"INSERT OR IGNORE INTO business_days\" +\n" +
    "  \" (business_date, status, created_at)\" +\n" +
    "  \" VALUES ('2026-10-13','open','t')\")\n" +
    "bu = c.execute('SELECT id FROM count_units' +\n" +
    "  ' WHERE material_id=%d AND is_base_unit=1' % mid).fetchone()[0]\n" +
    "c.execute('INSERT INTO stock_counts (business_date, material_id,' +\n" +
    "  ' opening_base, opening_qty_entered, opening_unit_id,' +\n" +
    "  ' closing_base, closing_qty_entered, closing_unit_id,' +\n" +
    "  ' created_by, created_at) VALUES' +\n" +
    "  ' (\\'2026-10-13\\',%d,1000,1000.0,%d,700,700.0,%d,1,\\'t\\')'\n" +
    "  % (mid, bu, bu))\n" +
    "c.execute('INSERT INTO product_sales (business_date, product_id,' +\n" +
    "  ' qty_sold, created_by, created_at)' +\n" +
    "  ' VALUES (\\'2026-10-13\\',%d,2,1,\\'t\\')' % pid)\n" +
    "c.commit()\n" +
    "print('fixture ok')\n";
  var py = fix.split("LONG_MAT").join(
    "خامة تجريبية طويلة الاسم جدا لاختبار التفاف النص في الجداول").split(
    "LONG_DISH").join("طبق دجاج مشوي بالأعشاب مع الأرز والخضار");
  var f = path.join(TMP, "fixture.py");
  fs.writeFileSync(f, py, "utf8");
  sh("python", [f]);
}

function waitForServer(next) {
  var tries = 0;
  (function poll() {
    tries++;
    var req = http.get(
      { host: "127.0.0.1", port: PORT, path: "/api/session", timeout: 2000 },
      function (res) {
        res.resume();
        if (res.statusCode === 200) return next();
        if (tries > 40) throw new Error("server never came up");
        setTimeout(poll, 500);
      });
    req.on("error", function () {
      if (tries > 40) throw new Error("server never came up");
      setTimeout(poll, 500);
    });
  })();
}

function chromeBin() {
  if (process.env.CHROME_BIN && fs.existsSync(process.env.CHROME_BIN)) {
    return process.env.CHROME_BIN;
  }
  var def = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
  if (fs.existsSync(def)) return def;
  throw new Error("Chrome not found (set CHROME_BIN)");
}

var WIN_W = parseInt(process.env.UI_W || "1040", 10);
var WIN_H = parseInt(process.env.UI_H || "745", 10);

function shot(bin, url, png, dump) {
  var size = WIN_W + "," + WIN_H;
  var args = ["--headless", "--disable-gpu", "--no-sandbox",
    "--hide-scrollbars", "--window-size=" + size,
    "--virtual-time-budget=8000", "--dump-dom", url];
  var r = cp.spawnSync(bin, args, { encoding: "utf8", timeout: 120000 });
  if (r.status !== 0) throw new Error("chrome dump failed: " + r.stderr);
  fs.writeFileSync(dump, r.stdout, "utf8");
  var r2 = cp.spawnSync(bin,
    ["--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
      "--screenshot=" + png, "--window-size=" + WIN_W + "," + WIN_H,
      "--virtual-time-budget=8000", url],
    { encoding: "utf8", timeout: 120000 });
  if (r2.status !== 0 || !fs.existsSync(png)) {
    throw new Error("chrome screenshot failed: " + (r2.stderr || "no file"));
  }
}

function resultOf(dump) {
  var html = fs.readFileSync(dump, "utf8");
  var m = /UICHECK-JSON:(\{.*?\})<\/pre>/.exec(html);
  if (!m) throw new Error("no uicheck result in " + dump);
  return JSON.parse(m[1]);
}

var CASES = [
  ["close-closed", "close", "2026-10-12"],
  ["close-open", "close", "2026-10-13"],
  ["report-closed", "report", "2026-10-12"],
  ["report-open", "report", "2026-10-13"],
  ["archive", "archive", "2026-10-12"],
  ["products", "products", "2026-10-12"],
  ["backup", "backup", "2026-10-12"]
];

function main() {
  ensureDemo();
  if (!fs.existsSync(SHOTS)) fs.mkdirSync(SHOTS, { recursive: true });
  var server = cp.spawn("python", [path.join(APP, "server.py"),
    "--data-dir", TMP], { cwd: APP, stdio: "ignore" });
  var failed = false;
  function done(code) {
    try { process.kill(server.pid); } catch (e) { /* gone */ }
    process.exit(code);
  }
  process.on("uncaughtException", function (e) {
    console.error("FATAL " + e.message);
    done(2);
  });
  waitForServer(function () {
    var bin = chromeBin();
    var all = [];
    CASES.forEach(function (c) {
      var name = c[0], tab = c[1], d = c[2];
      var url = "http://127.0.0.1:" + PORT +
        "/?uicheck=1&date=" + d + "#/" + tab;
      var dump = path.join(TMP, name + ".html");
      var png = path.join(TMP, name + ".png");
      try {
        shot(bin, url, png, dump);
        fs.copyFileSync(png, path.join(SHOTS, name + ".png"));
        var res = resultOf(dump);
        res.caseName = name;
        all.push(res);
      } catch (e) {
        failed = true;
        console.error("CASE-ERROR " + name + ": " + e.message);
      }
    });
    console.log("screen | kind | element | detail");
    console.log("-------|------|---------|-------");
    all.forEach(function (res) {
      res.violations.forEach(function (v) {
        failed = true;
        console.log(res.caseName + " | " + v.kind + " | " + v.el + " | " +
          v.detail);
      });
      if (!res.violations.length) {
        console.log(res.caseName + " | ok | viewport " +
          res.viewport.w + "x" + res.viewport.h + " doc " +
          res.doc.sw + "x" + res.doc.sh + " | -");
      }
    });
    console.log(failed ? "UI-CHECK: VIOLATIONS FOUND" : "UI-CHECK: CLEAN");
    done(failed ? 1 : 0);
  });
}

main();
