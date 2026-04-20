"""求职自动化系统 - 主入口"""

import streamlit as st

st.set_page_config(
    page_title="Job Automation",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stButton > button { border-radius: 8px; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

# 初始化语言
if "lang" not in st.session_state:
    st.session_state.lang = "zh"

from utils.i18n import t

with st.sidebar:
    st.markdown(f"## 💼 {t('app_title')}")

    # 语言切换
    lang_choice = st.radio(
        t("language"),
        ["中文", "English"],
        index=0 if st.session_state.lang == "zh" else 1,
        horizontal=True,
    )
    st.session_state.lang = "zh" if lang_choice == "中文" else "en"

    st.markdown("---")

    page = st.radio(
        "Menu" if st.session_state.lang == "en" else "功能模块",
        [t("nav_home"), t("nav_resume"), t("nav_jobs"),
         t("nav_matching"), t("nav_generator"), t("nav_tracker")],
        index=0
    )

    st.markdown("---")
    api_key = st.text_input(t("api_key_label"), type="password",
                             help=t("api_key_help"))
    if api_key:
        st.session_state["api_key"] = api_key
        st.success(t("api_key_set"))

    st.markdown("---")
    st.markdown(f"**{t('system_note')}**")
    st.markdown(t("system_note_body"))

if page == t("nav_home"):
    from pages import home; home.show()
elif page == t("nav_resume"):
    from pages import resume; resume.show()
elif page == t("nav_jobs"):
    from pages import jobs; jobs.show()
elif page == t("nav_matching"):
    from pages import matching; matching.show()
elif page == t("nav_generator"):
    from pages import generator; generator.show()
elif page == t("nav_tracker"):
    from pages import tracker; tracker.show()
