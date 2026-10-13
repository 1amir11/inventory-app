/* api.js - fetch wrapper on the one global KIOSK namespace. No modules. */
var KIOSK = KIOSK || {};

KIOSK.api = (function () {
  function get(path) {
    return fetch(path, { cache: "no-store" }).then(function (resp) {
      var ct = resp.headers.get("Content-Type") || "";
      if (ct.indexOf("json") >= 0) return resp.json();
      return resp.text();
    });
  }

  function post(path, payload) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    }).then(function (resp) {
      return resp.json().then(function (body) {
        body._status = resp.status;
        return body;
      });
    });
  }

  function failToast(body) {
    var msg = (body && (body.message || body.error)) || STR.err_unknown;
    KIOSK.ui.toast(STR.err_server_prefix + msg, true);
  }

  return { get: get, post: post, failToast: failToast };
})();
