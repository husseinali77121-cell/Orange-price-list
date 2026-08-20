# price_utils.py
# ============================================================
#  Orange Lab - Pricing / Validation utilities
#  Pure logic: NO streamlit imports -> قابل للاختبار من الترمكس مباشرة
#  python3 test_price_utils.py
# ============================================================

from __future__ import annotations

import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
from typing import Dict, List, Optional, Tuple

# ------------------------------------------------------------
# 1) Normalization
# ------------------------------------------------------------

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
_DIGIT_RE = re.compile(r"\d")


def norm(s: str) -> str:
    """توحيد شكل الاسم: lowercase + إزالة الترقيم + دمج المسافات."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    s = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def has_arabic(s: str) -> bool:
    return bool(_ARABIC_RE.search(s or ""))


# ------------------------------------------------------------
# 2) Price index
# ------------------------------------------------------------

@dataclass
class TestRec:
    name: str
    price: int
    category: str
    result_days: Optional[int] = None
    collection_notes: str = ""
    is_bundle: bool = False
    components: Tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return norm(self.name)

    @property
    def component_keys(self) -> set:
        return {norm(c) for c in self.components}


@dataclass
class PriceIndex:
    records: List[TestRec] = field(default_factory=list)
    by_key: Dict[str, List[TestRec]] = field(default_factory=dict)
    keys: List[str] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)
    bundles: List[TestRec] = field(default_factory=list)

    def get(self, name: str) -> List[TestRec]:
        return self.by_key.get(norm(name), [])

    def bundle_for(self, test_name: str) -> Optional[TestRec]:
        """الباقة اللي التحليل ده جوّاها (لو موجودة)."""
        k = norm(test_name)
        for b in self.bundles:
            if k in b.component_keys:
                return b
        return None


def build_index(labs_db: dict, bundle_defs: Optional[list] = None,
                bundle_category: str = "Profiles") -> PriceIndex:
    """
    بيبني الفهرس من قائمة الأسعار + الباقات المدموجة.
    الباقات بتتضاف كتحاليل عادية عشان تظهر في الـ search.
    """
    idx = PriceIndex()
    idx.aliases = dict(ALIASES)

    for category, tests in labs_db.items():
        for t in tests:
            rec = TestRec(
                name=str(t["name"]).strip(),
                price=int(t.get("price", 0) or 0),
                category=category,
                result_days=t.get("result_days"),
                collection_notes=t.get("collection_notes", "") or "",
            )
            idx.records.append(rec)
            idx.by_key.setdefault(rec.key, []).append(rec)

    for b in (bundle_defs or []):
        rec = TestRec(
            name=str(b["name"]).strip(),
            price=int(b["price"]),
            category=b.get("category", bundle_category),
            result_days=b.get("result_days"),
            collection_notes=b.get("collection_notes", ""),
            is_bundle=True,
            components=tuple(b.get("components", ())),
        )
        # الباقة بتاخد الأولوية على أي اسم مشابه في قائمة الأسعار
        idx.by_key[rec.key] = [rec] + idx.by_key.get(rec.key, [])
        idx.records.append(rec)
        idx.bundles.append(rec)
        for a in b.get("aliases", ()):
            idx.aliases[norm(a)] = rec.name

    idx.keys = sorted(idx.by_key.keys())
    return idx


# ------------------------------------------------------------
# 3) Aliases - الاختصارات اللي الاستقبال بيكتبها
#    كل alias لازم يشاور على اسم موجود فعلاً (الـ test بيتحقق من ده)
# ------------------------------------------------------------

ALIASES: Dict[str, str] = {
    "sugar": "FBG",
    "fasting": "FBG",
    "fbs": "FBG",
    "rbs": "RBG",
    "pp": "PPBG",
    "post prandial": "PPBG",
    "a1c": "HbA1C",
    "hba1c": "HbA1C",
    "sgpt": "ALT (SGPT)",
    "alt": "ALT (SGPT)",
    "sgot": "AST (SGOT)",
    "ast": "AST (SGOT)",
    "alp": "Alkaline Phosphatase (ALP)",
    "creat": "Creatinine (Serum)",
    "creatinine": "Creatinine (Serum)",
    "albumin": "Albumin (ALB)",
    "na": "Na (Sodium)",
    "sodium": "Na (Sodium)",
    "k": "K (Potassium)",
    "potassium": "K (Potassium)",
    "ca": "Calcium (Total)",
    "calcium": "Calcium (Total)",
    "mg": "Magnesium (Mg) serum",
    "phosphorus": "PO4 (Phosphorus)",
    "iron": "Iron (Serum)",
    "vit d": "Vitamin D3(25 Hydroxy Cholecal.)",
    "vitamin d": "Vitamin D3(25 Hydroxy Cholecal.)",
    "vit d3": "Vitamin D3(25 Hydroxy Cholecal.)",
    "b12": "Vitamin B12",
    "vit b12": "Vitamin B12",
    "amylase": "Amylase in (serum)",
    "urine": "Urine Examination",
    "urine analysis": "Urine Examination",
    "stool": "Stool Examination",
    "stool analysis": "Stool Examination",
    "semen": "Semen Examination",
    "widal": "Widal Test",
    "asot": "ASOT(Anti-Streptolysin-O)(Quanti",
    "aso": "ASOT(Anti-Streptolysin-O)(Quanti",
    "cea": "CEA (Carcinoembryonic Antigen)",
    "ana": "ANA (Antinuclear Ab)",
    "troponin": "Troponin (I)",
    "ck mb": "CK (MB)",
    "pregnancy": "Pregnancy in serum Qualit.",
    "bhcg": "Pregnancy in serum Qualit.",

    # ---- عربي: المصطلحات الدارجة اللي العملاء بيكتبوها ----
    # (بتخدم اللصق والبحث العربي مع بعض)
    "صوره دم": "CBC", "صورة دم": "CBC",
    "صوره دم كامله": "CBC", "صورة دم كاملة": "CBC",
    "سي بي سي": "CBC", "تحليل دم": "CBC",
    "سكر صايم": "FBG", "سكر صائم": "FBG", "صايم": "FBG", "صائم": "FBG",
    "سكر صيامي": "FBG", "جلوكوز صايم": "FBG",
    "سكر فاطر": "PPBG", "سكر بعد الاكل": "PPBG", "بعد الاكل": "PPBG",
    "سكر عشوائي": "RBG", "سكر راندوم": "RBG",
    "تراكمي": "HbA1C", "سكر تراكمي": "HbA1C", "هيموجلوبين سكري": "HbA1C",
    "كرياتينين": "Creatinine (Serum)", "كيرياتينين": "Creatinine (Serum)",
    "يوريا": "Urea", "بولينا": "Urea",
    "حمض يوريك": "Uric Acid", "حمض بوليك": "Uric Acid",
    "يوريك اسيد": "Uric Acid", "حمض البوليك": "Uric Acid",
    "فيتامين د": "Vitamin D3(25 Hydroxy Cholecal.)",
    "فيتامين دال": "Vitamin D3(25 Hydroxy Cholecal.)",
    "فيتامين د3": "Vitamin D3(25 Hydroxy Cholecal.)",
    "فيتامين ب12": "Vitamin B12", "ب12": "Vitamin B12",
    "حديد": "Iron (Serum)", "الحديد": "Iron (Serum)",
    "فيريتين": "Ferritin", "مخزون الحديد": "Ferritin", "فريتين": "Ferritin",
    "هيموجلوبين": "Hb (hemoglobin)", "هيموغلوبين": "Hb (hemoglobin)",
    "سرعه الترسيب": "ESR", "سرعة الترسيب": "ESR", "ترسيب": "ESR",
    "فصيله الدم": "ABO", "فصيلة الدم": "ABO", "فصيله": "ABO", "فصيلة": "ABO",
    "تحليل بول": "Urine Examination", "بول": "Urine Examination",
    "تحليل براز": "Stool Examination", "براز": "Stool Examination",
    "مزرعه بول": "Urine Culture", "مزرعة بول": "Urine Culture",
    "مزرعه براز": "Stool Culture", "مزرعة براز": "Stool Culture",
    "سائل منوي": "Semen Examination", "تحليل منوي": "Semen Examination",
    "حمل": "Pregnancy in serum Qualit.", "تحليل حمل": "Pregnancy in serum Qualit.",
    "كالسيوم": "Calcium (Total)", "كالسيوم كلي": "Calcium (Total)",
    "صوديوم": "Na (Sodium)", "بوتاسيوم": "K (Potassium)",
    "ماغنسيوم": "Magnesium (Mg) serum", "مغنسيوم": "Magnesium (Mg) serum",
    "فوسفور": "PO4 (Phosphorus)",
    "كوليسترول": "Cholesterol", "كولسترول": "Cholesterol",
    "دهون ثلاثيه": "Triglycerides", "دهون ثلاثية": "Triglycerides",
    "تراي جليسيريد": "Triglycerides",
    "الغده الدرقيه": "Thyroid Profile", "الغدة الدرقية": "Thyroid Profile",
    "هرمون الحليب": "Prolactin (PRL)", "برولاكتين": "Prolactin (PRL)",
    "اميليز": "Amylase in (serum)", "ليبيز": "Lipase in serum",
    "زمن البروثرومبين": "PT", "سيوله": "PT", "سيولة": "PT",
    "الفا فيتو بروتين": "AFP", "دي دايمر": "D-dimer",
    "زنك": "Zinc (blood)", "الزنك": "Zinc (blood)",
}

# مصطلحات غامضة: ممنوع الاختيار التلقائي، لازم المستخدم يحدد
AMBIGUOUS_TERMS = {
    "psa": "PSA (Free) / PSA (Total) / PSA Ratio",
    "h pylori": "7 صور مختلفة بأسعار من 300 لـ 1750",
    "hpylori": "7 صور مختلفة بأسعار من 300 لـ 1750",
    "pylori": "7 صور مختلفة بأسعار من 300 لـ 1750",
    "rf": "RF (Qualit) 160 / RF (Quantit) 280",
    "hcv": "HCV IgG / HCV IgM / PCR",
    "hbs": "HBs Ag / HBs Ab",
    "hiv": "HIV (I,II) Abs / HIV Combi Ag/Ab",
    "crp": "CRP / hs-CRP",
    "cortisol": "AM / PM / Urine",
    "vitamin d2": "D2 vs D3 - أكد الاختيار",
    # عربي: مصطلحات ليها أكتر من صورة بسعر مختلف
    "زلال": "زلال الدم (Albumin) غير زلال البول (Microalbuminuria)",
    "صفرا": "Bilirubin: Total / Direct / Indirect",
    "صفراء": "Bilirubin: Total / Direct / Indirect",
    "بيليروبين": "Bilirubin: Total / Direct / Indirect",
    "انزيمات الكبد": "ALT / AST / ALP / GGT - حدد أو خد Liver Profile",
    "هرمون الذكوره": "Testosterone Total / Free",
    "هرمون الذكورة": "Testosterone Total / Free",
    "تستوستيرون": "Testosterone Total / Free",
    "الكبد الوبائي": "HBs Ag / HCV IgG - حدد أنهي واحد",
    "فيروسات كبديه": "HBs Ag / HCV IgG - حدد أنهي واحد",
    "املاح": "Na / K / Ca / Mg / PO4 - حدد المطلوب",
    "أملاح": "Na / K / Ca / Mg / PO4 - حدد المطلوب",
    "هرمونات": "حدد الهرمون المطلوب بالاسم",
}


# ------------------------------------------------------------
# 4) Test-name resolution  ==  التحقق من الاسم قبل إدخاله
# ------------------------------------------------------------

MATCH_EXACT = "exact"          # مطابقة أكيدة -> يتضاف على طول
MATCH_ALIAS = "alias"          # اختصار معروف -> يتضاف على طول
MATCH_AMBIGUOUS = "ambiguous"  # أكتر من احتمال -> لازم تأكيد
MATCH_SUGGEST = "suggest"      # قريب بس مش مؤكد -> لازم تأكيد
MATCH_NOT_FOUND = "not_found"  # مش موجود خالص


@dataclass
class Resolution:
    status: str
    query: str
    candidates: List[TestRec] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""

    @property
    def is_confident(self) -> bool:
        return self.status in (MATCH_EXACT, MATCH_ALIAS)

    @property
    def best(self) -> Optional[TestRec]:
        return self.candidates[0] if self.candidates else None


def _same_price(recs: List[TestRec]) -> bool:
    return len({r.price for r in recs}) == 1


def resolve_test(query: str, idx: PriceIndex, cutoff: float = 0.62,
                 max_suggestions: int = 8) -> Resolution:
    """
    بيرجّع نتيجة موصوفة - مش بيخمّن ويضيف من نفسه أبداً.
    الترتيب: exact -> alias -> ambiguous-guard -> prefix/word -> fuzzy -> not found
    """
    q = norm(query)
    if not q:
        return Resolution(MATCH_NOT_FOUND, query, reason="الاسم فاضي")

    # -- Tier 1: exact
    if q in idx.by_key:
        recs = idx.by_key[q]
        if len(recs) == 1 or _same_price(recs):
            return Resolution(MATCH_EXACT, query, [recs[0]], 1.0, "مطابقة تامة")
        return Resolution(MATCH_AMBIGUOUS, query, recs, 1.0,
                          "الاسم مكرر في قائمة الأسعار بأسعار مختلفة")

    # -- Tier 2: alias (شامل aliases الباقات)
    alias_map = idx.aliases or ALIASES
    if q in alias_map:
        target = alias_map[q]
        recs = idx.get(target)
        if recs:
            if len(recs) == 1 or _same_price(recs):
                return Resolution(MATCH_ALIAS, query, [recs[0]], 1.0,
                                  f"اختصار معروف ← {recs[0].name}")
            return Resolution(MATCH_AMBIGUOUS, query, recs, 1.0, "alias بأسعار مختلفة")

    # -- Tier 3: ambiguity guard (نمنع التخمين في المصطلحات الخطرة)
    if q in AMBIGUOUS_TERMS:
        pat = re.compile(r"\b" + r"\s*".join(map(re.escape, q.split())) + r"\b")
        recs = _dedupe([r for r in idx.records if pat.search(norm(r.name))])
        recs = recs[:max_suggestions]
        return Resolution(MATCH_AMBIGUOUS, query, recs, 0.9,
                          f"مصطلح غير محدد: {AMBIGUOUS_TERMS[q]}")

    # -- Tier 4: prefix / whole-word containment
    qtok = set(q.split())
    starts, words = [], []
    for key, recs in idx.by_key.items():
        if key.startswith(q):
            starts.extend(recs)
        elif qtok and qtok.issubset(set(key.split())):
            words.extend(recs)
    hits = _dedupe(starts + words)
    if hits:
        if len(hits) == 1:
            return Resolution(MATCH_SUGGEST, query, hits, 0.85,
                              "نتيجة واحدة قريبة - أكّدها قبل الإضافة")
        return Resolution(MATCH_SUGGEST, query, hits[:max_suggestions], 0.8,
                          f"{len(hits)} نتيجة محتملة - اختار الصح")

    # -- Tier 5: fuzzy
    close = get_close_matches(q, idx.keys, n=max_suggestions, cutoff=cutoff)
    if close:
        recs = _dedupe([r for k in close for r in idx.by_key[k]])
        best_score = SequenceMatcher(None, q, close[0]).ratio()
        return Resolution(MATCH_SUGGEST, query, recs[:max_suggestions], best_score,
                          "مفيش مطابقة تامة - دي أقرب أسماء")

    # -- Tier 6: nothing
    loose = get_close_matches(q, idx.keys, n=5, cutoff=0.35)
    recs = _dedupe([r for k in loose for r in idx.by_key[k]])
    return Resolution(MATCH_NOT_FOUND, query, recs, 0.0,
                      "التحليل ده مش موجود في قائمة الأسعار")


def _dedupe(recs: List[TestRec]) -> List[TestRec]:
    seen, out = set(), []
    for r in recs:
        sig = (norm(r.name), r.price)
        if sig not in seen:
            seen.add(sig)
            out.append(r)
    return sorted(out, key=lambda r: (not r.is_bundle, len(r.name), r.name))


def search_tests(term: str, idx: PriceIndex, limit: int = 60) -> List[TestRec]:
    """بحث حر للعرض في القائمة (substring عادي)."""
    t = norm(term)
    if not t:
        return []
    out = [r for r in idx.records if t in norm(r.name)]
    if not out:
        out = [r for k in get_close_matches(t, idx.keys, n=12, cutoff=0.5)
               for r in idx.by_key[k]]
    return _dedupe(out)[:limit]


# ------------------------------------------------------------
# 4b) Bundle conflict detection  ==  منع الدفع مرتين
# ------------------------------------------------------------

# ------------------------------------------------------------
# 4b) لصق قائمة تحاليل (Copy/Paste من رسالة عميل)
# ------------------------------------------------------------

# فواصل آمنة. ملاحظة: مش بنقسم على "و" — أسماء كتير بتبدأ بيها
# (وظائف، ورم) والقسمة الغلط بتولّد ضجيج أكتر من فايدتها.
_BULK_SPLIT = re.compile(r"[\n\r,،؛;/|+]+")

# ترقيم وبولت في أول السطر: "1." / "1)" / "-" / "•" / "٢-"
_BULK_BULLET = re.compile(r"^\s*(?:[-–—*•·◦●]+|[\d\u0660-\u0669]{1,3}\s*[).\-:،]?)\s*")

# سطور مش تحاليل: تليفونات، تواريخ، أسعار
_BULK_NOISE = re.compile(
    r"^(?:\+?\d[\d\s\-()]{5,}|\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}|"
    r"[\d\u0660-\u0669\s.,]+)$")

BULK_MAX_LINES = 60


def parse_bulk_tests(raw: str, limit: int = BULK_MAX_LINES) -> List[str]:
    """
    بيحوّل نص ملزوق لقائمة أسماء مرشّحة — بيشيل الترقيم والضجيج
    والتكرار بس. مش بيطابق ولا بيخمّن؛ ده شغل resolve_test.
    """
    if not raw or not raw.strip():
        return []

    out, seen = [], set()
    for chunk in _BULK_SPLIT.split(raw):
        s = _BULK_BULLET.sub("", chunk).strip()
        s = s.strip(" \t:-–—•*.،؛?؟\"'()[]")
        if len(s) < 2 or _BULK_NOISE.match(s):
            continue
        if not re.search(r"[a-zA-Z\u0600-\u06FF]", s):   # لازم فيه حروف
            continue
        k = norm(s)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= limit:
            break
    return out


@dataclass
class Conflict:
    kind: str                      # "covered" | "supersedes"
    bundle: str = ""
    names: List[str] = field(default_factory=list)
    saving: int = 0
    message: str = ""


def check_add(items: List[dict], rec: TestRec, idx: PriceIndex) -> Optional[Conflict]:
    """
    بيتشيك قبل الإضافة:
      covered    = التحليل ده داخل في باقة موجودة بالفعل في الفاتورة
      supersedes = الباقة دي بتغطي تحاليل مفرّقة موجودة في الفاتورة
    """
    in_invoice = {norm(i["name"]): i for i in items}

    if rec.is_bundle:
        covered = [i["name"] for k, i in in_invoice.items()
                   if k in rec.component_keys]
        if covered:
            spent = sum(int(in_invoice[norm(n)]["price"]) for n in covered)
            return Conflict(
                "supersedes", rec.name, covered, spent - rec.price,
                f"{len(covered)} تحليل مفرّق في الفاتورة داخلين في {rec.name}")
        return None

    for b in idx.bundles:
        if norm(b.name) in in_invoice and rec.key in b.component_keys:
            return Conflict(
                "covered", b.name, [rec.name], rec.price,
                f"{rec.name} داخل بالفعل في باقة {b.name}")
    return None


def bundle_saving(rec: TestRec, idx: PriceIndex) -> Tuple[int, int]:
    """(سعر المفرّق, التوفير) للباقة."""
    if not rec.is_bundle:
        return (rec.price, 0)
    total = 0
    for c in rec.components:
        hits = idx.get(c)
        if hits:
            total += hits[0].price
    return (total, total - rec.price)


# ------------------------------------------------------------
# 5) Patient name validation
# ------------------------------------------------------------

@dataclass
class FieldCheck:
    ok: bool
    value: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def clean_name(raw: str) -> str:
    s = unicodedata.normalize("NFKC", (raw or "")).strip()
    s = re.sub(r"[^\w\u0600-\u06FF\.\'\- ]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def validate_patient_name(raw: str, min_parts: int = 2) -> FieldCheck:
    """التحقق من اسم العميل قبل الإدخال."""
    name = clean_name(raw)
    errors, warnings = [], []

    if not name:
        return FieldCheck(False, "", ["اسم العميل مطلوب"])

    if _DIGIT_RE.search(name):
        errors.append("الاسم فيه أرقام - امسحها")

    if len(name) < 3:
        errors.append("الاسم قصير جداً (أقل من 3 حروف)")

    parts = [p for p in name.split() if len(p) > 1]
    if len(parts) < min_parts:
        warnings.append(f"يفضّل {min_parts} مقاطع على الأقل (اسم + اسم الأب/العيلة)")

    if len(name) > 60:
        warnings.append("الاسم طويل - ممكن يتقص في الـ PDF")

    ar, en = has_arabic(name), bool(re.search(r"[A-Za-z]", name))
    if ar and en:
        warnings.append("الاسم مخلوط عربي/إنجليزي - وحّده")
    if ar:
        warnings.append("الاسم بالعربي: هيظهر ؟؟؟ في الـ PDF - اكتبه إنجليزي للـ PDF")

    if en and not ar:
        name = " ".join(w if w.isupper() else w.capitalize() for w in name.split())

    return FieldCheck(not errors, name, errors, warnings)


def name_is_pdf_safe(name: str) -> bool:
    """الـ PDF بيستخدم latin-1 - أي حرف بره النطاق هيبقى '?'."""
    try:
        (name or "").encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


# ------------------------------------------------------------
# 6) Phone validation (Egypt-first, international-tolerant)
# ------------------------------------------------------------

EG_MOBILE_PREFIXES = ("10", "11", "12", "15")   # بعد الـ 0


def validate_phone(raw: str, default_cc: str = "20") -> FieldCheck:
    """
    بيرجّع الرقم بصيغة E.164 من غير + (ده اللي wa.me بياخده).
    مقبول: 01012345678 / +201012345678 / 00201012345678 / 201012345678
    """
    s = re.sub(r"[^\d+]", "", unicodedata.normalize("NFKC", raw or "").strip())
    if not s:
        return FieldCheck(False, "", ["رقم التليفون مطلوب لإرسال الواتساب"])

    if s.startswith("00"):
        s = "+" + s[2:]

    intl = s.startswith("+")
    digits = s.lstrip("+")

    if not digits.isdigit():
        return FieldCheck(False, "", ["الرقم فيه حروف أو رموز غير مسموحة"])

    # محلي مصري: 01XXXXXXXXX
    if not intl and digits.startswith("0"):
        local = digits[1:]
        if len(local) != 10 or local[:2] not in EG_MOBILE_PREFIXES:
            return FieldCheck(False, "", [
                "رقم موبايل مصري غير صحيح - لازم 11 رقم يبدأ بـ 010 / 011 / 012 / 015"
            ])
        return FieldCheck(True, default_cc + local)

    # 201XXXXXXXXX من غير +
    if not intl and digits.startswith(default_cc) and len(digits) == 12:
        local = digits[2:]
        if local[:2] not in EG_MOBILE_PREFIXES:
            return FieldCheck(False, "", ["بادئة الشبكة غلط (010/011/012/015)"])
        return FieldCheck(True, digits)

    # 1XXXXXXXXX من غير صفر
    if not intl and len(digits) == 10 and digits[:2] in EG_MOBILE_PREFIXES:
        return FieldCheck(True, default_cc + digits,
                          warnings=["ناقص الصفر - اتضاف تلقائي"])

    # دولي
    if intl or len(digits) > 12:
        if not (8 <= len(digits) <= 15):
            return FieldCheck(False, "", ["طول الرقم الدولي غير منطقي (8-15 رقم)"])
        if digits.startswith(default_cc) and len(digits) == 12:
            if digits[2:4] not in EG_MOBILE_PREFIXES:
                return FieldCheck(False, "", ["بادئة الشبكة المصرية غلط"])
            return FieldCheck(True, digits)
        return FieldCheck(True, digits, warnings=["رقم دولي - اتأكد من كود الدولة"])

    return FieldCheck(False, "", ["صيغة الرقم غير معروفة - اكتبه 01XXXXXXXXX"])


def format_phone_display(e164: str) -> str:
    if e164.startswith("20") and len(e164) == 12:
        return f"+20 {e164[2:5]} {e164[5:8]} {e164[8:]}"
    return "+" + e164


# ------------------------------------------------------------
# 7) Totals
# ------------------------------------------------------------

def compute_totals(items: List[dict], discount_value: float,
                   discount_type: str) -> dict:
    subtotal = sum(int(i["price"]) for i in items)
    if discount_type == "Percentage":
        pct = max(0.0, min(100.0, float(discount_value)))
        discount = subtotal * pct / 100.0
        label = f"خصم {pct:.0f}%"
    else:
        discount = max(0.0, min(float(subtotal), float(discount_value)))
        label = "خصم"
    total = subtotal - discount
    days = [i.get("result_days") for i in items if i.get("result_days")]
    return {
        "subtotal": subtotal,
        "discount": round(discount),
        "discount_label": label,
        "total": round(total),
        "count": len(items),
        "max_days": max(days) if days else None,
        "unpriced": [i["name"] for i in items if int(i["price"]) == 0],
    }


# ------------------------------------------------------------
# 8) WhatsApp
# ------------------------------------------------------------

# wa.me على أندرويد بيتقفل عند ~2000 حرف في الـ URL.
# الحرف العربي بيبقى 9 حروف بعد الـ percent-encoding، فالحد بيتعدى بسرعة.
MAX_WA_URL = 1900


LRM = "\u200e"   # علامة اتجاه: بتمنع قلب التاريخ جوه نص عربي


def build_whatsapp_message(items: List[dict], totals: dict, patient_name: str,
                           lab_name: str = "معمل أورانج للتحاليل الطبية",
                           doctor: str = "", invoice_date: str = "",
                           currency: str = "ج.م", lang: str = "ar",
                           compact: bool = False) -> str:
    # اسم الفرع مايتذكرش للعميل — الاسم التجاري واحد.
    if invoice_date:
        invoice_date = LRM + invoice_date + LRM
    L = []
    if lang == "ar":
        # في الوضع المختصر بنستخدم فواصل ASCII وبنشيل الوحدة من كل سطر،
        # لأن كل حرف عربي بيبقى 9 حروف بعد encoding الـ URL.
        sep = "-" * 18 if compact else "━━━━━━━━━━━━━━━"
        L.append(f"🍊 *{lab_name}*")
        L.append(sep)
        if patient_name:
            L.append(f"الاسم: *{patient_name}*")
        if doctor and not compact:
            L.append(f"الطبيب: {doctor}")
        if invoice_date:
            L.append(f"التاريخ: {invoice_date}")
        L.append("")
        for i, it in enumerate(items, 1):
            # ملحوظة: من غير سعر بجوار كل تحليل عمداً — رسالة الواتساب
            # بتوريك الإجمالي والخصم والمطلوب بس (PDF لسه فيه سعر كل تحليل).
            if compact:
                L.append(f"{i}. {it['name']}")
            else:
                L.append(f"{i}. {it['name']} —")
        L.append(sep)
        L.append(f"الإجمالي: {totals['subtotal']:,} {currency}")
        if totals["discount"] > 0:
            L.append(f"{totals['discount_label']}: -{totals['discount']:,}")
        L.append(f"*المطلوب: {totals['total']:,} {currency}*")
        if totals["max_days"]:
            L.append(f"⏱️ النتيجة خلال {totals['max_days']} يوم")
        notes = [] if compact else _collection_summary(items)
        if notes:
            L.append("")
            L.append("*تعليمات العينة:*")
            L.extend(f"• {n}" for n in notes)
        if not compact:
            L.append("")
            L.append("شكراً لثقتكم 🍊")
    else:
        L.append(f"🍊 *{lab_name}*")
        L.append("-------------------")
        if patient_name:
            L.append(f"Patient: *{patient_name}*")
        for i, it in enumerate(items, 1):
            # نفس المنطق: من غير سعر بجوار كل تحليل في رسالة الواتساب.
            L.append(f"{i}. {it['name']}")
        L.append("-------------------")
        L.append(f"Subtotal: {totals['subtotal']:,} {currency}")
        if totals["discount"] > 0:
            L.append(f"Discount: -{totals['discount']:,} {currency}")
        L.append(f"*TOTAL: {totals['total']:,} {currency}*")
    return "\n".join(L)


def _collection_summary(items: List[dict], limit: int = 5) -> List[str]:
    seen, out = set(), []
    for it in items:
        n = (it.get("collection_notes") or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
        if len(out) >= limit:
            break
    return out


def build_whatsapp_url(phone_e164: str, message: str) -> str:
    """لينك يفتح الشات مع الرقم ده مباشرة."""
    text = urllib.parse.quote(message, safe="")
    if phone_e164:
        return f"https://wa.me/{phone_e164}?text={text}"
    return f"https://wa.me/?text={text}"


def build_whatsapp_link_safe(phone_e164: str, build_msg_fn) -> Tuple[str, str, str]:
    """
    بيجرّب الرسالة الكاملة الأول، ولو الـ URL طويل بيرجع للنسخة المختصرة.
    بيرجّع: (url, message, note)  -- note فاضية يعني تمام.
    """
    full = build_msg_fn(False)
    url = build_whatsapp_url(phone_e164, full)
    if len(url) <= MAX_WA_URL:
        return url, full, ""

    compact = build_msg_fn(True)
    url = build_whatsapp_url(phone_e164, compact)
    if len(url) <= MAX_WA_URL:
        return url, compact, "الرسالة طويلة — اتشالت تعليمات العينة عشان اللينك يشتغل"

    return url, compact, (
        "⚠️ الفاتورة كبيرة جداً على لينك واتساب — "
        "استخدم PDF أو انسخ الرسالة يدوي"
    )
