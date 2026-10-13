تعليمات التشغيل الأولى - اقرأ هذا أولا
====================================
1. انسخ ملف kitchen_inventory_portable.zip إلى القرص D:\ (وليس سطح المكتب).
2. كليك يمين على الملف ثم Extract All إلى D:\kitchen_inventory.
3. للتحقق: افتح موجه الأوامر واكتب
   certutil -hashfile kitchen_inventory_portable.zip SHA256
   وقارن الناتج مع ملف kitchen_inventory_portable.sha256.txt.
4. دبل كليك على RUN_CHECK.bat (يكتب تقرير report.txt ولا يغير أي شيء في الويندوز).
5. دبل كليك على start.bat لتشغيل البرنامج.
6. اختياري: create_shortcut.bat لعمل اختصار على سطح المكتب.
7. لا تضع أي بيانات حقيقية داخل ملفات البرنامج؛ مجلد data\ ينشأ فارغا ولا يستبدل أبدا عند تحديث الكود (للتحديث: استبدل كل شيء ما عدا data\).
8. للتجربة فقط: start_demo.bat ينشئ بيانات وهمية في data_demo\ (تظهر شارة تجريبي) ويمكن حذف data_demo\ بعد التجربة.
9. البرنامج يعمل على المنفذ 8001 (المنفذ 8000 يخص برنامج الكاشير). لا تغير أي إعدادات في الويندوز. ضبط المنطقة الزمنية على مصر يتم بمعرفة المدير بشكل منفصل.

KITCHEN INVENTORY - READ FIRST
=============================
1. Copy kitchen_inventory_portable.zip to drive D:\ (not the Desktop).
2. Right-click the zip > Extract All, to D:\kitchen_inventory.
3. Verify: run
   certutil -hashfile kitchen_inventory_portable.zip SHA256
   and compare with kitchen_inventory_portable.sha256.txt.
4. Double-click RUN_CHECK.bat (writes report.txt, changes nothing in Windows).
5. Double-click start.bat to run the program.
6. Optional: create_shortcut.bat puts a shortcut on the Desktop.
7. NEVER put real data inside the program files; data\ is created empty and is never overwritten on code updates (to update: replace everything EXCEPT data\).
8. Demo only: start_demo.bat builds fake history into data_demo\ (DEMO badge shows); data_demo\ can be deleted after the demo.
9. The app uses port 8001 (8000 belongs to the cafeteria POS). Do not change Windows settings. The Egypt timezone is set by the manager separately.
