"""
抓取任务管理器 - 使用独立子进程运行 Chrome，避免 Streamlit 线程限制
"""

import os
import sys
import json
import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from utils.database import upsert_job
from utils.lang_filter import is_allowed, get_lang_display

logger = logging.getLogger(__name__)


@dataclass
class ScrapeConfig:
    keyword:          str  = "Software Engineer"
    location:         str  = "United States"
    remote:           bool = False
    date_filter:      int  = 7
    max_pages:        int  = 3
    linkedin_email:   str  = ""
    linkedin_password:str  = ""
    glassdoor_email:  str  = ""
    glassdoor_password:str = ""
    use_linkedin:     bool = True
    use_glassdoor:    bool = True
    headless:         bool = False


@dataclass
class ScrapeResult:
    total:   int  = 0
    saved:   int  = 0
    skipped: int  = 0
    errors:  int  = 0
    log:     list = field(default_factory=list)
    done:    bool = False


# ── 独立抓取脚本内容（写入临时文件执行）────────────────

SCRAPE_SCRIPT = '''
import sys, json, os
sys.path.insert(0, "{project_dir}")

results = []

def save(job):
    results.append(job)
    print("JOB:" + json.dumps(job, ensure_ascii=False), flush=True)

config = json.loads(sys.argv[1])

if config.get("use_linkedin") and config.get("linkedin_email"):
    print("LOG:🔗 启动 LinkedIn...", flush=True)
    try:
        from utils.scraper_linkedin import LinkedInScraper
        s = LinkedInScraper(headless=config.get("headless", False))
        ok = s.login(config["linkedin_email"], config["linkedin_password"])
        if not ok:
            print("LOG:❌ LinkedIn 登录失败", flush=True)
        else:
            print("LOG:✅ LinkedIn 登录成功，开始搜索", flush=True)
            li_date = {{1:"r86400",7:"r604800",14:"r1209600",30:"r2592000"}}
            df = li_date.get(config.get("date_filter",7), "r604800")
            for job in s.search_jobs(
                keyword=config["keyword"],
                location=config.get("location",""),
                remote=config.get("remote",False),
                date_filter=df,
                max_pages=config.get("max_pages",2),
            ):
                save(job)
            print(f"LOG:LinkedIn 完成，共 {{len([r for r in results if r.get('source')=='linkedin'])}} 条", flush=True)
        s.quit()
    except Exception as e:
        print(f"LOG:❌ LinkedIn 异常: {{e}}", flush=True)

if config.get("use_glassdoor") and config.get("glassdoor_email"):
    print("LOG:🔷 启动 Glassdoor...", flush=True)
    try:
        from utils.scraper_glassdoor import GlassdoorScraper
        s = GlassdoorScraper(headless=config.get("headless", False))
        ok = s.login(config["glassdoor_email"], config["glassdoor_password"])
        if not ok:
            print("LOG:❌ Glassdoor 登录失败", flush=True)
        else:
            print("LOG:✅ Glassdoor 登录成功，开始搜索", flush=True)
            for job in s.search_jobs(
                keyword=config["keyword"],
                location=config.get("location",""),
                remote=config.get("remote",False),
                date_filter=config.get("date_filter",7),
                max_pages=config.get("max_pages",2),
            ):
                save(job)
            print(f"LOG:Glassdoor 完成", flush=True)
        s.quit()
    except Exception as e:
        print(f"LOG:❌ Glassdoor 异常: {{e}}", flush=True)

print("LOG:✅ 抓取完成", flush=True)
'''


class ScrapeManager:
    def __init__(self):
        self._proc = None
        self._stopped = False

    def stop(self):
        self._stopped = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def run(
        self,
        config: ScrapeConfig,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> ScrapeResult:
        self._stopped = False
        result = ScrapeResult()

        def log(msg):
            result.log.append(msg)
            if progress_cb:
                progress_cb(msg)

        # 找到项目根目录
        project_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )

        # 把配置序列化
        cfg_json = json.dumps({
            "keyword":          config.keyword,
            "location":         config.location,
            "remote":           config.remote,
            "date_filter":      config.date_filter,
            "max_pages":        config.max_pages,
            "headless":         config.headless,
            "use_linkedin":     config.use_linkedin,
            "use_glassdoor":    config.use_glassdoor,
            "linkedin_email":   config.linkedin_email,
            "linkedin_password":config.linkedin_password,
            "glassdoor_email":  config.glassdoor_email,
            "glassdoor_password":config.glassdoor_password,
        })

        # 写入临时脚本
        script_content = SCRAPE_SCRIPT.format(project_dir=project_dir)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script_content)
            script_path = f.name

        try:
            python = sys.executable
            self._proc = subprocess.Popen(
                [python, script_path, cfg_json],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=project_dir,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )

            for line in self._proc.stdout:
                line = line.rstrip()
                if not line:
                    continue

                if line.startswith("LOG:"):
                    log(line[4:])

                elif line.startswith("JOB:"):
                    try:
                        job = json.loads(line[4:])
                        result.total += 1
                        upsert_job(job)
                        result.saved += 1
                        log(f"  ✔ [{result.saved}] {job['title']} @ {job['company']}")
                    except Exception as e:
                        if "UNIQUE" in str(e):
                            result.skipped += 1
                        else:
                            result.errors += 1
                            log(f"  ⚠ 存储失败: {e}")
                else:
                    # 其他输出（报错等）也显示出来
                    if line.strip():
                        log(f"  {line}")

                if self._stopped:
                    self._proc.terminate()
                    break

            self._proc.wait()

        except Exception as e:
            log(f"❌ 启动失败: {e}")
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass

        result.done = True
        log(f"\n🎉 完成！新增 {result.saved} 条 | 重复 {result.skipped} 条 | 错误 {result.errors} 条")
        return result
