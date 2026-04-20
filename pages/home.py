"""主页总览"""
import streamlit as st
from utils.database import get_stats, get_jobs
from utils.i18n import t
import pandas as pd

def show():
    st.markdown(f"## {t('home_title')}")
    st.markdown(t("home_subtitle"))
    st.markdown("---")
    stats = get_stats()
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric(t("total_jobs"), stats["jobs_total"])
    c2.metric(t("pending"),    stats["jobs_new"])
    c3.metric(t("applied"),    stats["apps_total"])
    c4.metric(t("interviewing"),stats["interviews"])
    c5.metric(t("offers"),     stats["offers"])
    st.markdown("---")
    st.markdown(f"### {t('recent_jobs')}")
    jobs = get_jobs(limit=10)
    if jobs:
        df = pd.DataFrame(jobs)[["source","title","company","location","ai_score","status"]]
        df["ai_score"] = df["ai_score"].apply(lambda x: f"{x:.0f}" if x else "—")
        df.columns = [t("col_source"),t("col_title"),t("col_company"),t("col_location"),t("col_score"),t("col_status")]
        st.dataframe(df, use_container_width=True)
    else:
        st.info(t("go_search"))
    st.markdown(f"### {t('quick_start')}")
    col1,col2,col3 = st.columns(3)
    col1.button(t("upload_resume"), use_container_width=True)
    col2.button(t("search_jobs"),   use_container_width=True)
    col3.button(t("ai_match"),      use_container_width=True)
