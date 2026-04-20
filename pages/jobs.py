"""职位搜索页面"""
import streamlit as st
import threading
import time
from utils.scrape_manager import ScrapeConfig, ScrapeManager
from utils.lang_filter import LANG_NAMES
from utils.database import get_jobs, get_stats
from utils.i18n import t
import pandas as pd

_log_buffer = []
_is_running  = False
_run_result  = None
_lock = threading.Lock()

def show():
    global _log_buffer, _is_running, _run_result

    st.markdown(f"## {t('jobs_title')}")
    st.markdown(t("jobs_subtitle"))

    with st.expander(t("search_params"), expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            keyword  = st.text_input(t("keyword"),  placeholder=t("keyword_placeholder"))
            location = st.text_input(t("location"), placeholder=t("location_placeholder"))
            remote   = st.checkbox(t("remote_only"))
        with col2:
            date_filter = st.selectbox(t("date_posted"), [1,7,14,30], index=1,
                                        format_func=lambda x: t("date_days", x))
            max_pages   = st.slider(t("max_pages"), 1, 5, 1, help=t("max_pages_help"))
            headless    = st.checkbox(t("headless"))

        st.markdown("**🌐 " + ("Job Description Language" if st.session_state.get("lang")=="en" else "职位语言筛选") + "**")
        lang_options = {"English": "en", "中文": "zh", "Svenska": "sv", "Deutsch": "de", "Français": "fr", "Español": "es"}
        default_langs = ["English", "中文"]
        selected_lang_labels = st.multiselect(
            "只保存以下语言的职位" if st.session_state.get("lang") != "en" else "Only save jobs in selected languages",
            options=list(lang_options.keys()),
            default=default_langs,
            help="留空 = 不过滤，保存所有语言" if st.session_state.get("lang") != "en" else "Leave empty = no filter, save all languages"
        )
        allowed_langs = [lang_options[l] for l in selected_lang_labels] if selected_lang_labels else None

    is_en = st.session_state.get("lang") == "en"
    st.markdown("**🔑 " + ("JD Keyword Filter" if is_en else "JD 关键词筛选") + "**")
    kw_col1, kw_col2 = st.columns([3, 1])
    with kw_col1:
        kw_input = st.text_input(
            "关键词（逗号分隔）" if not is_en else "Keywords (comma separated)",
            placeholder="e.g. marketing, AI, remote" if is_en else "e.g. 市场营销, AI, 远程",
            help="抓取时过滤：只保存 JD 中包含这些关键词的职位" if not is_en else "Filter at scrape time: only save jobs whose JD contains these keywords"
        )
    with kw_col2:
        kw_logic = st.radio(
            "逻辑" if not is_en else "Logic",
            ["OR", "AND"],
            horizontal=True,
            help="OR=包含任意一个 / AND=必须全部包含" if not is_en else "OR=any match / AND=all must match"
        )
    kw_list = [k.strip() for k in kw_input.split(",") if k.strip()] if kw_input else []
    must_keywords = kw_list if kw_logic == "AND" else None
    any_keywords  = kw_list if kw_logic == "OR"  else None

    with st.expander(t("credentials"), expanded=True):
        tab_li, tab_gd = st.tabs(["LinkedIn", "Glassdoor"])
        with tab_li:
            use_linkedin = st.checkbox(t("enable_linkedin"), value=True)
            li_email     = st.text_input(t("linkedin_email"),    key="li_email")
            li_password  = st.text_input(t("linkedin_password"), key="li_pwd", type="password")
        with tab_gd:
            use_glassdoor = st.checkbox(t("enable_glassdoor"), value=False)
            gd_email      = st.text_input(t("glassdoor_email"),    key="gd_email")
            gd_password   = st.text_input(t("glassdoor_password"), key="gd_pwd", type="password")

    st.markdown("---")
    col_start, col_stop, _ = st.columns([2,2,6])
    start_btn = col_start.button(t("start_scrape"), type="primary", use_container_width=True)
    stop_btn  = col_stop.button(t("stop"), use_container_width=True)

    if "mgr" not in st.session_state:
        st.session_state.mgr = ScrapeManager()
    mgr: ScrapeManager = st.session_state.mgr

    if stop_btn and _is_running:
        mgr.stop(); _is_running = False
        st.warning(t("stop"))

    if start_btn and not _is_running:
        if not keyword.strip():
            st.error(t("err_no_keyword")); return
        if use_linkedin and not li_email:
            st.error(t("err_no_li_email")); return
        if use_glassdoor and not gd_email:
            st.error(t("err_no_gd_email")); return

        config = ScrapeConfig(
            keyword=keyword, location=location or "United States",
            remote=remote, date_filter=date_filter, max_pages=max_pages,
            headless=headless, use_linkedin=use_linkedin, use_glassdoor=use_glassdoor,
            linkedin_email=li_email, linkedin_password=li_password,
            allowed_langs=allowed_langs,
            must_keywords=must_keywords,
            any_keywords=any_keywords,
            glassdoor_email=gd_email, glassdoor_password=gd_password,
        )
        with _lock:
            _log_buffer.clear(); _is_running = True; _run_result = None

        def _run():
            global _is_running, _run_result
            def cb(msg):
                with _lock: _log_buffer.append(msg)
            result = mgr.run(config, progress_cb=cb)
            with _lock: _run_result = result; _is_running = False

        threading.Thread(target=_run, daemon=True).start()

    if _is_running or _log_buffer:
        st.markdown(f"### {t('scrape_log')}")
        with _lock: logs = list(_log_buffer[-80:])
        st.code("\n".join(logs) if logs else "...", language="")
        if _is_running:
            st.info(t("scraping"))
            time.sleep(2); st.rerun()

    if _run_result and _run_result.done:
        r = _run_result
        st.markdown(f"### {t('scrape_done')}")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric(t("scanned"),    r.total)
        c2.metric(t("new_saved"),  r.saved)
        c3.metric(t("duplicates"), r.skipped)
        c4.metric(t("errors"),     r.errors)

    st.markdown("---")
    st.markdown(f"### {t('db_jobs')}")
    jobs = get_jobs(limit=50)
    if jobs:
        stats = get_stats()
        col1,col2,col3 = st.columns(3)
        col1.metric(t("total_jobs"), stats["jobs_total"])
        col2.metric(t("pending"),    stats["jobs_new"])
        col3.metric(t("applied"),    stats["apps_total"])
        df = pd.DataFrame(jobs)[["source","title","company","location","posted_at","ai_score","status"]]
        df["ai_score"] = df["ai_score"].apply(lambda x: f"{x:.0f}" if x else "—")
        df.columns = [t("col_source"),t("col_title"),t("col_company"),t("col_location"),t("col_posted"),t("col_score"),t("col_status")]
        st.dataframe(df, use_container_width=True, height=350)
    else:
        st.info(t("no_jobs"))

    with st.expander(t("tips_title")):
        st.markdown(t("tips_body"))
