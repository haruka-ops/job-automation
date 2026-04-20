"""投递追踪页面"""
import streamlit as st
import pandas as pd
from utils.database import get_applications, get_stats, get_conn
from utils.i18n import t

def update_app_status(app_id, status):
    conn = get_conn()
    conn.execute("UPDATE applications SET status=? WHERE id=?", (status, app_id))
    conn.commit(); conn.close()

def show():
    st.markdown(f"## {t('tracker_title')}")
    stats = get_stats()
    cols = st.columns(5)
    metrics = [
        (t("total_apps"),     stats["apps_total"]),
        (t("interviews"),     stats["interviews"]),
        (t("offer_count"),    stats["offers"]),
        (t("conversion"),     f"{stats['offers']/max(stats['apps_total'],1)*100:.0f}%"),
        (t("interview_rate"), f"{stats['interviews']/max(stats['apps_total'],1)*100:.0f}%"),
    ]
    for col,(label,value) in zip(cols, metrics):
        col.metric(label, value)

    st.markdown("---")
    apps = get_applications()
    if not apps: st.info(t("no_apps")); return

    STATUS_LABELS = {
        "sent":      t("status_sent"),
        "viewed":    t("status_viewed"),
        "interview": t("status_interview"),
        "offer":     t("status_offer"),
        "rejected":  t("status_rejected"),
    }
    status_filter = st.multiselect(t("filter_status"), list(STATUS_LABELS.values()),
                                    default=list(STATUS_LABELS.values()))
    reverse_map  = {v:k for k,v in STATUS_LABELS.items()}
    selected     = {reverse_map[s] for s in status_filter}
    filtered     = [a for a in apps if a["status"] in selected]
    st.caption(t("showing_apps", len(filtered), len(apps)))

    for app in filtered:
        label = STATUS_LABELS.get(app["status"], app["status"])
        with st.expander(f"{label} — **{app['title']}** @ {app['company']}  |  {(app['applied_at'] or '')[:10]}"):
            col1, col2 = st.columns([3,1])
            with col1:
                st.markdown(f"**{t('source')}:** {app['source'].upper()}")
                if app.get("url"): st.markdown(f"**URL:** [{app['url'][:60]}…]({app['url']})")
            with col2:
                new_status = st.selectbox(t("update_status"),
                    list(STATUS_LABELS.keys()),
                    index=list(STATUS_LABELS.keys()).index(app["status"]),
                    format_func=lambda x: STATUS_LABELS[x],
                    key=f"status_{app['id']}")
                if st.button(t("update_btn"), key=f"upd_{app['id']}"):
                    update_app_status(app["id"], new_status); st.rerun()

    st.markdown("---")
    if st.button(t("export_csv")):
        csv = pd.DataFrame(apps).to_csv(index=False, encoding="utf-8-sig")
        st.download_button(t("download_csv"), csv, "applications.csv", "text/csv")
