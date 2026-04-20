# 求职自动化系统

自动抓取 LinkedIn / Glassdoor 职位 → AI 匹配评分 → 定制简历 → 投递追踪

## 📁 项目结构

```
job_automation/
├── app.py                      # Streamlit 主入口
├── requirements.txt
├── data/                       # 自动创建，存放 SQLite 数据库
├── pages/
│   ├── home.py                 # 主页总览
│   ├── resume.py               # 简历管理（上传/解析）
│   ├── jobs.py                 # 职位搜索（LinkedIn + Glassdoor 抓取）
│   ├── matching.py             # AI 匹配评分
│   ├── generator.py            # 定制简历 + 求职信生成
│   └── tracker.py              # 投递状态追踪
└── utils/
    ├── database.py             # SQLite 数据库操作
    ├── scraper_linkedin.py     # LinkedIn Selenium 抓取器
    ├── scraper_glassdoor.py    # Glassdoor Selenium 抓取器
    └── scrape_manager.py       # 统一调度管理器
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd job_automation
pip install -r requirements.txt
```

### 2. 安装 ChromeDriver

确保本机已安装 Chrome 浏览器，然后安装对应版本的 ChromeDriver：

```bash
# 方法一：使用 webdriver-manager（推荐，自动匹配版本）
pip install webdriver-manager

# 在代码中会自动下载，或手动安装：
# macOS
brew install --cask chromedriver

# Ubuntu/Debian
sudo apt-get install chromium-chromedriver
```

### 3. 启动应用

```bash
streamlit run app.py
```

浏览器访问 http://localhost:8501

### 4. 使用流程

1. **简历管理** → 上传 PDF/Word 简历，设为基础简历
2. **职位搜索** → 填写 LinkedIn/Glassdoor 账号，配置关键词，开始抓取
3. **AI 匹配** → 填写 Claude API Key，批量分析职位匹配度
4. **生成材料** → 选择高分职位，一键生成定制简历 + 求职信
5. **投递追踪** → 记录投递状态，跟进面试进展

## ⚙️ 配置说明

### Chrome Profile（登录持久化）

首次登录后，Chrome 会将 Cookie 保存到：
- LinkedIn：`/tmp/chrome_linkedin_profile`
- Glassdoor：`/tmp/chrome_glassdoor_profile`

下次启动无需重新输入账号密码。

### 关于人机验证

- LinkedIn / Glassdoor 可能在首次登录或频繁操作时触发验证
- 建议使用**有头模式**（不勾选「无头模式」），方便手动完成验证
- 验证完成后程序会自动继续运行（等待最长 2 分钟）

## ⚠️ 使用须知

- 本工具仅供个人求职使用，请遵守各平台服务条款
- 建议每次抓取不超过 3-5 页（约 75-125 条）
- 两次抓取之间建议间隔 30 分钟以上
- 不建议在短时间内抓取大量数据，以免账号被限制

## 🔧 常见问题

**Q: 提示 ChromeDriver 版本不匹配？**
```bash
pip install --upgrade webdriver-manager
```
然后在 `scraper_linkedin.py` 和 `scraper_glassdoor.py` 的 `build_driver()` 函数顶部添加：
```python
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
# 在 webdriver.Chrome(options=opts) 之前加：
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=opts)
```

**Q: Glassdoor 页面结构变了，抓不到数据？**
Glassdoor 会定期更新前端结构，如遇到问题请打开浏览器开发者工具检查最新的 CSS 选择器，
更新 `scraper_glassdoor.py` 中对应的 `*_sels` 列表。

**Q: 如何部署给他人使用？**
推荐使用 Docker + 反向代理部署：
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y chromium chromium-driver
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```
注意：多用户场景下需要为每个用户隔离 Chrome Profile 路径。
