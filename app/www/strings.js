/* strings.js - THE ONE file with all Arabic UI text.
   No Arabic may be hardcoded in HTML or other JS files: they reference
   STR.* keys only. Western digits (0-9) are always used for numbers.
   Plain script, no modules. Loaded first. */
var STR = {
  app_title: "مخزون المطبخ والكافتيريا",
  user: "المستخدم",
  user_pick: "اختر المستخدم",
  quit_program: "إنهاء البرنامج",
  quit_confirm_title: "إنهاء البرنامج",
  quit_confirm_text: "سيتم إغلاق البرنامج الآن.",
  quit_confirm_title: "إنهاء البرنامج",
  quit_confirm_text: "سيتم إغلاق البرنامج الآن.",
  dept_all: "الكل",
  dept_kitchen: "مطبخ",
  dept_cafeteria: "كافتيريا",
  day_prev: "اليوم السابق",
  day_next: "اليوم التالي",
  pick_date: "اختر التاريخ",
  status_open: "مفتوح",
  status_closed: "مغلق",
  status_new: "جديد",
  tab_close: "إغلاق اليوم",
  tab_report: "تقرير اليوم",
  tab_archive: "الأرشيف",
  tab_products: "الأصناف والأسعار",
  tab_backup: "نسخ احتياطي",

  loading: "جاري التحميل…",
  empty: "لا توجد بيانات",
  empty_materials: "لا توجد أصناف. أضف الأصناف من شاشة الأصناف والأسعار.",
  empty_days: "لا توجد أيام في هذه الفترة.",
  save: "حفظ",
  save_draft: "حفظ مسودة",
  saved: "تم الحفظ",
  saving: "جاري الحفظ…",
  cancel: "إلغاء",
  confirm: "تأكيد",
  back: "رجوع",
  close: "إغلاق",
  add: "إضافة",
  edit: "تعديل",
  deactivate: "إيقاف",
  activate: "تفعيل",
  rename: "إعادة تسمية",

  col_material: "الصنف",
  col_opening: "افتتاحي",
  col_received: "وارد",
  col_closing: "إغلاق",
  col_consumed: "مستهلك",
  add_receipt: "+ وارد",
  receipt_qty: "الكمية الواردة",
  opening_default_note: "من إغلاق الأمس",
  warn_spike: "أعلى من 10 أضعاف متوسط 14 يوما",
  warn_over_close: "الإغلاق أكبر من الافتتاحي + الوارد",
  err_bad_number: "رقم غير صالح",
  err_bad_date: "التاريخ غير صالح. الصيغة YYYY-MM-DD",
  err_unknown: "خطأ غير معروف",
  reason_title: "يلزم سبب مكتوب",
  reason_hint: "اكتب سبب التعديل هنا",
  reason_required: "السبب مطلوب",
  err_server_prefix: "خطأ: ",

  card_cups: "الأكواب",
  cups_consumed: "أكواب مستهلكة",
  coffee_derived: "أكواب قهوة محسوبة",
  coffee_counted: "عدّ يدوي لأكواب السادة",
  coffee_counted_hint: "اختياري: للمطابقة فقط",
  card_dishes: "الأطباق المباعة",
  sold_qty: "الكمية المباعة",
  card_summary: "ملخص اليوم",
  revenue: "إيراد",
  cost: "تكلفة",
  profit: "ربح",
  total_cups: "إجمالي الأكواب",
  reconcile_ok: "الأكواب متطابقة",
  reconcile_diff: "فرق الأكواب",
  close_day: "إغلاق اليوم",
  close_review_title: "مراجعة قبل الإغلاق",
  close_missing: "أصناف بلا جرد إغلاق",
  closed_banner: "يوم مغلق - للعرض فقط",
  add_adjust: "إضافة تصحيح",
  adjust_title: "تصحيح يوم مغلق",
  adjust_delta: "الفرق (موجب أو سالب)",
  adjust_hint: "مثال: 2- تعني عجز قطعتين",

  cups_by_drink: "الأكواب حسب المشروب",
  yield_title: "عائد القهوة",
  yield_per_bag: "كوب في الكيس",
  grams_per_cup: "جرام للكوب",
  confidence: "الثقة",
  conf_high: "عالية",
  conf_medium: "متوسطة",
  conf_low: "منخفضة",
  conf_none: "لا توجد",
  yield_based_on: "بناء على",
  yield_days: "يوم",
  yield_cups: "كوب",
  yield_estimate_note: "تقدير مبدئي: لا يوجد سجل كاف بعد",
  col_product: "المنتج",
  col_qty: "الكمية",
  variance_title: "فروق الأطباق",
  col_material: "الخامة",
  col_actual: "فعلي",
  col_expected: "متوقع",
  col_diff_base: "الفرق",
  col_diff_egp: "الفرق بالجنيه",
  coffee_check_ok: "العد اليدوي مطابق",
  coffee_check_bad: "العد اليدوي مختلف",

  archive_month: "الشهر",
  archive_open: "فتح",
  archive_open_report: "عرض بتخطيط التقرير",
  archive_prev: "اليوم السابق",
  archive_next: "اليوم التالي",

  prod_materials: "الخامات",
  prod_products: "المنتجات",
  mat_new: "خامة جديدة",
  mat_name: "اسم الخامة",
  base_unit: "الوحدة الأساسية",
  unit_g: "جرام",
  unit_ml: "مل",
  unit_piece: "قطعة",
  is_cup: "كوب تغليف",
  count_units: "وحدات العد",
  unit_name_ph: "مثال: كرتونة",
  factor_ph: "المعامل",
  cost_title: "التكلفة",
  cost_egp_ph: "السعر بالجنيه",
  effective_date: "ساري من",
  prod_new: "منتج جديد",
  prod_name: "اسم المنتج",
  sold_source: "طريقة حساب المباع",
  src_sachet: "من الخامة",
  src_sachet_hint: "كل ظرف يساوي كوبا واحدا، مثل الشاي.",
  src_remainder: "الباقي من الأكواب",
  src_remainder_hint: "أكواب القهوة = الأكواب المستهلكة ناقص باقي المشروبات.",
  src_manual: "يدوي",
  src_manual_hint: "عدد الأطباق المباعة يدخل يدويا آخر اليوم.",
  recipe_title: "المقادير",
  recipe_qty_ph: "الكمية",
  price_title: "سعر البيع",
  price_egp_ph: "السعر بالجنيه",
  uses_cup: "يستخدم كوب تغليف",
  source_material: "خامة المصدر",
  coffee_material: "خامة البن",
  recipe_qty_cup: "كمية الكوب",
  inactive_tag: "موقوف",
  today_or_later: "اليوم أو بعده فقط",

  backup_now: "نسخ احتياطي الآن",
  backup_list: "النسخ المحفوظة",
  col_size: "الحجم",
  col_time: "الوقت",
  csv_title: "تصدير CSV",
  csv_from: "من",
  csv_to: "إلى",
  csv_go: "تصدير",
  backup_done: "تم إنشاء النسخة",

  setup_title: "إعداد أول تشغيل",
  setup_hint: "قاعدة البيانات فارغة. أنشئ المستخدمين أولا.",
  setup_user_ph: "اسم المستخدم",
  setup_add_user: "إضافة مستخدم",
  setup_next: "انتقل لإدخال الأصناف من شاشة الأصناف والأسعار",
  demo_badge: "بيانات تجريبية",

  egp: "ج.م",
  lock: "🔒",
  check: "✓",
  warn_icon: "!",
  weekdays: ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"],
  months: ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
};

/* Merge server-provided strings (single source stays strings_ar.py). */
(function () {
  function merge() {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open("GET", "/api/strings", true);
      xhr.onreadystatechange = function () {
        if (xhr.readyState === 4 && xhr.status === 200) {
          try {
            var data = JSON.parse(xhr.responseText);
            for (var k in data) {
              if (typeof data[k] === "string") STR[k] = data[k];
            }
          } catch (e) { /* keep local strings */ }
        }
      };
      xhr.send();
    } catch (e) { /* offline: keep local strings */ }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", merge);
  } else { merge(); }
})();
