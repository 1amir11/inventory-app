/* ui.js - toast, in-page dialog, chips, list states. No alert/confirm. */
var KIOSK = KIOSK || {};

KIOSK.ui = (function () {
  var toastTimer = null;

  function $(id) { return document.getElementById(id); }

  function toast(msg, isErr) {
    var t = $("toast");
    t.textContent = msg;
    t.className = isErr ? "err" : "";
    t.classList.remove("hidden");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.add("hidden"); }, 4000);
  }

  /* In-page dialog. bodyHtml is app-escaped HTML. Returns nothing; buttons
     configured via opts {okText, okClass, onOk, cancelText, showCancel}. */
  function dialog(title, bodyHtml, opts) {
    opts = opts || {};
    var back = $("dlg-back"), dlg = $("dlg");
    dlg.innerHTML = "<h3>" + KIOSK.fmt.esc(title) + "</h3><div>" + bodyHtml +
      "</div>";
    var bar = document.createElement("div");
    bar.className = "dlg-actions";
    if (opts.showCancel !== false) {
      var c = document.createElement("button");
      c.type = "button";
      c.textContent = opts.cancelText || STR.cancel;
      c.onclick = close;
      bar.appendChild(c);
    }
    var ok = document.createElement("button");
    ok.type = "button";
    ok.textContent = opts.okText || STR.confirm;
    ok.className = opts.okClass || "btn-primary";
    ok.onclick = function () { if (opts.onOk) opts.onOk(); };
    bar.appendChild(ok);
    dlg.appendChild(bar);
    back.classList.remove("hidden");
    var first = dlg.querySelector("textarea, input, button");
    if (first) { try { first.focus(); } catch (e) { /* noop */ } }
  }

  function close() { $("dlg-back").classList.add("hidden"); }

  function reasonDialog(title, hint, okText, onReason) {
    var body = "<div class='muted small'>" + KIOSK.fmt.esc(hint) + "</div>" +
      '<textarea id="dlg-reason" rows="3" style="width:100%"></textarea>' +
      '<div class="inline-err" id="dlg-reason-err"></div>';
    dialog(title, body, {
      okText: okText || STR.confirm,
      onOk: function () {
        var r = $("dlg-reason").value.trim();
        if (!r) {
          $("dlg-reason-err").textContent = STR.reason_required;
          return;
        }
        close();
        onReason(r);
      }
    });
  }

  function chip(status) {
    if (status === "closed") {
      return '<span class="chip closed">' + KIOSK.fmt.esc(STR.lock) + " " +
        KIOSK.fmt.esc(STR.status_closed) + "</span>";
    }
    if (status === "open") {
      return '<span class="chip open">' + KIOSK.fmt.esc(STR.status_open) + "</span>";
    }
    return '<span class="chip new">' + KIOSK.fmt.esc(STR.status_new) + "</span>";
  }

  function loading(el) {
    el.innerHTML = '<div class="muted">' + KIOSK.fmt.esc(STR.loading) + "</div>";
  }

  function empty(el, msg) {
    el.innerHTML = '<div class="muted">' +
      KIOSK.fmt.esc(msg || STR.empty) + "</div>";
  }

  return {
    toast: toast, dialog: dialog, close: close, reasonDialog: reasonDialog,
    chip: chip, loading: loading, empty: empty
  };
})();
