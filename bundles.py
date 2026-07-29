# bundles.py
# ============================================================
#  الباقات المجمّعة (Profiles)
#
#  ليه ملف منفصل ومش جوه labs_price_list.py؟
#  لأن labs_price_list.py ملف *مولّد* من price_list.txt. أي إعادة
#  توليد بتمسح أي إضافة يدوية — وده اللي حصل قبل كده وكسر الـ panels.
#  الملف ده بيتدمج في قائمة الأسعار وقت التحميل، فالباقات بتظهر في
#  الـ search كأنها تحاليل عادية، ومش بتضيع لما تحدّث الأسعار.
#
#  لتعديل سعر باقة: غيّر "price" هنا وبس.
#  بعد أي تعديل شغّل: python3 test_price_utils.py
# ============================================================

BUNDLE_CATEGORY = "Profiles — باقات"

BUNDLES = [
    {
        "name": "Lipid Profile",
        "price": 700,
        "result_days": 1,
        "collection_notes": "1.0 ml Serum — صايم 12 ساعة",
        "components": ["Cholesterol", "Triglycerides", "HDL", "LDL", "VLDL"],
        "aliases": ["lipid", "lipids", "lipid profil", "دهون", "دهون الدم",
                    "الدهون", "كوليسترول"],
        "branches": ["Orange (La Cité)", "Diamond"],
    },
    {
        "name": "Liver Profile",
        "price": 850,
        "result_days": 1,
        "collection_notes": "1.0 ml Serum — يفضّل صايم 6-8 ساعات",
        "components": [
            "ALT (SGPT)", "AST (SGOT)", "Bilirubin Total", "Bilirubin Direct",
            "Albumin (ALB)", "Total Protein", "Alkaline Phosphatase (ALP)",
            "GGT (Gamma-glutamyl transferase)",
        ],
        "aliases": ["liver", "lft", "liver function", "كبد", "وظائف كبد",
                    "وظائف الكبد"],
        "branches": ["Orange (La Cité)", "Diamond"],
    },
    {
        "name": "Kidney Profile",
        "price": 850,
        "result_days": 1,
        "collection_notes": "1.0 ml Serum",
        # ⚠️ راجع التركيبة: بـ 5 تحاليل المفرّق 790 (أرخص من الباقة).
        #    بـ 7 تحاليل المفرّق 1150 والباقة بتوفّر 300 — دي الأقرب للمنطق.
        "components": [
            "Urea", "Creatinine (Serum)", "Uric Acid", "Na (Sodium)",
            "K (Potassium)", "Calcium (Total)", "PO4 (Phosphorus)",
        ],
        "aliases": ["kidney", "rft", "renal", "kidney function", "كلى",
                    "وظائف كلى", "وظائف الكلى"],
        "branches": ["Orange (La Cité)", "Diamond"],
    },
    {
        "name": "Thyroid Profile",
        "price": 870,
        "result_days": 1,
        "collection_notes": "1.0 ml Serum",
        "components": ["TSH", "FT3", "FT4"],
        "aliases": ["thyroid", "thyroid profil", "thyroid profie", "tft",
                    "غدة", "الغدة", "غدة درقية", "الغدة الدرقية"],
        "branches": ["Orange (La Cité)", "Diamond"],
    },
]


def bundles_for(branch: str):
    """الباقات المتاحة في فرع معيّن."""
    return [b for b in BUNDLES if branch in b["branches"]]


def bundle_by_name(name: str):
    from price_utils import norm
    n = norm(name)
    for b in BUNDLES:
        if norm(b["name"]) == n:
            return b
    return None
