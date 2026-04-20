"""
Glassdoor 职位抓取器
Glassdoor 有较严格的反爬，使用已登录 Cookie + 慢速操作降低风险
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
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
    ElementClickInterceptedException
)
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


def build_driver(headless: bool = False) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1366,768")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    # 独立 Profile，与 LinkedIn 分开
    opts.add_argument("--user-data-dir=/tmp/chrome_glassdoor_profile")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def human_sleep(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))


def human_scroll(driver, steps=3):
    for _ in range(steps):
        driver.execute_script(
            f"window.scrollBy(0, {random.randint(200, 500)})"
        )
        time.sleep(random.uniform(0.6, 1.2))


class GlassdoorScraper:
    BASE  = "https://www.glassdoor.com"
    JOBS  = "https://www.glassdoor.com/Job/jobs.htm"

    def __init__(self, headless=False):
        self.driver    = build_driver(headless)
        self.wait      = WebDriverWait(self.driver, 15)
        self.logged_in = False

    # ── 登录 ──────────────────────────────────────────

    def login(self, email: str, password: str) -> bool:
        """登录 Glassdoor。首次登录后 Chrome Profile 会保存 Cookie，后续无需重新登录。"""
        self.driver.get(f"{self.BASE}/profile/login_input.htm")
        human_sleep(2, 4)

        try:
            # 接受 Cookie 弹窗（如有）
            try:
                self.driver.find_element(
                    By.CSS_SELECTOR, "[id*='onetrust-accept'], button[aria-label*='Accept']"
                ).click()
                human_sleep(1, 2)
            except NoSuchElementException:
                pass

            # 输入邮箱
            email_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], #userEmail"))
            )
            email_field.clear()
            for ch in email:
                email_field.send_keys(ch)
                time.sleep(random.uniform(0.05, 0.15))
            human_sleep(0.5, 1.0)

            # 点击"继续"按钮（部分 UI 分两步）
            try:
                self.driver.find_element(
                    By.CSS_SELECTOR, "button[type='submit'], #submit-btn, .emailButton"
                ).click()
                human_sleep(1.5, 2.5)
            except NoSuchElementException:
                pass

            # 输入密码
            pwd_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], #userPassword"))
            )
            for ch in password:
                pwd_field.send_keys(ch)
                time.sleep(random.uniform(0.05, 0.18))
            human_sleep(0.5, 1.0)
            pwd_field.send_keys(Keys.RETURN)
            human_sleep(4, 7)

            # 检查是否登录成功
            if any(kw in self.driver.current_url for kw in ["home", "member", "profile", "jobs"]):
                self.logged_in = True
                logger.info("Glassdoor 登录成功")
                return True

            # CAPTCHA / 人机验证
            if "captcha" in self.driver.page_source.lower() or "verify" in self.driver.current_url:
                logger.warning("⚠️ Glassdoor 触发验证，请在浏览器中手动完成")
                for _ in range(30):
                    time.sleep(5)
                    if any(kw in self.driver.current_url for kw in ["home", "member", "jobs"]):
                        self.logged_in = True
                        return True
                return False

        except TimeoutException:
            logger.error("Glassdoor 登录超时")
        return False

    def is_logged_in(self) -> bool:
        self.driver.get(f"{self.BASE}/member/home/")
        human_sleep(2, 3)
        return "member" in self.driver.current_url or "home" in self.driver.current_url

    # ── 搜索 ──────────────────────────────────────────

    def search_jobs(
        self,
        keyword: str,
        location: str = "United States",
        remote: bool = False,
        date_filter: int = 7,           # 天数：1 / 7 / 14 / 30
        max_pages: int = 5,
        progress_cb=None
    ) -> Generator[dict, None, None]:
        """逐条 yield 职位字典"""
        if not self.logged_in:
            raise RuntimeError("请先调用 login()")

        # Glassdoor 日期参数映射
        date_map = {1: "1", 7: "7", 14: "14", 30: "30"}
        date_param = date_map.get(date_filter, "7")

        # 构造初始搜索 URL
        kw_encoded  = keyword.replace(" ", "-")
        loc_encoded = location.replace(" ", "-").replace(",", "")
        search_url  = (
            f"{self.BASE}/Job/{loc_encoded}-{kw_encoded}-jobs-SRCH_IL.0,{len(loc_encoded)}"
            f"_IN1_KO{len(loc_encoded)+1},{len(loc_encoded)+len(kw_encoded)+1}.htm"
            f"?fromAge={date_param}&applicationType=1"
        )

        self.driver.get(search_url)
        human_sleep(3, 5)
        self._close_modal()

        for page in range(1, max_pages + 1):
            logger.info(f"Glassdoor 第 {page} 页")
            human_scroll(self.driver, steps=random.randint(2, 4))

            # 获取职位列表
            listings = self.driver.find_elements(
                By.CSS_SELECTOR,
                "li.react-job-listing, [data-test='jobListing'], .job-listing"
            )
            logger.info(f"  找到 {len(listings)} 条")

            if not listings:
                break

            for idx, item in enumerate(listings):
                try:
                    job = self._parse_listing(item)
                    if job:
                        if progress_cb:
                            progress_cb(idx + 1, len(listings), job)
                        yield job
                        human_sleep(2.5, 6.0)
                        self._close_modal()
                except (StaleElementReferenceException, ElementClickInterceptedException):
                    continue
                except Exception as e:
                    logger.debug(f"  解析失败: {e}")
                    continue

            # 翻页
            if not self._next_page():
                break
            human_sleep(4, 8)

    # ── 解析单条 ──────────────────────────────────────

    def _parse_listing(self, item) -> dict | None:
        """点击列表项，提取详情面板"""
        try:
            item.click()
        except Exception:
            return None

        human_sleep(2.0, 4.0)
        driver = self.driver

        # 尝试关闭弹窗（频率限制提示）
        self._close_modal()

        # 详情面板选择器
        panel_sels = [
            ".jobViewMinimal", ".jobView", "[data-test='jobView']",
            ".job-view", ".DetailContainer"
        ]
        panel = None
        for sel in panel_sels:
            try:
                panel = WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                break
            except TimeoutException:
                continue

        if not panel:
            return None

        # 标题
        title = ""
        for sel in ["[data-test='job-title']", ".jobTitle", "h1.css-17x2pwl", ".heading_Heading__BqX5J"]:
            try:
                title = panel.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # 公司
        company = ""
        for sel in ["[data-test='employer-name']", ".employerName", ".css-16nw49e"]:
            try:
                company = panel.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # 地点
        location = ""
        for sel in ["[data-test='location']", ".location", ".css-1v5elnn"]:
            try:
                location = panel.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # 薪资
        salary = ""
        for sel in ["[data-test='detailSalary']", ".salary", ".css-1xe2xww"]:
            try:
                salary = panel.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # 展开完整 JD
        try:
            show_more = panel.find_element(
                By.CSS_SELECTOR, "[data-test='show-more-click'], .jobDescriptionContent button"
            )
            driver.execute_script("arguments[0].click();", show_more)
            human_sleep(0.5, 1.0)
        except NoSuchElementException:
            pass

        description = ""
        for sel in ["[data-test='jobDescriptionContent']", ".jobDescriptionContent", ".css-t3xrds"]:
            try:
                description = panel.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # 发布时间
        posted_at = ""
        for sel in ["[data-test='job-age']", ".job-age", ".css-do6t5g"]:
            try:
                posted_at = panel.find_element(By.CSS_SELECTOR, sel).text.strip()
                break
            except NoSuchElementException:
                continue

        # URL & Job ID
        current_url = driver.current_url
        job_id = ""
        if "jobListingId=" in current_url:
            job_id = current_url.split("jobListingId=")[1].split("&")[0]
        elif "/job-listing/" in current_url:
            job_id = current_url.split("/job-listing/")[1].split("/")[0]
        if not job_id:
            job_id = f"gd_{hash(title + company)}"

        if not title or not company:
            return None

        return {
            "source":      "glassdoor",
            "job_id":      job_id,
            "title":       title,
            "company":     company,
            "location":    location,
            "job_type":    "",
            "salary":      salary,
            "description": description,
            "url":         current_url,
            "posted_at":   posted_at,
        }

    # ── 辅助 ──────────────────────────────────────────

    def _close_modal(self):
        """关闭各种弹窗（注册提示、限速提示等）"""
        close_sels = [
            "button[alt='Close']",
            ".modal_closeIcon",
            "[data-test='modal-close-btn']",
            ".CloseButton",
            "svg.SVGInline.modal_closeIcon",
        ]
        for sel in close_sels:
            try:
                self.driver.find_element(By.CSS_SELECTOR, sel).click()
                human_sleep(0.5, 1.0)
                return
            except (NoSuchElementException, ElementClickInterceptedException):
                continue

    def _next_page(self) -> bool:
        """点击下一页，返回是否成功"""
        next_sels = [
            "[data-test='pagination-next']",
            "button[aria-label='Next']",
            ".nextButton",
            "a.e1wkp9m30[aria-label='Next']",
        ]
        for sel in next_sels:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_enabled():
                    self.driver.execute_script("arguments[0].click();", btn)
                    return True
            except (NoSuchElementException, ElementClickInterceptedException):
                continue
        return False

    def quit(self):
        try:
            self.driver.quit()
        except Exception:
            pass
