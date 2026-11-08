# navigation.py
# ============================================================
#  🧭 شريط تنقّل بين صفحات البرنامج، جوه الصفحة نفسها (Invoice.py بيخفي الـ header وفيه
#  زرار القايمة الجانبية). صفين: الأساسي (Invoice · Studio · Dashboard · Follow-up ·
#  Offers) وCRM (Customers · Branches · Gifts). الروابط محمية بـ try/except: صفحة مش
#  موجودة أو نسخة Streamlit قديمة ماتوقّفش الصفحة.
# ============================================================

from __future__ import annotations

NAV_MAIN = [
    ("Invoice.py", "🧾", "Invoice"),
    ("pages/2_Marketing_Studio.py", "🎨", "Studio"),
    ("pages/1_Dashboard.py", "📊", "Dashboard"),
    ("pages/3_Follow_Up.py", "📞", "Follow-up"),
    ("pages/4_Promotions.py", "🎁", "Offers"),
]
NAV_MORE = [
    ("pages/5_Customers.py", "👥", "Customers"),
    ("pages/6_Branches.py", "📍", "Branches"),
    ("pages/7_Gifts.py", "🎀", "Gifts"),
]
NAV_PAGES = NAV_MAIN + NAV_MORE

NAV_CSS = """
<style>
/* أزرار التنقّل: مربّعات واضحة بإطار برتقالي، جنب بعض حتى على الموبايل */
div[data-testid="stHorizontalBlock"]:has(a[data-testid="stPageLink-NavLink"]) {
  flex-wrap:nowrap !important; gap:.4rem !important; margin:.2rem 0 .4rem 0;
}
div[data-testid="stHorizontalBlock"]:has(a[data-testid="stPageLink-NavLink"]) > div {
  min-width:0 !important; flex:1 1 0 !important;
}
a[data-testid="stPageLink-NavLink"] {
  display:flex !important; flex-direction:column; align-items:center; justify-content:center;
  gap:.1rem; min-height:3.1rem; padding:.35rem .15rem !important;
  border:2px solid #E96D23 !important; border-radius:12px !important;
  background:#FFF3EA !important; box-shadow:0 1px 3px rgba(233,109,35,.25);
  text-decoration:none !important; direction:ltr;
}
a[data-testid="stPageLink-NavLink"]:hover {background:#E96D23 !important;}
a[data-testid="stPageLink-NavLink"]:hover p {color:#fff !important;}
a[data-testid="stPageLink-NavLink"] p {
  font-size:.74rem !important; font-weight:700 !important; color:#B84A0B !important;
  white-space:nowrap; margin:0 !important; line-height:1.1;
}
a[data-testid="stPageLink-NavLink"] span {font-size:1.15rem !important; margin:0 !important;}
</style>
"""


def nav_items(current: str = "", group=None):
    """صفحات المجموعة (الأساسية افتراضياً) ما عدا الحالية."""
    return [p for p in (group if group is not None else NAV_MAIN) if p[0] != current]


def _row(st, items) -> int:
    if not items:
        return 0
    cols = st.columns(len(items))
    shown = 0
    for col, (path, icon, label) in zip(cols, items):
        with col:
            try:
                try:
                    st.page_link(path, label=label, icon=icon, use_container_width=True)
                except TypeError:                       # نسخة أقدم من Streamlit
                    st.page_link(path, label=label, icon=icon)
                shown += 1
            except Exception:
                pass                                    # الصفحة مش متاحة هنا — نكمّل
    return shown


def render_nav(st, current: str = "") -> int:
    """بيرسم الصفين (من غير الصفحة الحالية). بيرجّع عدد الروابط اللي اترسمت فعلاً."""
    try:
        st.markdown(NAV_CSS, unsafe_allow_html=True)
    except Exception:
        pass
    return _row(st, nav_items(current, NAV_MAIN)) + _row(st, nav_items(current, NAV_MORE))
