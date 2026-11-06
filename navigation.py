# navigation.py
# ============================================================
#  🧭 شريط تنقّل بين صفحات البرنامج، جوه الصفحة نفسها.
#  ليه؟ Invoice.py بيخفي الـ header (عشان المساحة على الموبايل) وفيه زرار القايمة
#  الجانبية — فصفحات Dashboard/Studio كانت موجودة ومحدّش يوصللها.
#  الروابط محمية بـ try/except: صفحة مش موجودة أو نسخة Streamlit قديمة ماتوقّفش الصفحة.
# ============================================================

from __future__ import annotations

NAV_PAGES = [
    ("Invoice.py", "🧾", "Invoice"),
    ("pages/2_Marketing_Studio.py", "🎨", "Studio"),
    ("pages/1_Dashboard.py", "📊", "Dashboard"),
    ("pages/3_Follow_Up.py", "📞", "Follow-up"),
    ("pages/4_Promotions.py", "🎁", "Offers"),
]

NAV_CSS = """
<style>
/* أزرار التنقّل: مربّعات واضحة بإطار برتقالي، جنب بعض حتى على الموبايل */
div[data-testid="stHorizontalBlock"]:has(a[data-testid="stPageLink-NavLink"]) {
  flex-wrap:nowrap !important; gap:.4rem !important; margin:.2rem 0 .6rem 0;
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
