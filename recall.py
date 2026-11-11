# recall.py
# ============================================================
#  🔁 تذكير التحاليل الدورية (Recall) — أكبر مصدر عملاء راجعين للمعمل:
#  عميل حضر وعمل HbA1c من 3 شهور ← رسالة «ميعاد المتابعة الدورية». منطق بحت (من غير
#  streamlit) -> test_whatsapp_suite.py
#
#  ⚠️ الفترات دي مواعيد تذكير افتراضية (مش توصية طبية لمريض بعينه) — راجعها وعدّلها من هنا.
#  الرسالة نفسها بتقول «لو الدكتور طالب متابعة دورية»، ومابتقولش للعميل يعمل تحليل.
# ============================================================

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from price_utils import norm
from tracking import optout_keys, quote_records, stage_of

# كل قاعدة: أسماء التحاليل (أو الباقات) اللي بتفعّلها + بعد كام يوم من آخر زيارة
RECALL_RULES: List[dict] = [
    {"id": "hba1c", "label": "السكر التراكمي (HbA1c)", "days": 90, "tests": ["HbA1C"]},
    {"id": "vitd", "label": "فيتامين د", "days": 90, "tests": ["Vitamin D3(25 Hydroxy Cholecal.)"]},
    {"id": "iron", "label": "مخزون الحديد", "days": 90, "tests": ["Ferritin", "Iron (Serum)"]},
    {"id": "b12", "label": "فيتامين ب12", "days": 90, "tests": ["Vitamin B12"]},
    {"id": "lipid", "label": "الدهون", "days": 180,
     "tests": ["Lipid Profile", "Cholesterol", "Triglycerides", "LDL", "HDL"]},
    {"id": "thyroid", "label": "الغدة الدرقية", "days": 180, "tests": ["Thyroid Profile", "TSH"]},
    {"id": "kidney", "label": "وظائف الكلى", "days": 180,
     "tests": ["Kidney Profile", "Creatinine (Serum)", "Urea"]},
    {"id": "liver", "label": "وظائف الكبد", "days": 180, "tests": ["Liver Profile", "ALT (SGPT)", "AST (SGOT)"]},
]


def _rule_hits(rule: dict, items) -> bool:
    keys = {norm(t) for t in rule["tests"]}
    return any(norm(i) in keys for i in items or [])


def recall_due(events: List[dict], *, now: Optional[datetime] = None, rules: Optional[List[dict]] = None,
               lead_days: int = 7, cooldown_days: int = 30, max_age_days: int = 400) -> List[dict]:
    """
    العملاء اللي ميعاد تحليلهم الدوري قرّب أو عدّى:
      آخر زيارة (stage visited) فيها تحليل من القاعدة + days ≤ النهاردة + lead_days،
      ومارجعش عمل نفس التحليل بعدها، ومش موقوف، ومااتبعتلوش تذكير لنفس القاعدة من cooldown_days.
    كل عنصر: {pk, rule, label, last_visit, due, overdue_days, items, contact, branch, quote_id}
    """
    now = now or datetime.now()
    rules = rules or RECALL_RULES
    opted = optout_keys(events)
    contacted: Dict[tuple, str] = {}
    for e in events:
        if e.get("type") == "recall_contact" and e.get("pk"):
            k = (e["pk"], (e.get("meta") or {}).get("rule", ""))
            contacted[k] = max(contacted.get(k, ""), e.get("ts", ""))
    by_pk: Dict[str, List[dict]] = {}
    contacts: Dict[str, dict] = {}
    for r in quote_records(events).values():
        if not r["pk"]:
            continue
        if r["contact"]:
            contacts.setdefault(r["pk"], r["contact"])
        if stage_of(r) == "visited" and r["decision_ts"]:
            by_pk.setdefault(r["pk"], []).append(r)
    cool = (now - timedelta(days=cooldown_days)).isoformat(timespec="seconds")
    oldest = (now - timedelta(days=max_age_days)).isoformat(timespec="seconds")
    out = []
    for pk, visits in by_pk.items():
        if pk in opted:
            continue
        for rule in rules:
            hits = [v for v in visits if _rule_hits(rule, v["items"])]
            if not hits:
                continue
            last = max(hits, key=lambda v: v["decision_ts"])
            if last["decision_ts"] < oldest:
                continue
            last_dt = datetime.fromisoformat(last["decision_ts"])
            due = last_dt + timedelta(days=int(rule["days"]))
            if due > now + timedelta(days=lead_days):
                continue
            if contacted.get((pk, rule["id"]), "") > cool:
                continue
            out.append({"pk": pk, "rule": rule["id"], "label": rule["label"], "days": int(rule["days"]),
                        "last_visit": last["decision_ts"], "due": due,
                        "overdue_days": max(0, (now - due).days), "items": last["items"],
                        "contact": last["contact"] or contacts.get(pk) or {}, "branch": last["branch"],
                        "quote_id": last["quote_id"]})
    out.sort(key=lambda x: x["due"])
    return out


def recall_message(*, lab: str, name: str = "", label: str, months: int, branch_text: str = "",
                   home_visit: bool = True) -> str:
    """رسالة تذكير لطيفة — من غير ما نقول للعميل إنه «لازم» يعمل التحليل."""
    first = (name or "").strip().split(" ")[0] if (name or "").strip() else ""
    greet = f"أهلاً {first} 🍊" if first else "أهلاً بحضرتك 🍊"
    when = f"{months} شهور" if months != 1 else "شهر"
    lines = [greet, f"من {lab}",
             f"عدّى حوالي {when} على تحليل {label} اللي عملته معانا. "
             "لو الدكتور طالب منك متابعة دورية، حابين نفكّرك إن ده ميعادها المعتاد 🙏"]
    lines.append("تحب نحجزلك ميعاد في الفرع" + (" أو سحب منزلي؟ 🏠" if home_visit else "؟"))
    if branch_text:
        lines += ["", branch_text]
    lines.append("لو مش حابب نفكّرك تاني ابعتلنا «إيقاف».")
    return "\n".join(lines)
