"""
LinkedIn 职位抓取器
使用 Selenium 模拟人工操作，内置限速与随机延迟保护账号安全
"""

import time
import random
import logging
from datetime import datetime
from typing import Generator

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

# ── 反检测 Headers & Options ──────────────────────────

def build_driver(headless: bool = False) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    # 持久化登录 Cookie（首次登录后复用）
    opts.add_argument("--user-data-dir=/tmp/chrome_linkedin_profile")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    # 抹除 webdriver 特征
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ── 人性化操作工具 ─────────────────────────────────────

def human_sleep(min_s=1.5, max_s=4.0):
    """随机等待，模拟人工阅读"""
    time.sleep(random.uniform(min_s, max_s))


def human_scroll(driver, steps=3):
    """分段滚动，模拟人工浏览"""
    for _ in range(steps):
        driver.execute_script(
            f"window.scrollBy(0, {random.randint(300, 600)})"
        )
        time.sleep(random.uniform(0.4, 1.0))


def safe_text(el, selector: str, default="") -> str:
    try:
        return el.find_element(By.CSS_SELECTOR, selector).text.strip()
    except NoSuchElementException:
        return default


# ── LinkedIn 登录 ─────────────────────────────────────

class LinkedInScraper:
    BASE = "https://www.linkedin.com"
    JOBS = "https://www.linkedin.com/jobs/search/"

    def __init__(self, headless=False):
        self.driver = build_driver(headless)
        self.wait   = WebDriverWait(self.driver, 30)
        self.logged_in = False

    # ── 登录 ──────────────────────────────────────────

    def login(self, email: str, password: str) -> bool:
        """登录 LinkedIn，成功返回 True"""
        self.driver.get(f"{self.BASE}/login")
        human_sleep(4, 6)

        # 如果 Cookie 已有效，直接跳转到 feed，无需重新登录
        url = self.driver.current_url
        if any(k in url for k in ["feed", "mynetwork", "jobs", "messaging"]):
            logger.info("LinkedIn Cookie 有效，已自动登录")
            self.logged_in = True
            return True

        try:
            self.wait.until(EC.presence_of_element_located(
                (By.ID, "username"))).send_keys(email)
            human_sleep(0.5, 1.5)

            pwd = self.driver.find_element(By.ID, "password")
            for ch in password:          # 逐字符输入，模拟真实打字
                pwd.send_keys(ch)
                time.sleep(random.uniform(0.05, 0.18))
            human_sleep(0.5, 1.0)

            pwd.send_keys(Keys.RETURN)

            # 轮询等待跳转，最多 60 秒
            for _ in range(30):
                time.sleep(2)
                url = self.driver.current_url
                if any(k in url for k in ["feed", "mynetwork", "jobs", "messaging", "notifications"]):
                    self.logged_in = True
                    logger.info("LinkedIn 登录成功")
                    return True
                if "checkpoint" in url or "challenge" in url:
                    logger.warning("⚠️ 触发验证，请在浏览器窗口中手动完成")
                    for _ in range(60):
                        time.sleep(2)
                        if any(k in self.driver.current_url for k in ["feed", "mynetwork", "jobs"]):
                            self.logged_in = True
                            return True
                    return False

            logger.error("LinkedIn 登录超时：60秒内未跳转到首页")

        except TimeoutException:
            logger.error("LinkedIn 登录超时：找不到登录表单")
        return False

    def is_logged_in(self) -> bool:
        """检测当前是否已登录"""
        self.driver.get(f"{self.BASE}/feed")
        human_sleep(4, 6)
        return "feed" in self.driver.current_url

    # ── 搜索职位 ──────────────────────────────────────

    def search_jobs(
        self,
        keyword: str,
        location: str = "",
        remote: bool = False,
        date_filter: str = "r604800",   # 过去7天: r86400=1天, r604800=7天, r2592000=30天
        max_pages: int = 5,
        progress_cb=None                # 回调：progress_cb(current, total, job_dict)
    ) -> Generator[dict, None, None]:
        """
        搜索并逐条 yield 职位字典
        字段：source, job_id, title, company, location, job_type, salary,
              description, url, posted_at
        """
        if not self.logged_in:
            raise RuntimeError("请先调用 login() 或确认已登录")

        params = {
            "keywords": keyword,
            "location": location,
            "f_TPR": date_filter,       # 时间过滤
        }
        if remote:
            params["f_WT"] = "2"        # 2 = Remote

        query = "&".join(f"{k}={v}" for k, v in params.items())

        for page in range(max_pages):
            url = f"{self.JOBS}?{query}&start={page * 25}"
            self.driver.get(url)
            human_sleep(2.5, 4.5)

            # 等待职位列表卡片加载
            try:
                self.wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".jobs-search__results-list, .scaffold-layout__list")
                ))
            except TimeoutException:
                logger.warning(f"第 {page+1} 页加载超时，跳过")
                break

            human_scroll(self.driver, steps=random.randint(2, 4))

            # 获取所有职位卡片
            cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                "li.jobs-search-results__list-item, "
                ".job-card-container, "
                ".scaffold-layout__list-item"
            )
            logger.info(f"第 {page+1} 页：找到 {len(cards)} 个职位卡片")

            if not cards:
                break

            for idx, card in enumerate(cards):
                try:
                    job = self._parse_card_and_detail(card)
                    if job:
                        if progress_cb:
                            progress_cb(idx + 1, len(cards), job)
                        yield job
                        human_sleep(2.0, 5.0)   # 每条详情之间等待
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"解析卡片失败: {e}")
                    continue

            # 翻页间额外等待
            human_sleep(3.0, 7.0)

    # ── 解析单条职位 ──────────────────────────────────

    def _parse_card_and_detail(self, card) -> dict | None:
        """点击卡片，获取详情面板内容"""
        try:
            card.click()
            human_sleep(1.5, 3.0)
        except Exception:
            return None

        driver = self.driver

        # ── 详情面板（右侧或新标签页）────────────────
        panel_sel = (
            ".jobs-search__job-details, "
            ".job-view-layout, "
            ".jobs-details"
        )
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, panel_sel))
            )
        except TimeoutException:
            return None

        # Job ID（从 URL 解析）
        current_url = driver.current_url
        job_id = ""
        if "/jobs/view/" in current_url:
            job_id = current_url.split("/jobs/view/")[1].split("/")[0].split("?")[0]

        # 标题
        title = ""
        for sel in [".jobs-unified-top-card__job-title", "h1.t-24", ".job-details-jobs-unified-top-card__job-title"]:
            try:
                title = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # 公司
        company = ""
        for sel in [".jobs-unified-top-card__company-name", ".job-details-jobs-unified-top-card__company-name"]:
            try:
                company = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # 地点 / 类型 / 薪资
        location = salary = job_type = ""
        for sel in [
            ".jobs-unified-top-card__primary-description",
            ".job-details-jobs-unified-top-card__primary-description-container"
        ]:
            try:
                meta = driver.find_element(By.CSS_SELECTOR, sel).text
                parts = [p.strip() for p in meta.split("·")]
                if parts:
                    location = parts[0]
                if len(parts) > 1:
                    job_type = parts[1]
                if len(parts) > 2:
                    salary = parts[2]
                break
            except NoSuchElementException:
                continue

        # 职位描述（展开"查看更多"）
        description = ""
        try:
            more_btn = driver.find_element(
                By.CSS_SELECTOR,
                ".jobs-description__footer-button, "
                "button[aria-label='Show more, visually expands previously read content']"
            )
            driver.execute_script("arguments[0].click();", more_btn)
            human_sleep(0.5, 1.0)
        except NoSuchElementException:
            pass

        for sel in [".jobs-description-content__text", ".jobs-description__content", "#job-details"]:
            try:
                description = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # 发布时间
        posted_at = ""
        for sel in [".jobs-unified-top-card__posted-date", ".tvm__text--low-emphasis"]:
            try:
                posted_at = driver.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        if not title or not company:
            return None

        return {
            "source":      "linkedin",
            "job_id":      job_id or f"li_{hash(current_url)}",
            "title":       title,
            "company":     company,
            "location":    location,
            "job_type":    job_type,
            "salary":      salary,
            "description": description,
            "url":         current_url,
            "posted_at":   posted_at,
        }

    def quit(self):
        try:
            self.driver.quit()
        except Exception:
            pass
