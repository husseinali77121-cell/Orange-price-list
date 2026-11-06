# navigation.py
# ============================================================
#  🧭 شريط تنقّل بين صفحات البرنامج، جوه الصفحة نفسها.
#  ليه؟ Invoice.py بيخفي الـ header (عشان المساحة على الموبايل) وفيه زرار القايمة
#  الجانبية — فصفحات Dashboard/Studio كانت موجودة ومحدّش يوصللها.
#  الروابط محمية بـ try/except: صفحة مش موجودة أو نسخة Streamlit قديمة ماتوقّفش الصفحة.
# ============================================================

from __future__ import annotations

NAV_PAGES = [
    ("Invoice.py", "🧾", "الفاتورة"),
    ("pages/2_Marketing_Studio.py", "🎨", "الاستوديو"),
    ("pages/1_Dashboard.py", "📊", "الداشبورد"),
    ("pages/3_Follow_Up.py", "📞", "المتابعة"),
    ("pages/4_Promotions.py", "🎁", "العروض"),
]

NAV_CSS = """
<style>
/* روابط التنقّل تفضل جنب بعض على الموبايل */
div[data-testid="stHorizontalBlock"]:has(a[data-testid="stPageLink-NavLink"]) {
  flex-wrap:nowrap !important; gap:.3rem !important;
}
div[data-testid="stHorizontalBlock"]:has(a[data-testid="stPageLink-NavLink"]) > div {
  min-width:0 !important; flex:1 1 0 !important;
}
a[data-testid="stPageLink-NavLink"] {padding:.3rem .2rem !important; justify-content:center;}
a[data-testid="stPageLink-NavLink"] p {font-size:.78rem; white-space:nowrap;}
</style>
"""


def nav_items(current: str = ""):
    """كل الصفحات ما عدا الحالية."""
    return [p for p in NAV_PAGES if p[0] != current]


def render_nav(st, current: str = "") -> int:
    """بيرسم الشريط. بيرجّع عدد الروابط اللي اترسمت فعلاً (للاختبار)."""
    items = nav_items(current)
    try:
        st.markdown(NAV_CSS, unsafe_allow_html=True)
    except Exception:
        pass
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
