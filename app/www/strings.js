/* strings.js - single source is app/strings_ar.py via /api/strings.
   Plain script, no modules. Works on Firefox 115 / Chrome 109. */
var STR = {
  app_title: "مخزون المطبخ والكافتيريا",
  user_pick: "اختر المستخدم",
  business_date: "تاريخ اليوم التجاري",
  close_day: "إغلاق اليوم",
  quit_program: "إغلاق البرنامج",
  day_closed: "اليوم مغلق",
  demo_badge: "بيانات تجريبية"
};

function loadStrings() {
  var xhr = new XMLHttpRequest();
  xhr.open("GET", "/api/strings", true);
  xhr.onreadystatechange = function () {
    if (xhr.readyState === 4 && xhr.status === 200) {
      try {
        var data = JSON.parse(xhr.responseText);
        for (var k in data) { STR[k] = data[k]; }
        var t = document.getElementById("app-title");
        if (t) t.textContent = STR.app_title;
      } catch (e) { /* keep built-in fallback strings */ }
    }
  };
  try { xhr.send(); } catch (e) { /* offline fallback */ }
}
