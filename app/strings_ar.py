# strings_ar.py - ALL Arabic UI strings in ONE file.
#
# Code, table/column names and comments stay in English; every sentence the
# user sees lives here so it is easy to review and edit. UTF-8 everywhere.
# Standard library only, Python 3.8 compatible.

STRINGS = {
    "app_title": "مخزون المطبخ والكافتيريا",
    "already_running": "البرنامج يعمل بالفعل. تم فتح الصفحة الموجودة.",
    "port_busy": "المنفذ 8001 مشغول ببرنامج آخر. أغلق البرنامج الآخر ثم حاول مجددا.",
    "server_failed": "تعذر تشغيل الخادم. راجع ملف kitchen_launcher.log.",
    "no_browser": "لم يتم العثور على متصفح مناسب. ضع نسخة فايرفوكس المحمولة في مجلد runtime\\browser.",
    "bundled_browser_missing": "مجلد المتصفح المحمول موجود لكن ملف التشغيل ناقص. أعد نسخ runtime\\browser كاملا.",
    "user_pick": "اختر المستخدم",
    "business_date": "تاريخ اليوم التجاري",
    "setup_title": "إعداد أول تشغيل",
    "setup_hint": "قاعدة البيانات فارغة. أنشئ المستخدمين ثم المواد والمنتجات.",
    "day_closed": "اليوم مغلق",
    "close_day": "إغلاق اليوم",
    "quit_program": "إغلاق البرنامج",
    "error_generic": "حدث خطأ غير متوقع. حاول مجددا.",
    "login_required": "اختر المستخدم أولا.",
    "demo_badge": "بيانات تجريبية",
    "err_user_required": "اختر المستخدم أولا.",
    "err_day_closed": "اليوم مغلق. التعديل يكون بقيد تصحيح مع سبب.",
    "err_reason_required": "يلزم سبب مكتوب.",
    "err_opening_differs": "الافتتاحي مختلف عن إغلاق الأمس. اكتب السبب للتأكيد.",
    "err_negative_close": "الإغلاق أكبر من الافتتاحي والوارد. اكتب السبب للتأكيد.",
    "err_not_found": "العنصر غير موجود.",
    "err_invalid": "بيانات غير صالحة.",
    "err_missing_close": "هناك أصناف بلا جرد إغلاق.",
    "err_manual_only": "الكمية المباعة تدخل يدويا للأطباق فقط.",
    "err_adjust_open": "اليوم ما زال مفتوحا. عدّل الجرد مباشرة بدلا من قيد التصحيح.",
    "err_bad_date": "التاريخ غير صالح. الصيغة المطلوبة YYYY-MM-DD.",
    "ok_saved": "تم الحفظ.",
    "ok_closed": "تم إغلاق اليوم.",
    "warn_spike": "تحذير: الكمية أكبر من 10 أضعاف متوسط 14 يوما.",
    "warn_cup_diff": "فرق في مطابقة الأكواب.",
    "warn_coffee_check": "العد اليدوي للقهوة مختلف عن المحسوب.",
}

# Mirror for the browser (served as JSON by /api/strings).
JS_KEYS = ("app_title", "user_pick", "business_date", "close_day",
           "quit_program", "day_closed", "demo_badge")
