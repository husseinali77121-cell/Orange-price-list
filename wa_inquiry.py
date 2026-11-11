# wa_inquiry.py
# ============================================================
#  💬 تحليل استفسار الواتساب — الموظف بيلزق المحادثة زي ما هي، والبرنامج بيطلّع:
#    • اسم العميل ورقمه (من سطر «[10:15, 11/11/2026] Ahmed: …» أو من الرسالة نفسها)
#    • وقت رسالة العميل (لحساب سرعة الرد في الداشبورد)
#    • التحاليل المذكورة — حتى جوه جملة («عايز أعرف سعر صورة دم وفيتامين د»)
#    • نية العميل: بيسأل سعر / بيقول غالي / عايز خصم / سحب منزلي / عنوان / صيام… ← الرد المقترح
#    • المنطقة (6 أكتوبر / الشيخ زايد) وهل عايز زيارة منزلية
#    • رقم عرض من القائمة الترحيبية لو كتب رقم لوحده (1–39)
#  قاعدة البرنامج زي ما هي: مفيش تخمين — اللي مش أكيد بيروح لمراجعة الموظف.
#  منطق بحت (من غير streamlit) -> test_whatsapp_suite.py
# ============================================================

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from price_utils import (AMBIGUOUS_TERMS, norm, parse_bulk_tests, resolve_test,
                         validate_patient_name, validate_phone)

# ------------------------------------------------------------
# توحيد الحروف العربية (أ/إ/آ ← ا · ة ← ه · ى ← ي) + أرقام هندية ← إنجليزي
# ------------------------------------------------------------

_AR_DIAC = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_BIDI = re.compile(r"[‎‏‪-‮⁦-⁩﻿]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_AR_PUNCT = re.compile(r"[\u060C\u061B\u061F\u066A-\u066D\u06D4\u06DD\u06DE\u06E9]")   # ، ؛ ؟ ٪ ۔ …


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s or "")).translate(_DIGITS)
    s = _BIDI.sub("", s)
    s = _AR_DIAC.sub("", s)
    s = _AR_PUNCT.sub(" ", s)
    s = re.sub("[أإآٱ]", "ا", s).replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return norm(s)


# ------------------------------------------------------------
# 1) قراءة المحادثة الملزوقة
# ------------------------------------------------------------

_T = r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp]\.?\s?[Mm]\.?|ص|م)?"
_D = r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"
_LINE_RES = [
    re.compile(rf"^\[(?P<time>{_T})\s*[,،]\s*(?P<date>{_D})\]\s*(?P<sender>[^:\n]{{1,60}}?):\s?(?P<msg>.*)$"),  # Web/Desktop copy
    re.compile(rf"^\[(?P<date>{_D})\s*[,،]\s*(?P<time>{_T})\]\s*(?P<sender>[^:\n]{{1,60}}?):\s?(?P<msg>.*)$"),  # iOS export
    re.compile(rf"^(?P<date>{_D})\s*[,،]?\s+(?P<time>{_T})\s*[-–]\s*(?P<sender>[^:\n]{{1,60}}?):\s?(?P<msg>.*)$"),  # Android export
]
LAB_SENDER_HINTS = ("orange", "اورانج", "أورانج", "معمل", "lab", "you", "انت", "أنت")
_MEDIA = re.compile(r"<\s*(media omitted|تم استبعاد الوسائط)\s*>|image omitted|صوره محذوفه|‎?IMG-\d+|\.(jpe?g|png|pdf)\b",
                    re.I)
_PHONE_IN_TEXT = re.compile(r"(?<!\d)(\+?\d[\d \-]{8,16}\d)(?!\d)")
_NAME_IN_TEXT = re.compile(r"(?:الاسم|اسم المريض|اسمي|اسمى|name)\s*[:：\-]?\s*([^\n\d,،:]{3,40})", re.I)


def _to_dt(date_s: str, time_s: str, now: datetime) -> Optional[datetime]:
    """تاريخ واتساب ممكن يبقى يوم/شهر أو شهر/يوم حسب لغة الجهاز — بناخد الأقرب للنهاردة (من غير مستقبل)."""
    try:
        a, b, y = [int(x) for x in re.split(r"[/.\-]", date_s)]
    except ValueError:
        return None
    y = y + 2000 if y < 100 else y
    t = time_s.strip().lower().replace(".", "").replace(" ", "")
    pm = t.endswith("pm") or t.endswith("م")
    am = t.endswith("am") or t.endswith("ص")
    t = re.sub(r"(am|pm|ص|م)$", "", t)
    try:
        parts = [int(x) for x in t.split(":")]
    except ValueError:
        return None
    hh, mm = parts[0], parts[1]
    if pm and hh < 12:
        hh += 12
    if am and hh == 12:
        hh = 0
    cands = []
    for d, m in ((a, b), (b, a)):
        try:
            cands.append(datetime(y, m, d, hh, mm))
        except ValueError:
            pass
    ok = [c for c in cands if c <= now + timedelta(minutes=5)]
    if not ok:
        return None
    return min(ok, key=lambda c: now - c)


def _is_lab(sender: str) -> bool:
    s = fold(sender)
    return any(fold(h) in s.split() or (len(fold(h)) > 3 and fold(h) in s) for h in LAB_SENDER_HINTS)


def parse_chat(raw: str, now: Optional[datetime] = None) -> dict:
    """
    بيرجّع: {customer_text, sender, name, phone (E.164 من غير +), inquiry_ts (datetime|None),
             has_media, structured (هل الملزوق فيه سطور واتساب بتاريخ)}
    customer_text = رسايل العميل بس (من غير ردود المعمل) — آخر مجموعة رسايل لسه ماتردّش عليها
    بتتحسب لوقت الاستفسار.
    """
    now = now or datetime.now()
    text = _BIDI.sub("", unicodedata.normalize("NFKC", raw or "")).translate(_DIGITS)
    msgs: List[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = next((rx.match(line) for rx in _LINE_RES if rx.match(line)), None)
        if m:
            msgs.append({"sender": m.group("sender").strip(), "msg": m.group("msg").strip(),
                         "ts": _to_dt(m.group("date"), m.group("time"), now)})
        elif msgs:
            msgs[-1]["msg"] += "\n" + line                     # تكملة رسالة متعددة السطور
        else:
            msgs.append({"sender": "", "msg": line, "ts": None})
    structured = any(x["sender"] for x in msgs)
    senders: Dict[str, int] = {}
    for x in msgs:
        if x["sender"] and not _is_lab(x["sender"]):
            senders[x["sender"]] = senders.get(x["sender"], 0) + 1
    sender = max(senders, key=lambda k: (senders[k], -[x["sender"] for x in msgs].index(k))) if senders else ""
    cust = [x for x in msgs if (x["sender"] == sender) or not x["sender"]] if structured else msgs
    customer_text = "\n".join(x["msg"] for x in cust).strip()

    # وقت الاستفسار: أول رسالة للعميل بعد آخر رد من المعمل
    inquiry_ts = None
    last_lab = max((i for i, x in enumerate(msgs) if x["sender"] and x["sender"] != sender), default=-1)
    for x in msgs[last_lab + 1:]:
        if x["sender"] == sender and x["ts"]:
            inquiry_ts = x["ts"]
            break
    if inquiry_ts is None:
        inquiry_ts = next((x["ts"] for x in cust if x["ts"]), None)

    phone, name = "", ""
    if sender:
        pv = validate_phone(sender)
        if pv.ok and re.search(r"\d{7,}", re.sub(r"\D", "", sender)):
            phone = pv.value
        else:
            nm = re.sub(r"[^\w؀-ۿ .'\-]", " ", sender).strip()
            if validate_patient_name(nm, min_parts=1).ok:
                name = validate_patient_name(nm, min_parts=1).value
    if not phone:
        for m in _PHONE_IN_TEXT.finditer(customer_text):
            pv = validate_phone(m.group(1))
            if pv.ok:
                phone = pv.value
                break
    if not name:
        m = _NAME_IN_TEXT.search(customer_text)
        if m:
            raw_name = re.split(r"\s+(?:و?رقمي|و?رقم|و?تليفوني|و?تليفون|و?موبايلي|و?موبايل|عايز|عاوز|محتاج|عايزة|عاوزة)\b",
                                m.group(1).strip())[0]
            cand = validate_patient_name(raw_name.strip(), min_parts=1)
            if cand.ok:
                name = cand.value
    return {"customer_text": customer_text, "sender": sender, "name": name, "phone": phone,
            "inquiry_ts": inquiry_ts, "has_media": bool(_MEDIA.search(text)), "structured": structured}


# ------------------------------------------------------------
# 2) نية العميل ← الرد المقترح (replies.py)
# ------------------------------------------------------------

# (نية, رد مقترح, كلمات) — الكلمات بتتطابق بعد fold. الترتيب = الأولوية في الاقتراح.
INTENTS: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("stop", "stop_messages", ("ايقاف", "وقف الرسايل", "وقف الرسائل", "متبعتوش", "مش عايز رسايل", "stop", "unsubscribe")),
    ("complaint", "delay_apology", ("محدش رد", "اتاخرتوا", "متاخرين", "لسه مستني", "مستني من", "شكوي", "زعلان")),
    ("price_high", "price_high", ("غالي", "غاليه", "غالين", "كتير اوي", "مبالغ", "expensive", "too much", "too expensive")),
    ("competitor", "cheaper_elsewhere", ("ارخص", "معمل تاني", "مكان تاني", "معامل تانيه", "cheaper", "another lab")),
    ("discount", "ask_discount", ("خصم", "تخفيض", "عروض", "عرض", "discount", "offer", "offers")),
    ("postpone", "will_think", ("هفكر", "هشوف واقولك", "هرد عليك", "هبقي اكلمكم", "هبقي ارد", "بعدين", "let me think")),
    ("no_time", "no_time", ("مشغول", "مفيش وقت", "معنديش وقت", "مش فاضي", "busy")),
    ("prep", "prep", ("صيام", "صايم", "اصوم", "افطر", "قبل التحليل", "fasting", "fast")),
    ("result_time", "result_time", ("النتيجه امتي", "امتي النتيجه", "النتيجه بتطلع", "هتطلع امتي", "بتاخد قد ايه",
                                    "النتايج امتي", "how long", "when results")),
    ("result", "result_inquiry", ("النتيجه", "نتيجه", "النتايج", "استلم", "طلعت", "result", "results")),
    ("home_visit", "home_visit", ("منزلي", "منزليه", "البيت", "بيتي", "المنزل", "تيجوا", "تيجو", "home visit", "home")),
    ("book", "want_book", ("احجز", "حجز", "ميعاد", "موعد", "اجي امتي", "ينفع اجي", "book", "appointment")),
    ("location", "branch_info", ("عنوان", "العنوان", "فين", "مكانكم", "لوكيشن", "لوكيشان", "مواعيد", "بتفتحوا",
                                 "بتقفلوا", "شغالين", "location", "address", "open")),
    ("prescription", "prescription_received", ("روشته", "الروشته", "prescription")),
    ("price", "ask_prices", ("بكام", "سعر", "اسعار", "الاسعار", "تكلفه", "التكلفه", "كام", "price", "prices",
                             "how much", "cost")),
    ("thanks", "thanks", ("شكرا", "متشكر", "متشكرين", "تسلم", "تسلمي", "thanks", "thank you")),
    ("greeting", "welcome", ("السلام عليكم", "صباح الخير", "مساء الخير", "اهلا", "مرحبا", "hello", "hi")),
]


def detect_intents(text: str, *, has_media: bool = False) -> List[dict]:
    """[{intent, reply, keyword}] بالأولوية — من غير تكرار للرد."""
    t = " " + fold(text) + " "
    out, seen = [], set()
    for intent, reply, kws in INTENTS:
        for kw in kws:
            k = fold(kw)
            if k and re.search(r"(?<![\w؀-ۿ])" + re.escape(k) + r"(?![\w؀-ۿ])", t) \
                    or (len(k) >= 5 and " " not in k and k in t):
                if reply not in seen:
                    out.append({"intent": intent, "reply": reply, "keyword": kw})
                    seen.add(reply)
                break
    if has_media:                                   # بعت صورة (روشتة غالباً) = أول رد «وصلتنا الروشتة»
        out = [x for x in out if x["reply"] != "prescription_received"]
        out.insert(0, {"intent": "prescription", "reply": "prescription_received", "keyword": "📎 صورة"})
    # تحية لوحدها بتتشال لو فيه نية أوضح
    if len(out) > 1:
        out = [x for x in out if x["intent"] != "greeting"]
    return out


AREA_HINTS = {
    "Sheikh Zayed": ("زايد", "الشيخ زايد", "sheikh zayed", "zayed", "بيفرلي", "الحي المتميز"),
    "6 October": ("اكتوبر", "6 اكتوبر", "السادس من اكتوبر", "october", "الحصري", "دريم لاند", "الحي ال"),
}


def detect_area(text: str, areas: List[str]) -> str:
    t = fold(text)
    for area, kws in AREA_HINTS.items():
        if area in areas and any(fold(k) in t for k in kws):
            return area
    return ""


def wants_home_visit(text: str) -> bool:
    return any(x["intent"] == "home_visit" for x in detect_intents(text))


def offer_number(text: str, max_no: int = 39) -> Optional[int]:
    """العميل كتب رقم من القائمة الترحيبية لوحده (سطر = رقم 1–39، أو «عرض 5»)."""
    for line in (text or "").translate(_DIGITS).splitlines():
        m = re.fullmatch(r"\s*(?:عرض|رقم|offer|no\.?)?\s*(\d{1,2})\s*[.)\-]?\s*", line, re.I)
        if m and 1 <= int(m.group(1)) <= max_no:
            return int(m.group(1))
    return None


# ------------------------------------------------------------
# 3) التحاليل جوه كلام عادي
# ------------------------------------------------------------

STOP = {fold(w) for w in (
    "السلام عليكم ورحمة الله وبركاته صباح مساء الخير النور اهلا مرحبا هاي لو سمحت سمحتي من فضلك ممكن "
    "عايز عاوز عايزة عاوزة محتاج محتاجة اعرف سعر اسعار الاسعار السعر بكام كام تحليل تحاليل التحليل التحاليل "
    "و او يا دكتور دكتورة ده دي دا هو هي ايه عندكم عندك فيه في مع انا احنا شكرا تمام اوكي هل يعني طيب بس "
    "كمان برضه ازاي امتي فين حضرتك حضرتكم لكم ليه بتاع بتاعت اعمل نعمل اسال عن على علي الى الي للتحاليل "
    "please pls price prices test tests the of for how much and or i want need is what cost a an to do you have "
    "hi hello thanks ok").split()}
# كلمات بتتفهم تحليل لو جت لوحدها، بس في جملة غالباً معناها حاجة تانية («لازم أكون صايم؟»)
CONTEXT_ONLY = {fold(w) for w in ("صايم", "صائم", "fasting", "fast", "حمل", "بعد الاكل", "بول", "حديد", "الحديد",
                                  "urine", "stool", "iron", "sugar", "calcium", "albumin")}

_LOOKUP_CACHE: Dict[int, Dict[str, str]] = {}


def _lookup(idx) -> Dict[str, str]:
    """fold(اسم أو اختصار) ← الاسم في قائمة الأسعار (بتتبني مرة لكل فهرس)."""
    key = id(idx)
    if key not in _LOOKUP_CACHE:
        lk: Dict[str, str] = {}
        for k, recs in idx.by_key.items():
            lk.setdefault(fold(k), recs[0].name)
        for a, target in (idx.aliases or {}).items():
            lk.setdefault(fold(a), target)
        _LOOKUP_CACHE[key] = lk
    return _LOOKUP_CACHE[key]


_AMBIG = {fold(k) for k in AMBIGUOUS_TERMS}


def extract_tests(text: str, idx, *, max_words: int = 5) -> dict:
    """
    بيدوّر على أسماء/اختصارات تحاليل جوه جملة (أطول تطابق الأول، من غير تداخل).
    confident = مطابقة تامة/اختصار معروف · choose = مصطلح غامض (لازم الموظف يحدد).
    """
    words = [w for w in fold(text).split() if w]
    lk = _lookup(idx)
    confident, choose, i = [], [], 0
    while i < len(words):
        hit = None
        for L in range(min(max_words, len(words) - i), 0, -1):
            phrase = " ".join(words[i:i + L])
            variants = [phrase]
            if phrase.startswith("و") and len(phrase) > 3:          # «وفيتامين د» ← «فيتامين د»
                variants.append(phrase[1:])
            if phrase.startswith("ال") and len(phrase) > 4:
                variants.append(phrase[2:])
            for v in variants:
                if len(v) < 3 or v in STOP or (L == 1 and v in CONTEXT_ONLY):
                    continue
                if v in _AMBIG:
                    hit = ("choose", v, L)
                    break
                if v in lk:
                    hit = ("ok", lk[v], L)
                    break
            if hit:
                break
        if hit:
            kind, val, L = hit
            orig = " ".join(words[i:i + L])
            if kind == "ok":
                hits = idx.get(val)
                r = resolve_test(val, idx)
                if r.is_confident:
                    confident.append((orig, r.best))
                elif r.candidates:
                    choose.append((orig, r.candidates[:6], r.reason))
                elif hits:
                    confident.append((orig, hits[0]))
            else:
                r = resolve_test(val, idx)
                if r.candidates:
                    choose.append((orig, r.candidates[:6], r.reason))
            i += L
        else:
            i += 1
    return {"confident": confident, "choose": choose}


def analyze_tests(text: str, idx) -> dict:
    """
    نفس شكل «الصق قائمة» في الفاتورة: {"confident": [(نص, TestRec)], "choose": [(نص, [TestRec], سبب)],
    "missing": [نص]}. القوائم (سطر/فاصلة لكل تحليل) بتتقرا سطر سطر، والجمل بيدوّر جواها.
    الكلام العادي اللي مفيهوش تحليل بيتجاهل (مش بيتحط في «مش لاقيله مقابل»).
    """
    conf, choose, missing, seen = [], [], [], set()

    def add_conf(tok, rec):
        if rec.key not in seen:
            seen.add(rec.key)
            conf.append((tok, rec))

    listy = _looks_like_list(text)
    for tok in parse_bulk_tests(text):
        words = fold(tok).split()
        if not words or all(w in STOP for w in words):
            continue
        r = resolve_test(tok, idx)
        if r.is_confident:
            if len(words) == 1 and words[0] in CONTEXT_ONLY and not listy:
                choose.append((tok, [r.best], "كلمة ممكن تكون سؤال مش اسم تحليل — أكّدها"))
            else:
                add_conf(tok, r.best)
            continue
        found = extract_tests(tok, idx)
        if found["confident"] or found["choose"]:
            for t, rec in found["confident"]:
                add_conf(t, rec)
            choose.extend(c for c in found["choose"] if fold(c[0]) not in {fold(x[0]) for x in choose})
        elif len(words) <= 3 and not _MEDIA.search(tok) and not _chatty(tok):
            if r.candidates and r.status != "not_found":
                choose.append((tok, r.candidates[:6], r.reason))
            else:
                missing.append(tok)
    return {"confident": conf, "choose": choose, "missing": missing}


def _chatty(tok: str) -> bool:
    """سطر كلام (فيه كلمة نية زي «روشتة» أو «غالية») مش اسم تحليل — مايتحطش في «مش لاقيله مقابل»."""
    return bool(detect_intents(tok))


def _looks_like_list(text: str) -> bool:
    lines = [x for x in (text or "").splitlines() if x.strip()]
    return len(lines) >= 2 and sum(len(x.split()) <= 4 for x in lines) >= 0.6 * len(lines)


# ------------------------------------------------------------
# 4) كله مع بعض
# ------------------------------------------------------------

def analyze_inquiry(raw: str, idx, *, areas: Optional[List[str]] = None,
                    now: Optional[datetime] = None) -> dict:
    """تحليل كامل للمحادثة الملزوقة — القيم اللي الفاتورة بتملاها."""
    chat = parse_chat(raw, now=now)
    txt = chat["customer_text"]
    intents = detect_intents(txt, has_media=chat["has_media"])
    return {**chat,
            "tests": analyze_tests(txt, idx),
            "intents": intents,
            "area": detect_area(txt, list(areas or [])),
            "home_visit": any(x["intent"] == "home_visit" for x in intents),
            "offer_no": offer_number(txt)}
