# panels.py
# ============================================================
#  Quick Panels - الإدخال السريع
#
#  قاعدة: كل اسم تحليل هنا لازم يطابق اسم موجود في
#  labs_price_list.py بالظبط. التطبيق بيعمل self-check عند
#  التشغيل وبيبلّغ لو أي panel اتكسر بعد تحديث قائمة الأسعار.
#
#  BUNDLES: أسعار الباقات المجمّعة الموجودة في قائمة أسعار
#  Orange (06-Jun-2026) ومش موجودة في labs_price_list.py.
#  ⚠️ راجع الأرقام دي قبل الاستخدام الفعلي.
# ============================================================

#  أسعار الباقات وتركيبتها اتنقلت لـ bundles.py وبقت جزء من قائمة
#  الأسعار نفسها — فالـ panel هنا بيشاور على اسم الباقة وخلاص.

BRANCHES = ["Orange (La Cité)", "Diamond"]
DEFAULT_BRANCH = "Orange (La Cité)"


# panel -> {"tests": [أسماء بالظبط], "bundle": اسم في BUNDLES (اختياري)}
QUICK_PANELS = {
    # ---- الأكثر طلباً في الاستقبال ----
    "🩸 CBC": {"tests": ["CBC"]},
    "🧪 Urine Examination": {"tests": ["Urine Examination"]},
    "💩 Stool Examination": {"tests": ["Stool Examination"]},
    "🔥 CRP + ESR": {"tests": ["CRP", "ESR"]},
    "🤰 Pregnancy (Serum)": {"tests": ["Pregnancy in serum Qualit."]},

    # ---- مفرّق سريع (طلبات الاستقبال المتكررة) ----
    "🫀 ALT + AST": {"tests": ["ALT (SGPT)", "AST (SGOT)"]},
    "🫘 Urea + Creat": {"tests": ["Urea", "Creatinine (Serum)"]},
    "💎 Uric Acid": {"tests": ["Uric Acid"]},
    "🍬 HbA1c only": {"tests": ["HbA1C"]},
    "🦠 HBs + HCV + HIV": {
        "tests": ["HBs Ag", "HCV IgG", "HIV (I,II) Abs"],
    },

    # ---- بروفايلات ليها سعر باقة ----
    "🫀 Liver Profile": {
        "bundle": "Liver Profile",
        "tests": [
            "ALT (SGPT)", "AST (SGOT)", "Bilirubin Total", "Bilirubin Direct",
            "Albumin (ALB)", "Total Protein", "Alkaline Phosphatase (ALP)",
            "GGT (Gamma-glutamyl transferase)",
        ],
    },
    "🫘 Kidney Profile": {
        "bundle": "Kidney Profile",
        "tests": ["Urea", "Creatinine (Serum)", "Uric Acid", "Na (Sodium)",
                  "K (Potassium)", "Calcium (Total)", "PO4 (Phosphorus)"],
    },
    "💉 Lipid Profile": {
        "bundle": "Lipid Profile",
        "tests": ["Cholesterol", "Triglycerides", "HDL", "LDL", "VLDL"],
    },
    "🦋 Thyroid Profile": {
        "bundle": "Thyroid Profile",
        "tests": ["TSH", "FT3", "FT4"],
    },

    # ---- بروفايلات من غير باقة ----
    "🍬 Diabetes (FBG+PPBG+A1c)": {"tests": ["FBG", "PPBG", "HbA1C"]},
    "🦋 TSH Only": {"tests": ["TSH"]},
    "🔩 Anemia Workup": {"tests": ["CBC", "Ferritin", "Iron (Serum)", "TIBC"]},
    "🩹 PT + PTT": {"tests": ["PT", "PTT"]},
    "❤️ Cardiac": {"tests": ["Troponin (I)", "CK (MB)", "LDH"]},

    # ---- فيتامينات ----
    "☀️ Vitamin D3": {"tests": ["Vitamin D3(25 Hydroxy Cholecal.)"]},
    "💊 Vitamin B12": {"tests": ["Vitamin B12"]},

    # ---- باقات مركّبة ----
    "🧾 Check-up أساسي": {
        "tests": ["CBC", "FBG", "ALT (SGPT)", "AST (SGOT)", "Creatinine (Serum)",
                  "Urea", "Uric Acid", "Cholesterol", "Triglycerides",
                  "Urine Examination"],
    },
    "💍 قبل الزواج": {
        "tests": ["CBC", "ABO", "Blood Rh", "HBs Ag", "HCV IgG", "HIV (I,II) Abs"],
    },
    "🏥 قبل العملية": {
        "tests": ["CBC", "PT", "PTT", "FBG", "Creatinine (Serum)",
                  "HBs Ag", "HCV IgG", "ABO", "Blood Rh"],
    },
    "🤒 حمى / التهاب": {
        "tests": ["CBC", "CRP", "ESR", "Widal Test", "Urine Examination"],
    },
    "👶 متابعة حمل": {
        "tests": ["CBC", "ABO", "Blood Rh", "FBG", "Urine Examination", "TSH"],
    },
    "🧫 مزارع": {"tests": ["Urine Culture", "Stool Culture"]},
}


def panel_tests(panel: str):
    return QUICK_PANELS[panel]["tests"]


def panel_bundle_name(panel: str, branch: str = DEFAULT_BRANCH):
    """اسم الباقة الخاصة بالـ panel لو الفرع متاح فيه، وإلا None."""
    from bundles import bundles_for
    name = QUICK_PANELS.get(panel, {}).get("bundle")
    if not name:
        return None
    if any(b["name"] == name for b in bundles_for(branch)):
        return name
    return None


def validate_panels(idx, resolve_test, exact_statuses=("exact",)) -> dict:
    """
    بيتأكد إن كل عنصر في كل panel له مطابقة تامة.
    بيرجّع المكسور بس: {panel: [(name, status, hint), ...]}
    """
    broken = {}
    for panel, cfg in QUICK_PANELS.items():
        bad = []
        for t in cfg["tests"]:
            r = resolve_test(t, idx)
            if r.status not in exact_statuses:
                sug = r.best.name if r.best else "—"
                bad.append((t, r.status, f"أقرب اسم: {sug}"))
        if bad:
            broken[panel] = bad
    return broken
