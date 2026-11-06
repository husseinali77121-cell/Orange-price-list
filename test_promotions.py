#!/usr/bin/env python3
"""
اختبار: محرك العروض + سياسة الخصم + فحص جودة الأسعار + مكتبة الحملات +
        كتابة GitHub بالـ CAS (على requests وهمية) + بوابة كلمة السر.
    python3 test_promotions.py
"""
import base64
import json
import random
import sys
import types
from datetime import date, datetime

import access
import github_store as gs
import promotions as pr
from bundles import BUNDLE_CATEGORY, BUNDLES
from campaign_library import CAMPAIGNS, DISCLAIMER, campaign_fields
from labs_price_list import LABS_DB
from marketing_templates import SAMPLE_PHOTOS, TEMPLATES, render_template
from price_audit import audit_prices, summarize_audit
from price_utils import build_index, resolve_test

fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label:64} got={got}")
    if not ok:
        fails.append((label, got, want))


def raises(label, fn, contains=""):
    try:
        fn()
        check(label, "no error", "ValueError")
    except ValueError as e:
        check(label, contains in str(e), True)


IDX = build_index(LABS_DB, BUNDLES, BUNDLE_CATEGORY)
NOW = datetime(2026, 11, 5, 10, 0)
TODAY = date(2026, 11, 5)

# ------------------------------------------------------------
# 1) إنشاء عرض + التحقق
# ------------------------------------------------------------
p = pr.new_promotion(name="Lipid Nov", target="Lipid Profile", original_price=950,
                     promo_price=700, start="2026-11-01", end="2026-11-30",
                     branches=["Diamond"], now=NOW, rng=random.Random(3))
check("id shape", p["id"].startswith("PR-261105-") and len(p["id"]) == 14, True)
check("discount pct", pr.promo_discount_pct(p), 26.3)
check("branches stored sorted", p["branches"], ["Diamond"])
raises("promo >= original rejected", lambda: pr.new_promotion(
    name="x", target="CBC", original_price=400, promo_price=400, start="2026-11-01", end="2026-11-02"),
    "أقل من السعر الأصلي")
raises("zero promo rejected", lambda: pr.new_promotion(
    name="x", target="CBC", original_price=400, promo_price=0, start="2026-11-01", end="2026-11-02"), "أكبر من صفر")
raises("end before start rejected", lambda: pr.new_promotion(
    name="x", target="CBC", original_price=400, promo_price=300, start="2026-11-05", end="2026-11-01"), "النهاية")
raises("no name rejected", lambda: pr.new_promotion(
    name=" ", target="CBC", original_price=400, promo_price=300, start="2026-11-01", end="2026-11-02"), "اسم")
raises("unpriced target rejected", lambda: pr.new_promotion(
    name="x", target="CBC", original_price=0, promo_price=300, start="2026-11-01", end="2026-11-02"), "سعر")
raises("below floor rejected", lambda: pr.new_promotion(
    name="x", target="CBC", original_price=400, promo_price=100, floor_price=250,
    start="2026-11-01", end="2026-11-02"), "الحد الأدنى")

# ------------------------------------------------------------
# 2) الحالة بالتاريخ والفرع (التواريخ شاملة)
# ------------------------------------------------------------
check("active inside range", pr.promo_state(p, TODAY), "active")
check("active on first day", pr.promo_state(p, date(2026, 11, 1)), "active")
check("active on last day", pr.promo_state(p, date(2026, 11, 30)), "active")
check("expired day after", pr.promo_state(p, date(2026, 12, 1)), "expired")
check("scheduled before", pr.promo_state(p, date(2026, 10, 31)), "scheduled")
check("paused beats dates", pr.promo_state({**p, "status": "paused"}, TODAY), "paused")
check("cancelled beats dates", pr.promo_state({**p, "status": "cancelled"}, TODAY), "cancelled")

promos = [p]
check("applies in its branch", [x["id"] for x in pr.active_promotions(promos, "Diamond", TODAY)], [p["id"]])
check("hidden in other branch", pr.active_promotions(promos, "Orange (La Cité)", TODAY), [])
allb = pr.new_promotion(name="CBC all", target="CBC", original_price=400, promo_price=300,
                        start="2026-11-01", end="2026-11-30", now=NOW)
check("no branches = all branches", len(pr.active_promotions([allb], "Orange (La Cité)", TODAY)), 1)
check("expired not active", pr.active_promotions(promos, "Diamond", date(2026, 12, 2)), [])

cheap = {**p, "id": "PR-2", "promo_price": 650}
check("best promo = cheapest", pr.best_promo_for([p, cheap], "lipid profile", "Diamond", TODAY)["id"], "PR-2")
check("best promo none for other target", pr.best_promo_for([p], "CBC", "Diamond", TODAY), None)

# ------------------------------------------------------------
# 3) تقاطع العروض + انحراف القائمة + upsert/status
# ------------------------------------------------------------
dup = pr.new_promotion(name="again", target="Lipid Profile", original_price=950, promo_price=720,
                       start="2026-11-20", end="2026-12-10", branches=["Diamond"], now=NOW)
check("overlap detected (same target/branch/dates)", [x["id"] for x in pr.overlaps(promos, dup)], [p["id"]])
other_branch = {**dup, "branches": ["Orange (La Cité)"]}
check("no overlap on different branch", pr.overlaps(promos, other_branch), [])
later = {**dup, "start": "2026-12-01"}
check("no overlap on later dates", pr.overlaps(promos, later), [])
check("cancelled promo ignored in overlap", pr.overlaps([{**p, "status": "cancelled"}], dup), [])

lip = resolve_test("Lipid Profile", IDX).best
real = pr.new_promotion(name="real", target="Lipid Profile", original_price=lip.price + 100,
                        promo_price=lip.price - 1, start="2026-11-01", end="2026-11-30", now=NOW)
check("drift: list price changed", any("اتغيّر" in w for w in pr.drift_warnings(real, IDX)), True)
ok_p = pr.new_promotion(name="ok", target="Lipid Profile", original_price=lip.price + 50,
                        promo_price=lip.price - 50, start="2026-11-01", end="2026-11-30", now=NOW)
check("drift: promo price >= current list price", any("مش أقل" in w for w in pr.drift_warnings(
    {**ok_p, "original_price": lip.price, "promo_price": lip.price + 10}, IDX)), True)
check("drift: unknown target", "مش موجود" in pr.drift_warnings({**p, "target": "Nope Test"}, IDX)[0], True)
fresh = pr.new_promotion(name="fresh", target="CBC", original_price=resolve_test("CBC", IDX).best.price,
                         promo_price=300, start="2026-11-01", end="2026-11-30", now=NOW)
check("drift: clean promo has no warnings", pr.drift_warnings(fresh, IDX), [])

lst = pr.upsert([p], {**p, "promo_price": 690})
check("upsert replaces by id", (len(lst), lst[0]["promo_price"]), (1, 690))
check("set_status pauses", pr.set_status([p], p["id"], "paused")[0]["status"], "paused")
raises("bad status", lambda: pr.set_status([p], p["id"], "deleted"), "unknown")
order = pr.sorted_for_display([{**p, "id": "e", "end": "2026-10-01", "start": "2026-09-01"}, p], TODAY)
check("display order: active first", order[0]["id"], p["id"])

# ------------------------------------------------------------
# 4) سياسة الخصم
# ------------------------------------------------------------
tot = {"subtotal": 1000, "discount": 250}
check("25% > 20% limit needs approval", pr.needs_approval(tot, 20), True)
check("20% at limit doesn't", pr.needs_approval({"subtotal": 1000, "discount": 200}, 20), False)
check("limit 0 = disabled", pr.needs_approval(tot, 0), False)
check("empty invoice safe", pr.needs_approval({"subtotal": 0, "discount": 0}, 20), False)
check("pin ok", pr.pin_ok("1234", "1234"), True)
check("pin wrong", pr.pin_ok("1235", "1234"), False)
check("pin empty expected never ok", pr.pin_ok("", ""), False)

# ------------------------------------------------------------
# 5) فحص الأسعار على القاعدة الحقيقية (نفس أرقام المراجعة)
# ------------------------------------------------------------
sm = summarize_audit(audit_prices(IDX))
check("audit: zero-price items", sm.get("zero_price"), 16)
check("audit: no result_days", sm.get("no_result_days"), 34)
check("audit: no collection notes", sm.get("no_collection_notes"), 48)
check("audit: duplicates with different prices", sm.get("duplicate_diff_price"), 4)
check("audit: Thyroid has no saving", sm.get("bundle_no_saving"), 1)
check("audit: no missing bundle components", sm.get("bundle_component_missing", 0), 0)
check("audit: high severity first", audit_prices(IDX)[0]["severity"], "high")

tiny = build_index({"X": [{"name": "A", "price": 100, "result_days": 1, "collection_notes": "n"},
                          {"name": "B", "price": 100, "result_days": 1, "collection_notes": "n"}]},
                   [{"name": "AB", "price": 250, "components": ["A", "B", "Ghost"], "result_days": 1}], "P")
kinds = {i["kind"] for i in audit_prices(tiny)}
check("audit: missing component flagged", "bundle_component_missing" in kinds, True)
tiny2 = build_index({"X": [{"name": "A", "price": 100, "result_days": 1, "collection_notes": "n"},
                           {"name": "B", "price": 100, "result_days": 1, "collection_notes": "n"}]},
                    [{"name": "AB", "price": 250, "components": ["A", "B"], "result_days": 1}], "P")
check("audit: bundle pricier than parts", "bundle_pricier" in {i["kind"] for i in audit_prices(tiny2)}, True)

# ------------------------------------------------------------
# 6) مكتبة الحملات
# ------------------------------------------------------------
check("8 seasonal campaigns", len(CAMPAIGNS), 8)
for key, c in CAMPAIGNS.items():
    check(f"library {key}: template valid", c["template"] in TEMPLATES, True)
    check(f"library {key}: photo valid", c.get("photo", "sugar") in SAMPLE_PHOTOS, True)
    for t in c.get("tests", []):
        r = resolve_test(t, IDX)
        check(f"library {key}: test '{t}' resolves exactly", (r.is_confident and r.best.name == t), True)
    f = campaign_fields(key)
    img = render_template(f.pop("template"), "post", f)
    check(f"library {key}: renders", img.size, (1080, 1080))
check("disclaimer text exists", "استشارة الطبيب" in DISCLAIMER, True)
check("medical campaigns flagged for review",
      {k for k, c in CAMPAIGNS.items() if c.get("review")}, {"pregnancy", "children"})

# ------------------------------------------------------------
# 6b) تعليمات الأسعار: مفيش claims بأسعار ثابتة جوه المكتبة
# ------------------------------------------------------------
check("library has no hard-coded discount numbers except percent presets",
      all(not c.get("badge_value") or c["badge_mode"] == "percent" for c in CAMPAIGNS.values()), True)

# ------------------------------------------------------------
# 7) GitHub store: append/update بالـ CAS (على requests وهمية)
# ------------------------------------------------------------

class FakeResp:
    def __init__(self, code, payload=None):
        self.status_code, self._p, self.text = code, payload or {}, json.dumps(payload or {})

    def json(self):
        return self._p


class FakeGitHub:
    """ملفات بنسخة sha لكل مسار؛ بيرفض أي PUT بـ sha قديم (409) ويقدر يحاكي سباق."""

    class RequestException(Exception):
        pass

    def __init__(self):
        self.files, self.puts, self.race_once = {}, 0, False

    @staticmethod
    def _path(url):
        return url.split("/contents/")[1]

    def get(self, url, headers=None, params=None, timeout=None):
        f = self.files.get(self._path(url))
        if f is None:
            return FakeResp(404)
        return FakeResp(200, {"content": base64.b64encode(f["content"]).decode(), "sha": f"v{f['v']}"})

    def put(self, url, headers=None, json=None, timeout=None):
        self.puts += 1
        path, f = self._path(url), self.files.get(self._path(url))
        if self.race_once:                      # حد كتب قبلنا في نفس اللحظة
            self.race_once = False
            self.files[path] = {"content": b"[]", "v": (f["v"] + 1) if f else 1}
            return FakeResp(409)
        want = f"v{f['v']}" if f else None
        if json.get("sha") != want:
            return FakeResp(409)
        self.files[path] = {"content": base64.b64decode(json["content"]), "v": (f["v"] + 1) if f else 1}
        return FakeResp(201)


fake = FakeGitHub()
orig_requests = gs.requests
gs.requests = fake
try:
    store = gs.GithubEventStore("tok", "u/r")
    check("update creates file when missing", store.update("p.json", lambda d: d + [{"id": 1}]), [{"id": 1}])
    check("update appends", store.update("p.json", lambda d: d + [{"id": 2}]), [{"id": 1}, {"id": 2}])
    fake.race_once = True
    res = store.update("p.json", lambda d: d + [{"id": 3}])
    check("update retries after 409 and re-reads", res, [{"id": 3}])
    check("append still works", store.append("e.json", {"type": "quote", "quote_id": "Q"}), True)
    check("promotions via update (upsert)", [x["id"] for x in store.update(
        pr.PROMO_PATH, lambda d: pr.upsert(d, p))], [p["id"]])
    # فشل دايم -> خطأ واضح بعد 3 محاولات
    fake.put = lambda *a, **k: FakeResp(409)
    try:
        store.update("p.json", lambda d: d)
        check("persistent conflict raises", "no error", "GithubStoreError")
    except gs.GithubStoreError as e:
        check("persistent conflict raises", "3 محاولات" in str(e), True)
finally:
    gs.requests = orig_requests

# ------------------------------------------------------------
# 8) بوابة كلمة السر
# ------------------------------------------------------------
check("password from access_password", access.configured_password({"access_password": "abc"}), "abc")
check("password from dashboard_password (compat)", access.configured_password({"dashboard_password": "d"}), "d")
check("no password configured", access.configured_password({}), "")
check("secrets that raise are safe", access.configured_password(types.SimpleNamespace(
    get=lambda *a: (_ for _ in ()).throw(RuntimeError()))), "")
check("check_password ok", access.check_password("abc", "abc"), True)
check("check_password wrong", access.check_password("abd", "abc"), False)
check("check_password never ok when unset", access.check_password("", ""), False)


class FakeStreamlit:
    def __init__(self, secrets, state=None, typed=""):
        self.secrets, self.session_state, self.typed = secrets, dict(state or {}), typed
        self.out = []

    def warning(self, m): self.out.append(("warning", m))
    def markdown(self, m): self.out.append(("markdown", m))
    def error(self, m): self.out.append(("error", m))
    def text_input(self, *a, **k): return self.typed
    def rerun(self): self.out.append(("rerun", ""))
    def stop(self): raise SystemExit


def gate(secrets, state=None, typed=""):
    st = FakeStreamlit(secrets, state, typed)
    try:
        access.require_access(st)
        return "passed", st
    except SystemExit:
        return "stopped", st


check("gate: no password -> passes with warning", (gate({})[0], gate({})[1].out[0][0]), ("passed", "warning"))
check("gate: password set, nothing typed -> stopped", gate({"access_password": "pw"})[0], "stopped")
r, st_ = gate({"access_password": "pw"}, typed="bad")
check("gate: wrong password -> stopped + error", (r, st_.out[-1][0]), ("stopped", "error"))
r, st_ = gate({"access_password": "pw"}, typed="pw")
check("gate: right password -> unlocked + rerun", (st_.session_state.get("_access_ok"), r), (True, "stopped"))
check("gate: already unlocked passes", gate({"access_password": "pw"}, {"_access_ok": True})[0], "passed")

print("\n" + "=" * 74)
if fails:
    print(f"{len(fails)} FAILURE(S)")
    for f in fails:
        print("   ", f)
    sys.exit(1)
print("ALL CHECKS PASSED")
