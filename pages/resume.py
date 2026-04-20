"""简历管理页面"""
import streamlit as st
import io
from utils.database import save_resume, get_all_resumes, get_base_resume
from utils.i18n import t

def extract_pdf(data):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)

def extract_docx(data):
    import docx
    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)

def show():
    st.markdown(f"## {t('resume_title')}")
    tab1, tab2 = st.tabs([t("upload_tab"), t("versions_tab")])
    with tab1:
        uploaded = st.file_uploader(t("upload_label"), type=["pdf","docx"])
        resume_text = ""
        if uploaded:
            raw = uploaded.read()
            try:
                resume_text = extract_pdf(raw) if uploaded.name.endswith(".pdf") else extract_docx(raw)
                if resume_text:
                    st.success(t("parse_success", len(resume_text)))
            except Exception as e:
                st.error(str(e))
        st.markdown(t("paste_label"))
        manual = st.text_area("", value=resume_text, height=400, placeholder=t("paste_placeholder"))
        final = manual.strip()
        name    = st.text_input(t("version_name"), value="Base Resume v1" if st.session_state.get("lang")=="en" else "基础简历 v1")
        is_base = st.checkbox(t("set_base"), value=True)
        if st.button(t("save_resume"), type="primary") and final:
            rid = save_resume(name, final, is_base=is_base)
            st.success(f"✅ Saved (ID: {rid})")
    with tab2:
        resumes = get_all_resumes()
        if not resumes:
            st.info(t("no_resumes")); return
        for r in resumes:
            with st.expander(f"{'⭐ ' if r['is_base'] else ''}{r['name']}  —  {r['created_at'][:10]}"):
                st.text_area("", value=r["content"], height=200, key=f"rv_{r['id']}", disabled=True)
        base = get_base_resume()
        if base:
            st.info(t("current_base", base["name"], base["created_at"][:10]))
