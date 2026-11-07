# offers_data.py
# ============================================================
#  📋 كتالوج عروض المعمل — بيانات بحتة (من رسائل واتساب المعمل)
#
#  القائمة الترحيبية (MENU): 39 رقم بنفس نصوصك. كل رقم ممكن يقابله عرض أو أكتر
#  في OFFERS. الحالات (status):
#     current  عرض شغّال (الأحدث)         legacy   نسخة قديمة بسعر قديم (محفوظة للمرجع)
#     pending  الرقم في القائمة ومفيش تفاصيل/سعر لسه — ضيفها هنا
#     service  خدمة مش عرض (روشتة / إلغاء الرسائل)
#     bundles  بيتسعّر من باقات التطبيق (bundles.py)
#
#  قراءة الأسعار: before = «قبل الخصم»، after = «بعد الخصم». لو الشات فيه نسختين
#  بأسعار مختلفة لنفس العرض: الأحدث current والأقدم legacy (والأساس: مطابقة «قبل
#  الخصم» لمجموع أسعار قائمتك الحالية — شوف offers_catalog.price_check).
#  db = أسماء بالظبط في labs_price_list.py (للمقارنة بالقائمة فقط، مش بتأثر على الأسعار).
#  review = ملاحظة داخلية للإدارة (ما بتظهرش للعميل).
#
#  ⚠️ الأرقام دي منقولة من رسائلك — راجعها قبل الاعتماد، خصوصاً اللي علامتها review.
# ============================================================

MENU = [
    (1, "تساقط الشعر وعلاجه"),
    (2, "الفحص الشامل لكل الجسم"),
    (3, "عرض كل الفيتامينات والمعادن"),
    (4, "عرض أورانج 1"),
    (5, "عرض أورانج 2"),
    (6, "عرض بداية عمل تخسيس"),
    (7, "عرض زيادة الوزن"),
    (8, "عرض تشخيص الإرهاق المزمن"),
    (9, "تحاليل التوتر والصداع والدوخة"),
    (10, "تحاليل الضعف الجنسي وتأخر الإنجاب (يُرجى تحديد الجنس)"),
    (11, "عرض أهم فيتامينات الجسم"),
    (12, "عرض فيتامين د"),
    (13, "عرض الغدة الدرقية"),
    (14, "عرض جرثومة المعدة"),
    (15, "عرض معدل الحرق ومقاومة الأنسولين"),
    (16, "تحاليل عدم انتظام الدورة ومتابعتها"),
    (17, "مسحة عنق الرحم"),
    (18, "مسحة لتحديد الفيروسات (البرد، كورونا، التنفس)"),
    (19, "كثرة الشعر عند الإناث"),
    (20, "الحساسية وأنواعها"),
    (21, "تشخيص الروماتيزم وألم العظام"),
    (22, "تحاليل الاكتئاب"),
    (23, "النحافة وعدم زيادة الوزن"),
    (24, "تحاليل القولون"),
    (25, "دلالات الأورام"),
    (26, "معي روشتة وأرغب بمعرفة الأسعار"),
    (27, "إلغاء خدمة إرسال العروض للواتساب"),
    (28, "تحاليل ما قبل الزواج"),
    (29, "متابعة الحمل وتحاليله الدورية"),
    (30, "تحاليل وظائف الكبد والكلى"),
    (31, "متابعة مرضى السكري و السكر التراكمي"),
    (32, "تحاليل الدهون والكوليسترول"),
    (33, "تشخيص الأنيميا وأمراض الدم"),
    (34, "تحاليل هشاشة العظام"),
    (35, "تحاليل الالتهابات المناعية"),
    (36, "تحاليل الأمراض المنقولة جنسيًا"),
    (37, "مسحة البلعوم والأنف"),
    (38, "تحاليل حساسية الطعام"),
    (39, "تحاليل حديثي الولادة والفحص المبكر للأمراض الوراثية"),
]

# أسماء قائمة الأسعار (مختصرات عشان السطور تبقى قصيرة)
D3 = "Vitamin D3(25 Hydroxy Cholecal.)"
B12 = "Vitamin B12"
MG = "Magnesium (Mg) serum"
CA = "Calcium (Total)"
ALT, AST = "ALT (SGPT)", "AST (SGOT)"
CREAT = "Creatinine (Serum)"
FOLATE = "Folate (Folic Acid) serum"
HBA1C = "HbA1C"
TESTO_T, TESTO_F = "Testosterone Total", "Testosterone Free"


def _o(**kw):
    base = {"no": None, "title": "", "short": "", "pill": "", "status": "current",
            "tests": [], "db": [], "before": None, "after": None, "pct": "",
            "fasting": 0, "notes": [], "desc": "", "see_also": [], "override": "",
            "bundle_refs": [], "review": "", "from_price": False}
    base.update(kw)
    return base


OFFERS = [
    # ---------------- 1 ----------------
    _o(id="1", no=1, title="عرض تساقط الشعر", short="تساقط الشعر", pill="Hair Loss",
       desc="تحاليل تساقط الشعر",
       tests=["صورة دم (CBC)", "غدة درقية (TSH)", "مخزون حديد (Ferritin)", "زنك", "فيتامين د"],
       db=["CBC", "TSH", "Ferritin", "Zinc (blood)", D3], before=2680, after=2150),

    # ---------------- 2 (الفحص الشامل) ----------------
    _o(id="2", no=2, title="عرض خصم 25% على تحاليل Check up", short="الفحص الشامل", pill="Check up",
       pct="25%",
       desc=("صورة دم كاملة - سكر صائم وتراكمي - أهم إنزيمات الكلى والكبد - دهون - أهم تحليل للغدة - "
             "مقاومة أنسولين (يحتاج صيام) - مؤشر التهابات - جرثومة المعدة - فيتامين د وفيتامين B12 - "
             "تحليل بول وإنزيم للقلب"),
       tests=["CBC", "FBG", "HbA1c", "ALT", "AST", "Urea", "Creatinine", "Uric Acid", "FT4", "TSH",
              "HOMA-IR", "Lipid Profile", "CRP", "H.Pylori Ag", "Urine", "CK-MB", "Vitamin D", "Vitamin B12"],
       db=["CBC", "FBG", HBA1C, ALT, AST, "Urea", CREAT, "Uric Acid", "FT4", "TSH", "HOMA1-IR",
           "Lipid Profile", "CRP", "H.pylori Ag in Stool (Quanti)", "Urine Examination", "CK (MB)", D3, B12],
       before=7490, after=5600, see_also=["4", "5"]),
    _o(id="2-v1", no=2, status="legacy", title="عرض خصم 30% على تحاليل Check up (بدون FT4)",
       short="الفحص الشامل", pill="Check up", pct="30%",
       tests=["CBC", "FBG", "HbA1c", "ALT", "AST", "Urea", "Creatinine", "Uric Acid", "TSH", "HOMA-IR",
              "Lipid Profile", "CRP", "H.Pylori Ag", "Urine", "CK-MB", "Vitamin D", "Vitamin B12"],
       db=["CBC", "FBG", HBA1C, ALT, AST, "Urea", CREAT, "Uric Acid", "TSH", "HOMA1-IR",
           "Lipid Profile", "CRP", "H.pylori Ag in Stool (Quanti)", "Urine Examination", "CK (MB)", D3, B12],
       before=6520, after=4600),

    # ---------------- 3 ----------------
    _o(id="3", no=3, title="عرض الفيتامينات والمعادن (شامل فيتامين C)", short="فيتامينات ومعادن",
       pill="Vitamins+C",
       tests=["فيتامين D", "فيتامين C", "فيتامين B12", "فوليك أسيد", "النحاس", "المغنيسيوم",
              "مخزون الحديد", "الزنك", "الكالسيوم"],
       db=[D3, "Vitamin C", B12, FOLATE, "Copper (blood)", MG, "Ferritin", "Zinc (blood)", CA],
       before=11680, after=9500),
    _o(id="3b", no=3, title="عرض الفيتامينات والمعادن", short="فيتامينات ومعادن", pill="Vitamins",
       tests=["فيتامين D", "فيتامين B12", "فوليك أسيد", "النحاس", "المغنيسيوم", "مخزون الحديد",
              "الزنك", "الكالسيوم"],
       db=[D3, B12, FOLATE, "Copper (blood)", MG, "Ferritin", "Zinc (blood)", CA],
       before=5880, after=4700),

    # ---------------- 4 / 5 ----------------
    _o(id="4", no=4, title="عرض أورانج 1", short="أورانج 1", pill="Orange 1",
       desc=("صورة دم وسكر تراكمي ودهون كامل وأهم وظائف الكلى والكبد وفيتامين د وغدة درقية (أهم اثنين) "
             "وكالسيوم ومغنسيوم ومخزون حديد"),
       tests=["CBC", "HbA1c", "Lipid Profile", "ALT", "AST", "Urea", "Creatinine", "Uric Acid",
              "Vitamin D", "FT4", "TSH", "Calcium", "Magnesium", "Ferritin"],
       db=["CBC", HBA1C, "Lipid Profile", ALT, AST, "Urea", CREAT, "Uric Acid", D3, "FT4", "TSH", CA, MG, "Ferritin"],
       before=4710, after=3750,
       notes=["ويتم إضافة تحليل مقاومة الأنسولين في حالة عدم وجود سكري"]),
    _o(id="4-v1", no=4, status="legacy", title="عرض أورانج 1 (سعر قديم)", short="أورانج 1", pill="Orange 1",
       tests=["CBC", "HbA1c", "Lipid Profile", "ALT", "AST", "Urea", "Creatinine", "Uric Acid",
              "Vitamin D", "FT4", "TSH", "Calcium", "Magnesium", "Ferritin"],
       db=["CBC", HBA1C, "Lipid Profile", ALT, AST, "Urea", CREAT, "Uric Acid", D3, "FT4", "TSH", CA, MG, "Ferritin"],
       before=4050, after=3250),
    _o(id="5", no=5, title="عرض أورانج لاب 2", short="أورانج 2", pill="Orange 2",
       desc=("صورة دم وسكر تراكمي ودهون كامل وأهم وظائف الكلى والكبد وتحليل واحد للغدة الدرقية "
             "ودلالات التهابات وتحليل بول وتحليل فيتامين د"),
       tests=["CBC", "HbA1c", "Lipid Profile", "ALT", "AST", "Urea", "Creatinine", "Uric Acid",
              "TSH", "CRP", "Urine", "Vitamin D"],
       db=["CBC", HBA1C, "Lipid Profile", ALT, AST, "Urea", CREAT, "Uric Acid", "TSH", "CRP", "Urine Examination", D3],
       before=4050, after=3200, notes=["لا يتطلب صيام"]),
    _o(id="5-v1", no=5, status="legacy", title="عرض أورانج لاب 2 (سعر قديم — بدون فيتامين د)", short="أورانج 2",
       pill="Orange 2",
       tests=["CBC", "HbA1c", "Lipid Profile", "ALT", "AST", "Urea", "Creatinine", "Uric Acid",
              "TSH", "CRP", "Urine"],
       db=["CBC", HBA1C, "Lipid Profile", ALT, AST, "Urea", CREAT, "Uric Acid", "TSH", "CRP", "Urine Examination"],
       before=2640, after=2100, notes=["لا يتطلب صيام"]),

    # ---------------- 6 / 7 ----------------
    _o(id="6", no=6, title="عرض بداية عمل تخسيس", short="بداية تخسيس", pill="Slimming",
       desc="تحاليل لعمل تخسيس", fasting=10,
       tests=["CBC", "Na", "K", "Ca", "PO4", "Mg", "Urea", "Creatinine", "ALT", "Albumin", "Zinc",
              "Iron", "Vitamin D", "FT4", "TSH", "HOMA-IR", "Lipid Profile"],
       db=["CBC", "Na (Sodium)", "K (Potassium)", CA, "PO4 (Phosphorus)", MG, "Urea", CREAT, ALT,
           "Albumin (ALB)", "Zinc (blood)", "Iron (Serum)", D3, "FT4", "TSH", "HOMA1-IR", "Lipid Profile"],
       before=5780, after=4300),
    _o(id="7", no=7, title="عرض زيادة الوزن وضعف الحرق", short="زيادة الوزن", pill="Overweight",
       desc=("لتشخيص زيادة الوزن وضعف الحرق — تشمل مقاومة الأنسولين مع الدهون والغدة الدرقية والسكر "
             "التراكمي وأهم وظيفة للكبد والكلى"), fasting=10,
       tests=["HOMA-IR", "Lipid Profile", "FT3", "FT4", "TSH", "HbA1c", "ALT", "Creatinine"],
       db=["HOMA1-IR", "Lipid Profile", "FT3", "FT4", "TSH", HBA1C, ALT, CREAT], before=2820, after=2100),
    _o(id="7-v1", no=7, status="legacy", title="عرض زيادة الوزن (سعر قديم)", short="زيادة الوزن", pill="Overweight",
       fasting=10, tests=["HOMA-IR", "Lipid Profile", "FT3", "FT4", "TSH", "HbA1c", "ALT", "Creatinine"],
       db=["HOMA1-IR", "Lipid Profile", "FT3", "FT4", "TSH", HBA1C, ALT, CREAT], before=2480, after=1850),

    # ---------------- 8 ----------------
    _o(id="8", no=8, title="عرض تحاليل الإرهاق المزمن", short="الإرهاق المزمن", pill="Chronic Fatigue",
       desc="تشمل 14 تحليل",
       tests=["الغدة (تحليلين)", "صورة دم", "مخزون الحديد", "أملاح الدم", "الكالسيوم", "الفيتامينات",
              "معدل الحرق", "الالتهابات", "وظائف الكبد"],
       before=5840, after=4380,
       review="التحاليل الـ14 مش مسمّاة بالاسم في الرسالة — ماينفعش أقارنها بالقائمة"),
    _o(id="8-v1", no=8, status="legacy", title="عرض تحاليل الإرهاق المزمن (سعر قديم)", short="الإرهاق المزمن",
       pill="Chronic Fatigue", desc="تشمل 14 تحليل",
       tests=["الغدة (تحليلين)", "صورة دم", "مخزون الحديد", "أملاح الدم", "الكالسيوم", "الفيتامينات",
              "معدل الحرق", "الالتهابات", "وظائف الكبد"], before=5240, after=3900),

    # ---------------- 9 ----------------
    _o(id="9", no=9, title="تحاليل الدوخة أو الصداع والتوتر", short="الدوخة والصداع", pill="Dizziness",
       tests=["CBC", "Ferritin", "FT4", "TSH", "FBG", "HbA1c", "Na", "K", "Mg", "Calcium"],
       db=["CBC", "Ferritin", "FT4", "TSH", "FBG", HBA1C, "Na (Sodium)", "K (Potassium)", MG, CA],
       before=2690, after=2150),
    _o(id="9-v1", no=9, status="legacy", title="تحاليل الدوخة أو الصداع والتوتر (سعر قديم)", short="الدوخة والصداع",
       pill="Dizziness", tests=["CBC", "Ferritin", "FT4", "TSH", "FBG", "HbA1c", "Na", "K", "Mg", "Calcium"],
       db=["CBC", "Ferritin", "FT4", "TSH", "FBG", HBA1C, "Na (Sodium)", "K (Potassium)", MG, CA],
       before=2610, after=2000),

    # ---------------- 10 ----------------
    _o(id="10F", no=10, title="تحاليل الضعف الجنسي عند الإناث", short="ضعف جنسي (إناث)", pill="Female",
       desc="تشمل بعض الهرمونات مع الغدة الدرقية وحمض الفوليك وصورة الدم وأهم وظيفة للكبد والكلى",
       tests=["FSH", "LH", "Testosterone (Total, Free)", "PRL", "TSH", "FT4", "E2", "Folic Acid", "CBC",
              "ALT", "Creatinine"],
       db=["FSH", "LH", TESTO_T, TESTO_F, "Prolactin (PRL)", "TSH", "FT4", "E2 (Estradiol)", FOLATE, "CBC", ALT, CREAT],
       before=4430, after=3300),
    _o(id="10M", no=10, title="تحاليل الضعف الجنسي وضعف الانتصاب عند الرجال", short="ضعف جنسي (رجال)", pill="Male",
       desc="تشمل بعض الهرمونات مع الزنك والسكر التراكمي والغدة الدرقية والدهون",
       tests=["FSH", "LH", "Testosterone (Total, Free)", "PRL", "TSH", "Zinc", "HbA1c", "Lipid Profile"],
       db=["FSH", "LH", TESTO_T, TESTO_F, "Prolactin (PRL)", "TSH", "Zinc (blood)", HBA1C, "Lipid Profile"],
       before=3550, after=2650),

    # ---------------- 11 ----------------
    _o(id="11", no=11, title="عرض أهم فيتامينات الجسم", short="أهم الفيتامينات", pill="Vitamins",
       tests=["فيتامين D", "فيتامين B12"], db=[D3, B12], before=2400, after=1800),

    # ---------------- 13 (override: الرسالة الأصلية بسعرين) ----------------
    _o(id="13", no=13, title="عرض الغدة الدرقية", short="الغدة الدرقية", pill="Thyroid",
       tests=["FT3", "FT4", "TSH"], db=["FT3", "FT4", "TSH"], after=650,
       override=("عرض الغدة الدرقية الثلاث\nFT3, FT4, TSH\nالثلاث تحاليل بـ 650 ج\nوالخمس تحاليل بـ 1000 ج"),
       review=("الخمس تحاليل (1000 ج) مش مسمّاة في الرسالة. وباقة Thyroid Profile في التطبيق "
               "(bundles.py) بـ 870 = مجموع التحاليل — بينما عرضك 650 لنفس الثلاثة")),

    # ---------------- 15 / 16 / 17 ----------------
    _o(id="15", no=15, title="عرض تحليل مقاومة الأنسولين (معدل الحرق)", short="مقاومة الأنسولين", pill="HOMA-IR",
       tests=["HOMA-IR (مقاومة الأنسولين)"], db=["HOMA1-IR"], after=450, fasting=8,
       notes=["مسموح بالمياه والعلاج فقط"]),
    _o(id="16", no=16, title="تحاليل تشخيص تكيس المبايض وعدم انتظام الدورة", short="تكيس المبايض", pill="PCOS",
       tests=["FSH", "LH", "AMH", "PRL", "TSH"],
       db=["FSH", "LH", "AMH (Anti Mullerian Hormone)", "Prolactin (PRL)", "TSH"], before=2610, after=2100,
       notes=["تتعمل في اليوم الثاني إلى الخامس من بداية الدورة"],
       review="ربطت الرقم 16 (عدم انتظام الدورة) بعرض تكيس المبايض — راجع إنه صح"),
    _o(id="17", no=17, title="مسحة عنق الرحم", short="مسحة عنق الرحم", pill="Cervical Swab",
       tests=["Vaginal swab C/S (بكتيري فقط)", "Vaginal panel by PCR (بكتريا وفيروسات وفطريات)"],
       after=450, from_price=True,
       override=("أهلاً وسهلاً بحضرتك\n"
                 "مسحة عنق الرحم بتؤخذ عن طريق الطبيبة المختصة بحضرتك، أو بنقول لحضرتك الطريقة على سواب قطن من المعمل.\n\n"
                 "النوع الأول: فحص بكتيري فقط\nVaginal swab C/S\nوسعره 450 ج\n\n"
                 "النوع الثاني: بيضم كل البكتريا والفيروسات والفطريات في المسحة\nVaginal panel by PCR\nوسعره 3000 ج")),

    # ---------------- 19 ----------------
    _o(id="19", no=19, title="تحاليل تشخيص كثرة الشعر عند الإناث", short="كثرة الشعر", pill="Hirsutism",
       desc="يشمل 5 تحاليل",
       tests=["FSH", "LH", "DHEA-S", "Testosterone Total", "17-OH Progesterone"],
       db=["FSH", "LH", "DHEA-S", TESTO_T, "17 OH Progesterone"], before=3300, after=2650,
       notes=["تتعمل في اليوم الثاني أو الثالث من بداية الدورة"]),
    _o(id="19-v1", no=19, status="legacy", title="تحاليل تشخيص كثرة الشعر (سعر قديم)", short="كثرة الشعر", pill="Hirsutism",
       tests=["FSH", "LH", "DHEA-S", "Testosterone Total", "17-OH Progesterone"],
       db=["FSH", "LH", "DHEA-S", TESTO_T, "17 OH Progesterone"], before=3250, after=2600,
       notes=["تتعمل في اليوم الثاني أو الثالث من بداية الدورة"]),

    # ---------------- 20 – 25 ----------------
    _o(id="20", no=20, title="عرض الحساسية", short="الحساسية", pill="Allergy",
       desc="يشمل 3 تحاليل: المؤشر العام + 30 نوع طعام + 30 نوع روائح ومستنشقات",
       tests=["IgE Total (المؤشر العام)", "IgE Food panel (30 نوع طعام)", "IgE Inhalant panel (30 نوع روائح ومستنشقات)"],
       db=["IgE (Total)", "IgE Food allergy test panel", "IgE Inhalant allergy panel"], before=4900, after=4000),
    _o(id="21", no=21, title="عرض 25% على تحاليل تشخيص الروماتيزم", short="الروماتيزم", pill="Rheumatism",
       pct="25%", desc="لتشخيص الروماتيزم أو النقرس وألم عظام الرجلين",
       tests=["ANA", "Uric Acid", "TSH", "Vitamin D", "Vitamin B12", "ESR", "CRP", "Anti CCP"],
       db=["ANA (Antinuclear Ab)", "Uric Acid", "TSH", D3, B12, "ESR", "CRP", "Anti CCP"], before=4970, after=3700),
    _o(id="22", no=22, title="تحاليل الاكتئاب", short="تحاليل الاكتئاب", pill="Depression",
       desc="تحاليل مهمة تتداخل في أسباب الاكتئاب",
       tests=["فيتامين D", "فيتامين B12", "ماغنسيوم", "زنك", "مخزون الحديد", "TSH"],
       db=[D3, B12, MG, "Zinc (blood)", "Ferritin", "TSH"], before=3850, after=2850),
    _o(id="23", no=23, title="بروفايل النحافة وعدم زيادة الوزن", short="النحافة", pill="Underweight",
       tests=["CBC", "HbA1c", "ALT", "AST", "Ferritin", "FT4", "TSH", "tTG IgA", "Total IgA"],
       db=["CBC", HBA1C, ALT, AST, "Ferritin", "FT4", "TSH", "Tissue transglutaminase Ab (IgA)",
           "IgA (Immunoglobulin A)"], before=3500, after=2800),
    _o(id="24", no=24, title="تحاليل القولون", short="القولون", pill="Colon",
       tests=["Schebo test", "Calprotectin", "FOB"],
       db=["Schebo test (M2-PK)", "Calprotectin in stool (Quant)", "Occult Blood In Stool (FOB)"],
       before=4500, after=3600),
    _o(id="25", no=25, title="عرض دلالات الأورام (للإناث)", short="دلالات الأورام", pill="Tumor Markers",
       tests=["CEA", "CA 19.9", "CA 125", "CA 15.3", "AFP", "Tg"],
       db=["CEA (Carcinoembryonic Antigen)", "CA 19.9", "CA 125", "CA 15.3", "AFP", "Thyroglobulin (Tg)"],
       before=4000, after=3000, notes=["للإناث"],
       review="الرسالة مكتوب فيها «For female» — مفيش نسخة للرجال في الشات"),

    # ---------------- 26 / 27 (خدمات) ----------------
    _o(id="26", no=26, status="service", title="معي روشتة وأرغب بمعرفة الأسعار", short="روشتة",
       override=("أهلاً بحضرتك 🌟\nابعتلنا صورة الروشتة (أو اكتب أسماء التحاليل المطلوبة) وهنرد عليك بالأسعار "
                 "والمواعيد المتاحة في أقرب وقت."),
       review="نص مقترح مني — عدّله زي ما بتردّوا عادةً"),
    _o(id="27", no=27, status="service", title="إلغاء خدمة إرسال العروض للواتساب", short="إلغاء العروض",
       override=("تم إيقاف إرسال العروض على رقمك ✅\nلو حبيت ترجع تستقبلها تاني ابعتلنا كلمة «عروض»، "
                 "ويسعدنا خدمتك في أي وقت."),
       review="نص مقترح مني. وفي الفاتورة زرار «تسجيل طلب إيقاف الرسائل» بيسجّل الإيقاف على الرقم"),

    # ---------------- 28 / 29 ----------------
    _o(id="28", no=28, title="عرض تحاليل الزواج", short="تحاليل الزواج", pill="Premarital",
       tests=["CBC", "ABO Rh", "Hb electrophoresis", "HCV Ab", "HBs Ag", "HIV"],
       db=["CBC", "ABO", "Blood Rh", "Hemoglobin electrophoresis by", "HCV IgG", "HBs Ag", "HIV (I,II) Abs"],
       before=2150, after=1700,
       review="Hb electrophoresis ليها سعرين في القائمة (600 و4000) — التطبيق بيستخدم 600 في المقارنة"),
    _o(id="29", no=29, title="تحاليل متابعة الحمل", short="متابعة الحمل", pill="Pregnancy",
       tests=["CBC", "Ferritin", "Urine analysis", "Vitamin D", "ABO Rh", "Creatinine", "ALT"],
       db=["CBC", "Ferritin", "Urine Examination", D3, "ABO", "Blood Rh", CREAT, ALT], before=2100, after=1680),

    # ---------------- 30 / 32 (من باقات التطبيق) ----------------
    _o(id="30", no=30, status="bundles", title="تحاليل وظائف الكبد والكلى", short="الكبد والكلى",
       bundle_refs=["Liver Profile", "Kidney Profile"]),
    _o(id="32", no=32, status="bundles", title="تحاليل الدهون والكوليسترول", short="الدهون",
       bundle_refs=["Lipid Profile"]),

    # ---------------- خارج القائمة الترحيبية ----------------
    _o(id="S1", no=None, title="عرض تحاليل ما بعد عمليات تكميم المعدة", short="بعد التكميم", pill="Post-Sleeve",
       desc="يشمل كل التحاليل والمعادن والفيتامينات بعد عمليات تكميم المعدة",
       tests=["CBC", "Ferritin", "HbA1c", "Lipid Profile", "TSH", "ALT", "AST", "Albumin", "Urea", "Creatinine",
              "Uric Acid", "Na", "K", "Mg", "Ca total", "PO4", "Vitamin D", "Vitamin B12", "Folic acid", "Zinc",
              "Iron profile", "Testosterone (total, free)", "Estrogen", "FSH", "LH", "Prolactin"],
       after=8000, review="مفيش «قبل الخصم» في الرسالة، ومش ليه رقم في القائمة الترحيبية"),
]

# أرقام القائمة اللي مفيش عرض ليها لسه (تتضاف تلقائياً كـ pending)
PENDING_NOS = [12, 14, 18, 31, 33, 34, 35, 36, 37, 38, 39]

_TITLES = dict(MENU)
OFFERS += [_o(id=str(n), no=n, status="pending", title=_TITLES[n], short=_TITLES[n]) for n in PENDING_NOS]
