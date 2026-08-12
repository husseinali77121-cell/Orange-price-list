# خطوط الـ PDF

الفاتورة بتدوّر على خط يدعم يونيكود بالترتيب ده (`arabic_pdf.FONT_CANDIDATES`):

1. أي خط في المجلد ده — `Amiri-Regular.ttf` / `NotoNaskhArabic-Regular.ttf` /
   `Cairo-Regular.ttf` / `DejaVuSans.ttf`
2. خطوط النظام (Streamlit Cloud وDebian فيهم `DejaVuSans.ttf` جاهز)
3. Termux / Android / Windows / macOS

**مفيش خط = مفيش عربي في الـ PDF** — البرنامج بيرجع للسلوك القديم
(إنجليزي بس) وبيقفل زرار الـ PDF لو الاسم عربي، من غير ما يقع.

## للشكل الأحسن
حمّل **Amiri** أو **Noto Naskh Arabic** من Google Fonts وحط الـ `.ttf`
هنا. DejaVu بيشتغل صح بس شكله مش نسخي.
