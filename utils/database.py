"""
数据库管理 - SQLite 本地存储
表结构：jobs（职位）, applications（投递记录）, resumes（简历版本）
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS jobs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source      TEXT NOT NULL,          -- 'linkedin' | 'glassdoor'
        job_id      TEXT,                   -- 平台原始ID
        title       TEXT NOT NULL,
        company     TEXT NOT NULL,
        location    TEXT,
        job_type    TEXT,                   -- Full-time / Remote ...
        salary      TEXT,
        description TEXT,
        url         TEXT,
        posted_at   TEXT,
        scraped_at  TEXT NOT NULL,
        lang        TEXT,                   -- 职位语言代码 en/zh/sv...
        ai_score    REAL,                   -- AI匹配分 0-100
        ai_summary  TEXT,                   -- AI分析摘要
        status      TEXT DEFAULT 'new',     -- new|saved|applied|interviewing|offer|rejected
        UNIQUE(source, job_id)
    );

    CREATE TABLE IF NOT EXISTS resumes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,          -- 版本名称
        content     TEXT NOT NULL,          -- 简历全文（纯文本）
        file_path   TEXT,                   -- 原始文件路径
        created_at  TEXT NOT NULL,
        is_base     INTEGER DEFAULT 0       -- 1=基础简历
    );

    CREATE TABLE IF NOT EXISTS applications (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id          INTEGER REFERENCES jobs(id),
        resume_id       INTEGER REFERENCES resumes(id),
        cover_letter    TEXT,
        applied_at      TEXT,
        status          TEXT DEFAULT 'sent',  -- sent|viewed|interview|offer|rejected
        notes           TEXT,
        next_action     TEXT,
        next_action_date TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_jobs_status   ON jobs(status);
    CREATE INDEX IF NOT EXISTS idx_jobs_source   ON jobs(source);
    CREATE INDEX IF NOT EXISTS idx_jobs_score    ON jobs(ai_score DESC);
    """)

    conn.commit()
    conn.close()


# ── Jobs ──────────────────────────────────────────────

def upsert_job(job: dict) -> int:
    """插入或更新职位，返回 row id"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO jobs (source, job_id, title, company, location, job_type,
                          salary, description, url, posted_at, scraped_at, lang)
        VALUES (:source,:job_id,:title,:company,:location,:job_type,
                :salary,:description,:url,:posted_at,:scraped_at,:lang)
        ON CONFLICT(source, job_id) DO UPDATE SET
            title=excluded.title,
            description=excluded.description,
            scraped_at=excluded.scraped_at,
            lang=excluded.lang
    """, {**job, "scraped_at": datetime.now().isoformat(), "lang": job.get("lang", "")})
    rowid = c.lastrowid
    conn.commit()
    conn.close()
    return rowid


def update_job_ai(job_id: int, score: float, summary: str):
    conn = get_conn()
    conn.execute("UPDATE jobs SET ai_score=?, ai_summary=? WHERE id=?",
                 (score, summary, job_id))
    conn.commit()
    conn.close()


def update_job_status(job_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
    conn.commit()
    conn.close()


def get_jobs(status=None, source=None, min_score=None, lang=None, keywords=None, keyword_logic="OR", limit=200) -> list:
    conn = get_conn()
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if source:
        query += " AND source=?"
        params.append(source)
    if min_score is not None:
        query += " AND ai_score>=?"
        params.append(min_score)
    if lang:
        placeholders = ",".join("?" * len(lang))
        query += f" AND lang IN ({placeholders})"
        params.extend(lang)
    if keywords:
        kws = [k.strip() for k in keywords if k.strip()]
        if kws:
            if keyword_logic == "AND":
                for kw in kws:
                    query += " AND (LOWER(title || ' ' || COALESCE(description,'')) LIKE ?)"
                    params.append(f"%{kw.lower()}%")
            else:  # OR
                parts = " OR ".join(
                    ["LOWER(title || ' ' || COALESCE(description,'')) LIKE ?" for _ in kws]
                )
                query += f" AND ({parts})"
                params.extend(f"%{kw.lower()}%" for kw in kws)
    query += " ORDER BY ai_score DESC NULLS LAST, scraped_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job(job_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Resumes ───────────────────────────────────────────

def save_resume(name: str, content: str, file_path: str = None, is_base=False) -> int:
    conn = get_conn()
    if is_base:
        conn.execute("UPDATE resumes SET is_base=0")
    c = conn.cursor()
    c.execute("""
        INSERT INTO resumes (name, content, file_path, created_at, is_base)
        VALUES (?,?,?,?,?)
    """, (name, content, file_path, datetime.now().isoformat(), int(is_base)))
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid


def get_base_resume() -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM resumes WHERE is_base=1 ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_resumes() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM resumes ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Applications ──────────────────────────────────────

def save_application(job_id: int, resume_id: int, cover_letter: str = None) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO applications (job_id, resume_id, cover_letter, applied_at, status)
        VALUES (?,?,?,?,?)
    """, (job_id, resume_id, cover_letter, datetime.now().isoformat(), "sent"))
    conn.execute("UPDATE jobs SET status='applied' WHERE id=?", (job_id,))
    aid = c.lastrowid
    conn.commit()
    conn.close()
    return aid


def get_applications() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.*, j.title, j.company, j.source, j.url,
               r.name as resume_name
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        JOIN resumes r ON a.resume_id = r.id
        ORDER BY a.applied_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    conn = get_conn()
    jobs_total   = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    jobs_new     = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='new'").fetchone()[0]
    apps_total   = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    interviews   = conn.execute("SELECT COUNT(*) FROM applications WHERE status='interview'").fetchone()[0]
    offers       = conn.execute("SELECT COUNT(*) FROM applications WHERE status='offer'").fetchone()[0]
    conn.close()
    return dict(jobs_total=jobs_total, jobs_new=jobs_new,
                apps_total=apps_total, interviews=interviews, offers=offers)


# 首次运行时建表
init_db()
