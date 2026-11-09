# fake_streamlit.py
# ============================================================
#  أدوات اختبار فقط — Streamlit وهمي + GitHub وهمي، عشان نشغّل صفحات
#  البرنامج كاملة (Invoice.py وغيرها) من الترمكس من غير streamlit ولا شبكة.
#  مش بيتستورد من أي صفحة. شوف test_invoice_smoke.py.
#
#  الحدود: ده مش Streamlit — بيتأكد إن السكربت بيتنفّذ من أوله لآخره وإن
#  الأحداث/الأزرار المنطقية شغّالة، مش إن الشكل على الشاشة صح.
# ============================================================

import base64
import json
import os
import runpy
import sys
import types


class AttrDict(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class Rerun(Exception):
    pass


class Stop(Exception):
    pass


class _Ctx:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self._st

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)


class QueryParams(dict):
    def clear(self):
        super().clear()


class FakeSt(types.ModuleType):
    def __init__(self, state=None, secrets=None, clicks=(), query=None, typed=None):
        super().__init__("streamlit")
        self.session_state = AttrDict(state or {})
        self.secrets = dict(secrets or {})
        self.clicks = set(clicks)        # أسماء/مفاتيح الأزرار اللي "اتداس" عليها
        self.typed = dict(typed or {})   # مفتاح/عنوان خانة -> قيمة بتتكتب فيها
        self.query_params = QueryParams(query or {})
        self.calls = []
        self.options = {}                # key -> خيارات آخر selectbox اتبنى بالمفتاح ده
        self.sidebar = _Ctx(self)

    # ---- helpers
    def _hit(self, label, key):
        for k in (key, label):
            if k is not None and k in self.clicks:
                self.clicks.discard(k)
                return True
        return False

    def _input(self, label, key, default):
        ident = key if key is not None else label
        if key is not None:
            if key in self.typed:
                self.session_state[key] = self.typed[key]
            self.session_state.setdefault(key, default)
            return self.session_state[key]
        return self.typed.get(ident, default)

    # ---- widgets
    def text_input(self, label, value="", key=None, **kw):
        return self._input(label, key, value)

    def text_area(self, label, value="", key=None, **kw):
        return self._input(label, key, value)

    def number_input(self, label, value=0, key=None, **kw):
        return self._input(label, key, kw.get("min_value", 0) if value is None else value)

    def date_input(self, label, value=None, key=None, **kw):
        return self._input(label, key, value)

    def time_input(self, label, value=None, key=None, **kw):
        return self._input(label, key, value)

    def toggle(self, label, value=False, key=None, **kw):
        return self._input(label, key, value)

    checkbox = toggle

    def selectbox(self, label, options, index=0, key=None, **kw):
        options = list(options)
        self.options[key or label] = options
        default = options[index] if (options and index is not None) else None
        return self._input(label, key, default)

    def radio(self, label, options, index=0, key=None, **kw):
        options = list(options)
        return self._input(label, key, options[index] if options else None)

    def multiselect(self, label, options, default=None, key=None, **kw):
        return self._input(label, key, list(default or []))

    def button(self, label, key=None, **kw):
        return self._hit(label, key) and not kw.get("disabled", False)

    form_submit_button = button

    def download_button(self, label, data, **kw):
        self.calls.append(("download", label))
        return False

    def link_button(self, label, url, **kw):
        self.calls.append(("link", label, url))
        return False

    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx(self) for _ in range(n)]

    def expander(self, *a, **kw):
        return _Ctx(self)

    def form(self, *a, **kw):
        return _Ctx(self)

    def container(self, *a, **kw):
        return _Ctx(self)

    def tabs(self, labels):
        return [_Ctx(self) for _ in labels]

    def rerun(self):
        raise Rerun()

    def stop(self):
        raise Stop()

    def cache_data(self, *a, **kw):
        def deco(fn):
            fn.clear = lambda: None        # زي الدوال المخبّأة في Streamlit الحقيقي
            return fn
        if len(a) == 1 and callable(a[0]) and not kw:
            return deco(a[0])
        return deco

    cache_resource = cache_data

    def data_editor(self, df, **kw):
        return df

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: self.calls.append((name, a[:1]))

    # ---- مساعدات للاختبار
    def messages(self, kind):
        return [str(c[1][0]) if c[1] else "" for c in self.calls if c[0] == kind]


def run_script(path, **kw):
    """يشغّل سكربت صفحة على FakeSt، ويعيد التشغيل على Rerun زي Streamlit (لحد 6 مرات).
    بيرجّع (fake, globals). Stop = st.stop()."""
    fake = FakeSt(**kw)
    comp = types.ModuleType("streamlit.components.v1")
    comp.html = lambda h, **k: fake.calls.append(("components.html", h))
    pkg = types.ModuleType("streamlit.components")
    pkg.v1 = comp
    fake.components = pkg
    names = ("streamlit", "streamlit.components", "streamlit.components.v1")
    saved = {n: sys.modules.get(n) for n in names}
    sys.modules.update({"streamlit": fake, "streamlit.components": pkg,
                        "streamlit.components.v1": comp})
    g = {}
    try:
        for _ in range(6):
            try:
                g = runpy.run_path(os.path.abspath(path))
                break
            except Rerun:
                continue
            except Stop:
                break
    finally:
        for n, v in saved.items():
            if v is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = v
    return fake, g


# ------------------------------------------------------------
# GitHub وهمي (ملفات بنسخة sha، CAS حقيقي)
# ------------------------------------------------------------

class FakeResp:
    def __init__(self, code, payload=None):
        self.status_code, self._p, self.text = code, payload or {}, json.dumps(payload or {})

    def json(self):
        return self._p


class FakeGitHub:
    class RequestException(Exception):
        pass

    def __init__(self):
        self.files, self.puts = {}, 0

    @staticmethod
    def _path(url):
        return url.split("/contents/")[1]

    repo_private = True
    repo_status = 200

    def get(self, url, headers=None, params=None, timeout=None):
        if "/contents/" not in url:                     # GET /repos/{owner}/{repo}
            return FakeResp(self.repo_status, {"private": self.repo_private, "default_branch": "main"})
        f = self.files.get(self._path(url))
        if f is None:
            return FakeResp(404)
        return FakeResp(200, {"content": base64.b64encode(f["content"]).decode(), "sha": f"v{f['v']}"})

    def put(self, url, headers=None, json=None, timeout=None):
        self.puts += 1
        path, f = self._path(url), self.files.get(self._path(url))
        want = f"v{f['v']}" if f else None
        if json.get("sha") != want:
            return FakeResp(409)
        self.files[path] = {"content": base64.b64decode(json["content"]), "v": (f["v"] + 1) if f else 1}
        return FakeResp(201)

    # مساعد: كل الأحداث المتخزّنة في كل ملفات events/
    def events(self):
        import json as _j
        out = []
        for p, f in sorted(self.files.items()):
            if p.startswith("events/"):
                out.extend(_j.loads(f["content"].decode("utf-8")))
        return out

    def put_json(self, path, data):
        import json as _j
        f = self.files.get(path)
        self.files[path] = {"content": _j.dumps(data, ensure_ascii=False).encode("utf-8"),
                            "v": (f["v"] + 1) if f else 1}
