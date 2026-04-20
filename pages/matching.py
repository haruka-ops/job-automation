"""AI 匹配评分页面"""
import streamlit as st
import anthropic, json
from utils.database import get_jobs, get_base_resume, update_job_ai
from utils.i18n import t

SCORE_PROMPT = """You are a senior recruiter. Analyze the match between the job description and the candidate's resume.

Resume:
{resume}

Job Description:
{jd}

Return ONLY a JSON object with this structure:
{{
  "score": <integer 0-100>,
  "summary": "<2-3 sentence summary in the same language as the resume>",
  "strengths": ["strength1", "strength2", "strength3"],
  "gaps": ["gap1", "gap2"],
  "keywords_match": ["matched keyword1", "matched keyword2"],
  "keywords_missing": ["missing keyword1", "missing keyword2"]
}}
No other text, no markdown fences."""

def analyze_job(api_key, resume, job):
    client = anthropic.Anthropic(api_key=api_key)
    jd = f"Title: {job['title']}\nCompany: {job['company']}\n\n{job['description']}"
    msg = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=1000,
        messages=[{"role":"user","content":SCORE_PROMPT.format(resume=resume,jd=jd)}]
    )
    raw = msg.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)

def show():
    st.markdown(f"## {t('matching_title')}")
    api_key = st.session_state.get("api_key","")
    if not api_key: st.warning(t("no_api_key")); return
    base = get_base_resume()
    if not base: st.warning(t("no_base_resume")); return
    st.info(t("using_resume", base["name"]))

    jobs     = get_jobs(limit=200)
    unscored = [j for j in jobs if j["ai_score"] is None and j["description"]]
    all_jobs = jobs

    col1,col2,col3 = st.columns(3)
    col1.metric(t("pending_score"), len(unscored))
    col2.metric(t("scored"),        sum(1 for j in all_jobs if j["ai_score"] is not None))
    col3.metric(t("high_score"),    sum(1 for j in all_jobs if (j["ai_score"] or 0) >= 70))

    st.markdown("---")

    # ── 关键词筛选 ────────────────────────────────────
    is_en = st.session_state.get("lang") == "en"
    with st.expander("🔑 " + ("Filter by JD Keywords" if is_en else "按 JD 关键词筛选"), expanded=False):
        kw_col1, kw_col2 = st.columns([3,1])
        with kw_col1:
            kw_input = st.text_input(
                "Keywords (comma separated)" if is_en else "关键词（逗号分隔）",
                placeholder="e.g. marketing, AI" if is_en else "e.g. 市场营销, AI",
                key="match_kw_input"
            )
        with kw_col2:
            kw_logic = st.radio("Logic" if is_en else "逻辑", ["OR","AND"],
                                 horizontal=True, key="match_kw_logic")
        kw_list = [k.strip() for k in kw_input.split(",") if k.strip()] if kw_input else []

    # 重新拉取带关键词过滤的列表
    if kw_list:
        from utils.database import get_jobs as _get_jobs
        jobs     = _get_jobs(limit=200, keywords=kw_list, keyword_logic=kw_logic)
        unscored = [j for j in jobs if j["ai_score"] is None and j["description"]]
        if is_en:
            st.caption(f"Showing {len(jobs)} jobs matching keywords")
        else:
            st.caption(f"关键词筛选后共 {len(jobs)} 条职位")

    if unscored:
        batch_n = st.slider("", 1, min(len(unscored),20), min(5,len(unscored)))
        if st.button(t("batch_analyze", batch_n), type="primary"):
            progress = st.progress(0)
            status   = st.empty()
            results  = st.container()
            for i, job in enumerate(unscored[:batch_n]):
                status.text(t("analyzing", i+1, batch_n, job["title"], job["company"]))
                try:
                    analysis = analyze_job(api_key, base["content"], job)
                    score    = float(analysis.get("score", 0))
                    update_job_ai(job["id"], score, json.dumps(analysis, ensure_ascii=False))
                    color = "🟢" if score>=70 else "🟡" if score>=50 else "🔴"
                    results.markdown(f"{color} **{score:.0f}** — {job['title']} @ {job['company']}: {analysis.get('summary','')}")
                except Exception as e:
                    results.warning(f"❌ {job['title']}: {e}")
                progress.progress((i+1)/batch_n)
            status.success(t("analyze_done", batch_n))
            st.rerun()

    st.markdown(f"### {t('score_results')}")
    if kw_list:
        scored = [j for j in get_jobs(limit=200, keywords=kw_list, keyword_logic=kw_logic) if j["ai_score"] is not None]
    else:
        scored = [j for j in get_jobs(limit=200) if j["ai_score"] is not None]
    if not scored: st.info(t("no_scores")); return

    min_score = st.slider(t("min_score"), 0, 100, 60)
    filtered  = [j for j in scored if j["ai_score"] >= min_score]
    st.caption(t("showing", len(filtered), len(scored)))

    for job in filtered:
        score = job["ai_score"]
        color = "🟢" if score>=70 else "🟡" if score>=50 else "🔴"
        with st.expander(f"{color} **{score:.0f}** — {job['title']} @ {job['company']} ({job['source']})"):
            col1, col2 = st.columns([3,1])
            with col1:
                if job["ai_summary"]:
                    try:
                        data = json.loads(job["ai_summary"])
                        st.markdown(f"{t('summary')} {data.get('summary','')}")
                        if data.get("strengths"):
                            st.markdown(f"{t('strengths')} " + " · ".join(data["strengths"]))
                        if data.get("gaps"):
                            st.markdown(f"{t('gaps')} " + " · ".join(data["gaps"]))
                        if data.get("keywords_missing"):
                            st.markdown(f"{t('missing_kw')} " + "、".join(data["keywords_missing"]))
                    except Exception:
                        st.text(job["ai_summary"])
            with col2:
                st.metric(t("match_score"), f"{score:.0f}")
                if job.get("salary"): st.caption(f"💰 {job['salary']}")
                if job.get("url"):    st.link_button(t("view_post"), job["url"])
                if st.button(t("gen_materials"), key=f"gen_{job['id']}"):
                    st.session_state["selected_job_id"] = job["id"]
                    st.rerun()
