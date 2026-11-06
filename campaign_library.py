# campaign_library.py
# ============================================================
#  📚 مكتبة الحملات الموسمية — محتوى جاهز قابل للتعديل (Marketing Studio)
#  كل حملة: قالب + نص + تحاليل مقترحة (بأسماء القائمة بالظبط عشان السعر
#  يتحسب منها). المحتوى الطبي عام للتوعية بس — لازم يتراجع من المسؤول
#  الطبي قبل النشر، وماينتشرش كتوصية طبية شخصية.
# ============================================================

DISCLAIMER = "هذا المحتوى للتوعية العامة وليس بديلاً عن استشارة الطبيب."

# tests = أسماء بالظبط في قائمة الأسعار/الباقات (test_marketing_templates.py بيتأكد)
CAMPAIGNS = {
    "preventive": {
        "label": "🩺 الفحص الدوري (Preventive Health)",
        "template": "offer", "photo": "sugar",
        "title_small": "الفحص الدوري", "title_big": "اطمّن",
        "subtitle": "تحاليل أساسية لمتابعة صحتك بانتظام",
        "badge_mode": "price", "badge_top": "بسعر", "badge_pill": "باقة الفحص الدوري",
        "list_title": "الباقة تشمل", "cta": "احجز تحاليلك الآن",
        "display_items": ["صورة دم كاملة (CBC)", "سكر صائم (FBS)", "وظائف الكبد (ALT)",
                          "وظائف الكلى (Creatinine)", "الدهون (Cholesterol)", "فيتامين د"],
        "tests": ["CBC", "FBG", "ALT (SGPT)", "Creatinine (Serum)", "Cholesterol",
                  "Vitamin D3(25 Hydroxy Cholecal.)"],
    },
    "diabetes": {
        "label": "🩸 التوعية بالسكر (Diabetes Awareness)",
        "template": "offer", "photo": "sugar",
        "title_small": "تحاليل", "title_big": "السكر",
        "subtitle": "شاملة ودقيقة لعناية أفضل بصحتك",
        "badge_mode": "percent", "badge_top": "خصم", "badge_value": "20%",
        "badge_sub": "على باقات", "badge_pill": "تحاليل السكر",
        "list_title": "الباقة تشمل", "cta": "احجز تحاليلك الآن",
        "display_items": ["سكر صائم (FBS)", "سكر بعد الأكل بساعتين (PP)",
                          "السكر التراكمي (HbA1c)", "الأنسولين (Insulin)",
                          "مقاومة الأنسولين (HOMA-IR)"],
        "tests": ["FBG", "PPBG", "HbA1C", "Insulin (Fasting)", "HOMA1-IR"],
    },
    "women": {
        "label": "🌸 صحة المرأة (Women's Health)",
        "template": "offer", "photo": "sun",
        "title_small": "تحاليل", "title_big": "صحة المرأة",
        "subtitle": "متابعة دورية بخصوصية واهتمام",
        "badge_mode": "price", "badge_top": "بسعر", "badge_pill": "باقة صحة المرأة",
        "list_title": "الباقة تشمل", "cta": "احجزي تحاليلك الآن",
        "display_items": ["صورة دم كاملة (CBC)", "مخزون الحديد (Ferritin)",
                          "فيتامين د", "الغدة الدرقية (TSH)"],
        "tests": ["CBC", "Ferritin", "Vitamin D3(25 Hydroxy Cholecal.)", "TSH"],
    },
    "pregnancy": {
        "label": "🤰 متابعة الحمل (Pregnancy Care)",
        "template": "tip", "photo": "sun",
        "headline": "متابعة الحمل بالتحاليل",
        "body": "تحاليل الحمل الدورية تساعد طبيبك في [[متابعة صحتك وصحة الجنين]] — "
                "التزمي بالجدول الذي يحدده لك الطبيب",
        "tests": ["CBC", "ABO", "Blood Rh", "TSH"], "review": True,
    },
    "children": {
        "label": "🧒 صحة الأطفال (Children's Health)",
        "template": "awareness", "photo": "hair",
        "headline": "إرهاق وضعف شهية عند طفلك؟",
        "body": "قد يكون نقص [[الحديد]] أحد الأسباب — تحليل [[الفيريتين وصورة الدم]] "
                "يساعد الطبيب في التقييم",
        "tests": ["Ferritin", "CBC"], "review": True,
    },
    "kidney_liver": {
        "label": "🫘 الكلى والكبد (Kidney & Liver Health)",
        "template": "offer", "photo": "sugar",
        "title_small": "تحاليل", "title_big": "الكلى والكبد",
        "subtitle": "متابعة وظائف الأعضاء الحيوية",
        "badge_mode": "price", "badge_top": "بسعر", "badge_pill": "Liver + Kidney",
        "list_title": "الباقات تشمل", "cta": "احجز تحاليلك الآن",
        "display_items": ["Liver Profile — وظائف الكبد", "Kidney Profile — وظائف الكلى"],
        "tests": ["Liver Profile", "Kidney Profile"],
    },
    "home": {
        "label": "🏠 السحب المنزلي (Home Collection)",
        "template": "offer", "photo": "sugar",
        "title_small": "السحب", "title_big": "المنزلي",
        "subtitle": "ونوصلك لحد باب البيت",
        "badge_mode": "none",
        "list_title": "الخدمة تشمل", "cta": "احجز زيارة منزلية",
        "display_items": ["فني سحب مدرّب", "التزام بمواعيد الزيارة", "النتائج على واتساب"],
        "tests": [],
    },
    "loyalty": {
        "label": "⭐ عملاء Orange (Customer Loyalty)",
        "template": "offer", "photo": "sun",
        "title_small": "شكراً", "title_big": "لثقتك",
        "subtitle": "عرض خاص لعملائنا المتكررين",
        "badge_mode": "percent", "badge_top": "خصم", "badge_value": "10%",
        "badge_sub": "على زيارتك القادمة", "badge_pill": "عملاء Orange",
        "list_title": "اسأل عن العرض", "cta": "احجز زيارتك",
        "display_items": ["اذكر كود العرض عند الحجز", "ساري على الزيارة القادمة"],
        "tests": [],
    },
}


def campaign_fields(key: str) -> dict:
    """حقول الاستوديو (ms_*) من حملة المكتبة. items = display_items سطر لكل بند."""
    c = dict(CAMPAIGNS[key])
    f = {k: v for k, v in c.items() if k not in ("label", "display_items", "tests", "review")}
    if c.get("display_items"):
        f["items"] = "\n".join(c["display_items"])
    return f
