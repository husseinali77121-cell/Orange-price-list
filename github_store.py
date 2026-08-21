# github_store.py
# ============================================================
#  تخزين أحداث الـ Marketing (referral / lost-sale / converted)
#  في ملف JSON على GitHub — نفس فكرة الـ CAS write protection
#  اللي في HVMS، لكن نسخة مصغّرة مخصوصة للأحداث دي بس.
#
#  محتاج Streamlit secrets (ضيفهم في Settings -> Secrets):
#    gh_events_token   = fine-grained PAT (Contents: Read & write)
#    gh_events_repo    = "username/repo-name"  (ممكن نفس ريبو الداتا
#                          بتاع HVMS أو ريبو تاني منفصل — قرارك)
#    gh_events_branch  = "main"  (اختياري، افتراضي main)
#
#  ⚠️ ملف الشبكة ده مش قابل للاختبار من غير اتصال حقيقي بـ GitHub —
#  اختبره بعد الرفع على Streamlit Cloud. المنطق البحت (تلخيص/بناء
#  الأحداث) في tracking.py و test_tracking.py وده اللي بيتأكد منه
#  محلياً قبل الرفع.
# ============================================================

from __future__ import annotations

import base64
import json
from typing import List, Optional, Tuple

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

API_ROOT = "https://api.github.com"
TIMEOUT = 12


class GithubStoreError(Exception):
    pass


class GithubEventStore:
    """ملف JSON واحد (قائمة أحداث) على GitHub، بحماية CAS."""

    def __init__(self, token: str, repo: str, branch: str = "main"):
        if not requests:
            raise GithubStoreError("مكتبة requests مش متثبّتة — ضيفها لـ requirements.txt")
        if not token or not repo:
            raise GithubStoreError("gh_events_token / gh_events_repo مش متظبطين في secrets")
        self.token = token
        self.repo = repo.strip("/")
        self.branch = branch or "main"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"{API_ROOT}/repos/{self.repo}/contents/{path}"

    def read(self, path: str) -> Tuple[List[dict], Optional[str]]:
        """(events, sha). sha=None لو الملف لسه مش موجود (أول مرة)."""
        r = requests.get(self._url(path), headers=self._headers(),
                         params={"ref": self.branch}, timeout=TIMEOUT)
        if r.status_code == 404:
            return [], None
        if r.status_code != 200:
            raise GithubStoreError(f"GitHub read فشل ({r.status_code}): {r.text[:200]}")
        data = r.json()
        raw = base64.b64decode(data["content"]).decode("utf-8") if data.get("content") else "[]"
        try:
            events = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            events = []
        return events, data.get("sha")

    def append(self, path: str, event: dict, max_retries: int = 3) -> bool:
        """
        بيقرا، يضيف الحدث، يكتب بالـ sha بتاع النسخة اللي قراها (CAS).
        لو حد كتب فوقه في نفس اللحظة (409) بيعيد المحاولة من الأول.
        """
        last_err = None
        for _ in range(max_retries):
            try:
                events, sha = self.read(path)
                events.append(event)
                body = {
                    "message": f"event: {event.get('type', '?')} {event.get('quote_id', '')}",
                    "content": base64.b64encode(
                        json.dumps(events, ensure_ascii=False, indent=1).encode("utf-8")
                    ).decode("ascii"),
                    "branch": self.branch,
                }
                if sha:
                    body["sha"] = sha
                r = requests.put(self._url(path), headers=self._headers(),
                                 json=body, timeout=TIMEOUT)
                if r.status_code in (200, 201):
                    return True
                if r.status_code == 409:   # race — حد كتب قبلنا، جرّب تاني
                    last_err = "409 conflict"
                    continue
                raise GithubStoreError(f"GitHub write فشل ({r.status_code}): {r.text[:200]}")
            except requests.RequestException as e:
                last_err = str(e)
        raise GithubStoreError(f"append فشلت بعد {max_retries} محاولات: {last_err}")


def events_path(month_key: str) -> str:
    """events/2026-08.json"""
    return f"events/{month_key}.json"


def month_range(start_month: str, end_month: str) -> List[str]:
    """كل شهور YYYY-MM من start لغاية end شامل الطرفين، بالترتيب."""
    y1, m1 = (int(x) for x in start_month.split("-"))
    y2, m2 = (int(x) for x in end_month.split("-"))
    out = []
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def read_events_range(store: "GithubEventStore", start_month: str,
                      end_month: str) -> List[dict]:
    """يقرا كل شهور الفترة (شامل الطرفين) ويرجّعهم مجمّعين في list واحدة."""
    out: List[dict] = []
    for mk in month_range(start_month, end_month):
        events, _ = store.read(events_path(mk))
        out.extend(events)
    return out


def store_from_secrets(secrets) -> Optional["GithubEventStore"]:
    """
    عامل مشترك بين Invoice.py وصفحة الداشبورد — None لو التتبّع مش
    متظبط، بدون ما يوقّف أي صفحة.
    """
    try:
        token = secrets.get("gh_events_token", "")
        repo = secrets.get("gh_events_repo", "")
        branch = secrets.get("gh_events_branch", "main")
        if not token or not repo:
            return None
        return GithubEventStore(token, repo, branch)
    except Exception:
        return None
