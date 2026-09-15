import sys
import datetime
import sqlite3
import json
import subprocess
import os
import re
import glob
import html
import urllib.request
import urllib.parse
import asyncio
from playwright.sync_api import sync_playwright

# --- 配置区 ---
TARGET_URL = "https://tftb.sczwfw.gov.cn:8085/hos-server/pub/jmas/jmasbucket/jmopen_files/unzip/6e5032129863494a94bb2e2e7a2e9748/sltqszdsksssqxxpc/index.html#/"
DB_FILE = "reservoirs.db"
RESERVOIR_NAMES = ["二滩", "锦屏一级", "官地"]
LOG_FILE = "scrape.log"
GOV_SOURCE = "四川政务公开"
XUEQIU_SOURCE = "雪球@纬班长"
WECHAT_SOURCE = "微信公众号@纬班长"
XUEQIU_USER_ID = "4737961300"
XUEQIU_STATUS_IDS = [
    status_id.strip()
    for status_id in os.environ.get("XUEQIU_STATUS_IDS", "400178377,399726339,395818607,395752602,395690742,395607216,395104103,394878166,394700390,394539731,394304756,394086059,393824168,393149445").split(",")
    if status_id.strip()
]
XUEQIU_LOCAL_POST_DIR = "xueqiu_posts"
WECHAT_LOCAL_POST_DIR = "wechat_posts"
WECHAT_ARTICLE_URL_FILE = os.environ.get(
    "WECHAT_ARTICLE_URL_FILE",
    os.path.join(WECHAT_LOCAL_POST_DIR, "article_urls.txt"),
)
XUEQIU_RESERVOIR_NAMES = ["两河口", "杨房沟", "锦屏一级", "官地", "二滩", "桐子林"]
XUEQIU_FETCH_LIMIT = int(os.environ.get("XUEQIU_FETCH_LIMIT", "10"))
GENERATED_WECHAT_CACHE_FILES = []
DISCOVERED_WECHAT_ARTICLES = []

def log(msg):
    """写入日志"""
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # 检查字段是否存在
    cursor.execute("PRAGMA table_info(reservoir_data)")
    columns = [column[1] for column in cursor.fetchall()]
    migrations = {
        'percentage': 'ALTER TABLE reservoir_data ADD COLUMN percentage REAL',
        'source': "ALTER TABLE reservoir_data ADD COLUMN source TEXT DEFAULT '四川政务公开'",
        'source_url': 'ALTER TABLE reservoir_data ADD COLUMN source_url TEXT',
        'energy_level': 'ALTER TABLE reservoir_data ADD COLUMN energy_level REAL',
        'note': 'ALTER TABLE reservoir_data ADD COLUMN note TEXT',
    }
    for column_name, sql in migrations.items():
        if column_name not in columns:
            cursor.execute(sql)
    conn.commit()
    conn.close()
    log("✅ 数据库初始化完成。")

def safe_float(value, default=0.0):
    """安全转换浮点数"""
    if value is None or value == "" or value == "-":
        return default
    try:
        return float(value)
    except ValueError:
        return default

def open_target_page(page, attempts=3):
    """打开目标页面，带重试，避免偶发网络/渲染卡顿直接失败。"""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                log(f"🔁 重新访问页面 ({attempt}/{attempts})...")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            return
        except Exception as e:
            last_error = e
            log(f"⚠️ 页面访问失败 ({attempt}/{attempts}): {e}")
            if attempt < attempts:
                page.wait_for_timeout(3000)
    raise last_error

def wait_for_station_input(page, attempts=3):
    """等待站名输入框可见，必要时刷新重试。"""
    selector = 'input[placeholder="站名"]'
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            page.wait_for_selector(selector, state="visible", timeout=45000)
            return page.locator(selector)
        except Exception as e:
            last_error = e
            log(f"⚠️ 站名输入框未出现 ({attempt}/{attempts}): {e}")
            if attempt < attempts:
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
    raise last_error

def save_to_sqlite(data_list):
    """将数据存入数据库，具备去重功能"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_records_count = 0

    for res in data_list:
        val_name = res.get("zhanming")
        val_water_level = safe_float(res.get("ksw"))
        val_inflow = safe_float(res.get("rkll"))
        val_outflow = safe_float(res.get("ckll"))
        val_capacity = None if res.get("xsl") is None else safe_float(res.get("xsl")) / 100.0
        val_energy = res.get("energy_level")
        val_source = res.get("source") or GOV_SOURCE
        val_source_url = res.get("source_url")
        val_note = res.get("note")
        val_record_time = res.get("record_time") or now

        # --- 去重核心逻辑 ---
        cursor.execute('''
            SELECT water_level, inflow, outflow, capacity_level, energy_level
            FROM reservoir_data
            WHERE name = ? AND record_time = ?
            ORDER BY id DESC LIMIT 1
        ''', (val_name, val_record_time))
        same_time_record = cursor.fetchone()

        if same_time_record:
            if (val_water_level == same_time_record[0] and
                val_inflow == same_time_record[1] and
                val_outflow == same_time_record[2] and
                val_capacity == same_time_record[3] and
                val_energy == same_time_record[4]):
                log(f"⏭️ {val_name} {val_record_time} 已存在，跳过写入。")
                continue

        cursor.execute('''
            SELECT water_level, inflow, outflow, capacity_level, energy_level
            FROM reservoir_data 
            WHERE name = ? 
            ORDER BY record_time DESC LIMIT 1
        ''', (val_name,))
        last_record = cursor.fetchone()

        if last_record:
            if (val_water_level == last_record[0] and 
                val_inflow == last_record[1] and 
                val_outflow == last_record[2] and 
                val_capacity == last_record[3] and
                val_energy == last_record[4]):
                log(f"⏭️ {val_name} 数据未变化，跳过写入。")
                continue

        cursor.execute('''
            INSERT INTO reservoir_data (
                name, record_time, water_level, inflow, outflow, capacity_level,
                energy_level, source, source_url, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            val_name, val_record_time, val_water_level, val_inflow, val_outflow,
            val_capacity, val_energy, val_source, val_source_url, val_note
        ))
        new_records_count += 1
        log(f"✅ {val_name} 数据已更新: 水位 {val_water_level}m，来源 {val_source}")

    conn.commit()
    conn.close()
    return new_records_count

def strip_tags(value):
    value = re.sub(r'<br\s*/?>', '\n', value, flags=re.I)
    value = re.sub(r'</p\s*>', '\n', value, flags=re.I)
    value = re.sub(r'<[^>]+>', '', value)
    return html.unescape(value)

def xueqiu_status_url(status_id):
    return f"https://xueqiu.com/{XUEQIU_USER_ID}/{status_id}"

def xueqiu_status_id_from_source(source):
    match = re.search(r'/(\d{6,})$', source or "")
    if match:
        return match.group(1)

    basename = os.path.basename(source or "")
    match = re.search(r'-(\d{6,})\.txt$', basename)
    if match:
        return match.group(1)
    match = re.fullmatch(r'(\d{6,})\.txt', basename)
    if match:
        return match.group(1)

    return None

def local_post_source_url(path):
    status_id = xueqiu_status_id_from_source(path)
    if status_id:
        return xueqiu_status_url(status_id)
    return f"file://{os.path.abspath(path)}"

def cache_xueqiu_post(text, source_url):
    """缓存成功抓到的雪球正文，避免下次运行完全依赖实时接口。"""
    status_id = xueqiu_status_id_from_source(source_url)
    if not status_id or not text.strip():
        return

    date_match = re.search(r'(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日', text)
    if date_match:
        y, m, d = map(int, date_match.groups())
        filename = f"{y:04d}-{m:02d}-{d:02d}-{status_id}.txt"
    else:
        filename = f"{status_id}.txt"

    os.makedirs(XUEQIU_LOCAL_POST_DIR, exist_ok=True)
    path = os.path.join(XUEQIU_LOCAL_POST_DIR, filename)
    if os.path.exists(path):
        return

    with open(path, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    log(f"🗂️ 已缓存雪球帖子: {path}")

def request_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode('utf-8')
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            preview = strip_tags(body)[:120].replace("\n", " ")
            raise RuntimeError(f"响应不是 JSON，可能被登录或滑块验证拦截: {preview}") from e

def fetch_xueqiu_status_text(status_id):
    """读取雪球帖子。公开接口常被 WAF/登录拦截；支持 XUEQIU_COOKIE 提升成功率。"""
    source_url = xueqiu_status_url(status_id)
    cookie = os.environ.get("XUEQIU_COOKIE", "").strip()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Referer": "https://xueqiu.com/",
        "Accept": "application/json,text/plain,*/*",
    }
    if cookie:
        headers["Cookie"] = cookie

    api_url = f"https://xueqiu.com/statuses/show.json?id={urllib.parse.quote(status_id)}"
    data = request_json(api_url, headers=headers)
    if data.get("error_code"):
        raise RuntimeError(f"雪球接口返回错误 {data.get('error_code')}: {data.get('error_description')}")
    text = strip_tags(data.get("text", ""))
    title = strip_tags(data.get("title", ""))
    return "\n".join(part for part in [title, text] if part), source_url

def fetch_xueqiu_timeline_posts():
    """用登录态读取纬班长时间线，自动发现最新雅砻江帖子。"""
    cookie = os.environ.get("XUEQIU_COOKIE", "").strip()
    if not cookie:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Referer": f"https://xueqiu.com/u/{XUEQIU_USER_ID}",
        "Accept": "application/json,text/plain,*/*",
        "Cookie": cookie,
    }
    url = (
        "https://xueqiu.com/v4/statuses/user_timeline.json?"
        f"user_id={urllib.parse.quote(XUEQIU_USER_ID)}&page=1&count={XUEQIU_FETCH_LIMIT}"
    )
    data = request_json(url, headers=headers)
    statuses = data.get("statuses") or data.get("list") or []
    posts = []
    for item in statuses:
        title = strip_tags(item.get("title", ""))
        text = strip_tags(item.get("text", ""))
        combined = "\n".join(part for part in [title, text] if part)
        if "雅砻江主要库" not in combined:
            continue
        status_id = str(item.get("id") or item.get("status_id") or "")
        source_url = f"https://xueqiu.com/{XUEQIU_USER_ID}/{status_id}" if status_id else f"https://xueqiu.com/u/{XUEQIU_USER_ID}"
        posts.append((combined, source_url))
    return posts

def iter_xueqiu_text_sources():
    for path in sorted(glob.glob(os.path.join(XUEQIU_LOCAL_POST_DIR, "*.txt"))):
        with open(path, "r", encoding="utf-8") as f:
            yield f.read(), local_post_source_url(path)

    try:
        for text, source_url in fetch_xueqiu_timeline_posts():
            cache_xueqiu_post(text, source_url)
            yield text, source_url
    except Exception as e:
        log(f"⚠️ 雪球时间线读取失败: {e}")

    for status_id in XUEQIU_STATUS_IDS:
        try:
            text, source_url = fetch_xueqiu_status_text(status_id)
            cache_xueqiu_post(text, source_url)
            yield text, source_url
        except Exception as e:
            log(f"⚠️ 雪球帖子 {status_id} 读取失败: {e}")


def iter_wechat_text_sources():
    """读取已校验的纬班长微信公众号文章缓存。"""
    url_file = os.path.abspath(WECHAT_ARTICLE_URL_FILE)
    for path in sorted(glob.glob(os.path.join(WECHAT_LOCAL_POST_DIR, "*.txt"))):
        if os.path.abspath(path) == url_file:
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        source_match = re.search(r'^来源\s*[:：]\s*(\S+)', text, re.M)
        source_url = source_match.group(1) if source_match else f"file://{os.path.abspath(path)}"
        yield text, source_url


def configured_wechat_article_urls():
    """读取待抓取的原始公众号文章链接，不把索引摘要当作数据源。"""
    global DISCOVERED_WECHAT_ARTICLES
    DISCOVERED_WECHAT_ARTICLES = []
    candidates = []
    raw_urls = os.environ.get("WECHAT_ARTICLE_URLS", "")
    candidates.extend(re.split(r"[\s,;]+", raw_urls))

    if os.path.isfile(WECHAT_ARTICLE_URL_FILE):
        with open(WECHAT_ARTICLE_URL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line:
                    candidates.append(line)

    # Sogou is used only as a discovery index.  The returned original URL is
    # passed to wechat_crawler, whose full article content and six-row check
    # remain the admission gate for the database.
    try:
        from sogou_weixin_discovery import discover_wechat_articles

        discovered_articles = discover_wechat_articles()
        DISCOVERED_WECHAT_ARTICLES = discovered_articles
        discovered = [article["url"] for article in discovered_articles]
        if discovered:
            log(f"🔎 Sogou 发现 {len(discovered)} 个公众号原文链接。")
            candidates.extend(discovered)
        else:
            log("ℹ️ Sogou 未发现新的纬班长雅砻江公众号原文。")
    except Exception as exc:
        log(f"⚠️ Sogou 公众号文章发现失败，继续使用已配置链接: {exc}")

    urls = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or not re.match(r"^https://mp\.weixin\.qq\.com/s(?:/|\?)", candidate):
            continue
        if candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
    return urls


def cached_wechat_source_urls():
    """返回已有缓存中的原始公众号链接，避免重复抓取同一篇文章。"""
    urls = set()
    for path in sorted(glob.glob(os.path.join(WECHAT_LOCAL_POST_DIR, "*.txt"))):
        if os.path.abspath(path) == os.path.abspath(WECHAT_ARTICLE_URL_FILE):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            log(f"⚠️ 读取公众号缓存失败 {path}: {exc}")
            continue
        source_match = re.search(r'^来源\s*[:：]\s*(\S+)', text, re.M)
        if source_match and re.match(r"^https://mp\.weixin\.qq\.com/s(?:/|\?)", source_match.group(1)):
            urls.add(source_match.group(1))
    return urls


def normalize_wechat_article_title(title):
    return re.sub(r"\s+", "", (title or "")).strip()


def cached_wechat_article_titles():
    """返回已通过六库校验的缓存标题，抵御 Sogou 签名 URL 每次变化。"""
    titles = set()
    for path in sorted(glob.glob(os.path.join(WECHAT_LOCAL_POST_DIR, "*.txt"))):
        if os.path.abspath(path) == os.path.abspath(WECHAT_ARTICLE_URL_FILE):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
        except OSError:
            continue
        if first_line:
            titles.add(normalize_wechat_article_title(first_line.lstrip("# ")))
    return titles


def wechat_article_cache_text(article, source_url):
    """将 crawler 结果整理为项目现有解析器可识别的缓存文本。"""
    markdown = article.get("markdown", "") or ""
    # 解析器需要正文数字；图片仍由 crawler 负责修复，但不把图片 URL 当作数据。
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip()
    lines = [article.get("title", "").strip()]
    if article.get("author"):
        lines.append(f"公众号：{article['author'].strip()}")
    if article.get("publish_time"):
        lines.append(f"发布于：{article['publish_time'].strip()}")
    lines.extend([
        f"来源：{source_url}",
        "说明：使用公开 wechat-article-crawler 抓取原文；仅在六库字段完整且日期可解析时自动入库。",
        "",
        text,
        "",
    ])
    return "\n".join(lines)


def validate_wechat_rows(rows, source_url):
    """要求六个对象和必需字段齐全，防止验证码页或半张表进入数据库。"""
    expected_names = set(XUEQIU_RESERVOIR_NAMES)
    actual_names = {row.get("zhanming") for row in rows}
    if len(rows) != 6 or actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        raise ValueError(f"六库数据不完整，缺少: {', '.join(missing) or '对象重复'} ({source_url})")

    required_fields = ("ksw", "rkll", "ckll")
    for row in rows:
        missing = [field for field in required_fields if row.get(field) in (None, "")]
        if row.get("zhanming") != "桐子林" and row.get("xsl") is None:
            missing.append("xsl")
        if missing:
            raise ValueError(f"{row.get('zhanming')} 缺少字段: {', '.join(missing)} ({source_url})")


def crawl_new_wechat_articles():
    """抓取配置的原始公众号链接；失败时跳过，不影响官方数据流程。"""
    global GENERATED_WECHAT_CACHE_FILES
    urls = configured_wechat_article_urls()
    if not urls:
        log("ℹ️ 未配置待抓取的公众号原始链接，跳过自动 crawler。")
        return

    try:
        from wechat_crawler import crawl_wechat_article
    except Exception as exc:
        log(f"⚠️ 微信公众号 crawler 不可用，跳过自动抓取: {exc}")
        return

    cached_urls = cached_wechat_source_urls()
    cached_titles = cached_wechat_article_titles()
    discovered_by_url = {
        article["url"]: article for article in DISCOVERED_WECHAT_ARTICLES
    }
    for source_url in urls:
        if source_url in cached_urls:
            log(f"⏭️ 公众号文章已缓存，跳过重复抓取: {source_url}")
            continue
        discovered_hint = discovered_by_url.get(source_url, {})
        title_hint = normalize_wechat_article_title(discovered_hint.get("title", ""))
        if title_hint and title_hint in cached_titles:
            log(f"⏭️ 公众号文章标题已缓存，跳过新的签名链接: {discovered_hint.get('title')}")
            continue
        try:
            article = asyncio.run(crawl_wechat_article(source_url))
            author = article.get("author", "")
            if "纬班长" not in f"{author} {article.get('title', '')}":
                raise ValueError(f"未确认公众号为纬班长，识别作者: {author or '空'}")

            cache_text = wechat_article_cache_text(article, source_url)
            rows = parse_xueqiu_reservoir_rows(
                cache_text,
                source_url,
                source_name=WECHAT_SOURCE,
                note="微信公众号原文 crawler 自动抓取并完成六库校验",
            )
            validate_wechat_rows(rows, source_url)
            record_dates = {row["record_time"][:10] for row in rows}
            if len(record_dates) != 1:
                raise ValueError(f"六库表格日期不一致: {sorted(record_dates)}")

            os.makedirs(WECHAT_LOCAL_POST_DIR, exist_ok=True)
            record_date = next(iter(record_dates))
            url_fingerprint = __import__("hashlib").sha1(source_url.encode("utf-8")).hexdigest()[:10]
            cache_path = os.path.join(
                WECHAT_LOCAL_POST_DIR,
                f"{record_date}-weibanzhang-auto-{url_fingerprint}.txt",
            )
            temp_path = f"{cache_path}.tmp.{os.getpid()}"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(cache_text)
            os.replace(temp_path, cache_path)
            GENERATED_WECHAT_CACHE_FILES.append(cache_path)
            cached_urls.add(source_url)
            cached_titles.add(normalize_wechat_article_title(article.get("title", "")))
            log(f"✅ 公众号文章已抓取并通过六库校验: {source_url} -> {cache_path}")
        except Exception as exc:
            log(f"⚠️ 公众号文章未通过自动抓取/校验，保留旧数据: {source_url}: {exc}")


def parse_xueqiu_reservoir_rows(text, source_url, source_name=None, note=None):
    """解析纬班长雪球或公众号文章中的“水位/蓄量/入库/出库”行。"""
    rows = []
    date_match = re.search(r'(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日', text)
    if not date_match:
        log(f"⚠️ 纬班长来源缺少表格日期，跳过解析: {source_url}")
        return []

    if source_name is None:
        source_name = WECHAT_SOURCE if "mp.weixin.qq.com" in (source_url or "") else XUEQIU_SOURCE
    if note is None:
        note = "微信公众号文章截图人工核验" if source_name == WECHAT_SOURCE else "雪球帖子解析"

    normalized_text = re.sub(r'[；;]', '\n', text)
    known_names = "|".join(re.escape(name) for name in XUEQIU_RESERVOIR_NAMES)
    name_pattern = rf'({known_names})(?:水库|水电站|水文站)?'
    # 文章正文的概览句会先枚举库名（例如“锦屏一级、官地、二滩……”）。
    # 只有紧跟表格日期/水位的库名才是实际数据块的起点。
    reservoir_matches = [
        match for match in re.finditer(name_pattern, normalized_text)
        if re.search(
            r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日|水位",
            normalized_text[match.end():match.end() + 120],
        )
    ]
    for index, match in enumerate(reservoir_matches):
        # 公众号文章通常把一个库的水位、入库、出库、蓄水量拆成多行；
        # 按相邻库名切块后再解析，同时兼容雪球的一行式记录。
        chunk_end = reservoir_matches[index + 1].start() if index + 1 < len(reservoir_matches) else len(normalized_text)
        chunk = normalized_text[match.start():chunk_end]
        if not chunk.strip():
            continue
        name = match.group(1).strip()
        markdown_gap = r'\**\s*'
        water = re.search(
            rf'水位\s*[:：]?\s*{markdown_gap}([0-9]+(?:\.[0-9]+)?)\s*m?',
            chunk,
            re.I,
        )
        capacity = re.search(
            rf'蓄(?:水)?量(?:\([^)]*\))?\s*[:：]?\s*{markdown_gap}'
            r'([0-9]+(?:\.[0-9]+)?)\s*亿?m?[³3]?',
            chunk,
        )
        inflow = re.search(
            rf'入库(?:流量)?(?:\([^)]*\))?\s*[:：]?\s*{markdown_gap}'
            r'([0-9]+(?:\.[0-9]+)?)',
            chunk,
        )
        outflow = re.search(
            rf'出库(?:流量)?(?:\([^)]*\))?\s*[:：]?\s*{markdown_gap}'
            r'([0-9]+(?:\.[0-9]+)?)',
            chunk,
        )
        if name == "桐子林" and not inflow and not outflow:
            station_flow = re.search(
                rf'流量(?:\([^)]*\))?\s*[:：]?\s*{markdown_gap}'
                r'([0-9]+(?:\.[0-9]+)?)',
                chunk,
            )
            if station_flow:
                # 文章对桐子林水文站只给一个流量，沿用项目既有兼容约定。
                inflow = station_flow
                outflow = station_flow

        if not any([water, capacity, inflow, outflow]):
            continue

        row_date_match = re.search(r'(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日', chunk)
        row_date_match = row_date_match or date_match
        y, m, d = map(int, row_date_match.groups())
        record_time = f"{y:04d}-{m:02d}-{d:02d} 08:00:00"

        capacity_value = None
        if capacity:
            capacity_number = safe_float(capacity.group(1), 0)
            if "亿" in capacity.group(0):
                capacity_value = capacity_number * 100
            else:
                capacity_value = capacity_number
            if name == "桐子林" and capacity_value == 0:
                capacity_value = None

        rows.append({
            "zhanming": name,
            "ksw": water.group(1) if water else None,
            "rkll": inflow.group(1) if inflow else None,
            "ckll": outflow.group(1) if outflow else None,
            "xsl": capacity_value,
            "energy_level": None,
            "record_time": record_time,
            "source": source_name,
            "source_url": source_url,
            "note": note,
        })

    deduped = {}
    for row in rows:
        deduped[row["zhanming"]] = row
    return list(deduped.values())

def fetch_xueqiu_supplemental_data():
    all_rows = []
    for text, source_url in iter_xueqiu_text_sources():
        parsed = parse_xueqiu_reservoir_rows(text, source_url)
        if parsed:
            log(f"✅ 雪球补充源解析到 {len(parsed)} 条: {source_url}")
            all_rows.extend(parsed)

    for text, source_url in iter_wechat_text_sources():
        parsed = parse_xueqiu_reservoir_rows(
            text,
            source_url,
            source_name=WECHAT_SOURCE,
            note="微信公众号文章截图人工核验",
        )
        if parsed:
            log(f"✅ 微信公众号补充源解析到 {len(parsed)} 条: {source_url}")
            all_rows.extend(parsed)

    if not all_rows:
        log("⚠️ 纬班长补充源未解析到有效数据。")
    return all_rows

def fetch_and_store_data():
    log("🚀 启动自动化浏览器...")
    all_data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--no-proxy-server']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            log(f"🔗 正在访问页面...")
            open_target_page(page)

            input_box = wait_for_station_input(page)

            for name in RESERVOIR_NAMES:
                log(f"🔍 正在查询: {name}...")
                input_box.fill("")
                input_box.fill(name)
                page.wait_for_timeout(1500)

                try:
                    with page.expect_response("**/gateway.do", timeout=20000) as response_info:
                        page.locator("button.blue_button:has-text('搜索')").click()

                    response = response_info.value
                    if response.ok:
                        outer_data = response.json()
                        if 'data' in outer_data and isinstance(outer_data['data'], str):
                            inner_data = json.loads(outer_data['data'])
                            res_list = inner_data.get('result', {}).get('data', {}).get('list', [])
                            for item in res_list:
                                if item.get('zhanming') == name:
                                    all_data.append(item)
                                    break
                except Exception as e:
                    log(f"❌ 查询 {name} 失败: {e}")
        except Exception as e:
            log(f"⚠️ 四川政务公开抓取失败，继续尝试雪球补充源: {e}")
        finally:
            browser.close()

    crawl_new_wechat_articles()
    xueqiu_data = fetch_xueqiu_supplemental_data()
    combined_data = all_data + xueqiu_data

    if combined_data:
        return save_to_sqlite(combined_data)

    log("⚠️ 未抓取到有效数据。")
    raise RuntimeError("未抓取到有效数据")

def git_push_data():
    repo_path = os.path.dirname(os.path.abspath(__file__))

    def run_git(args, step_name, timeout=180):
        env = os.environ.copy()
        # 任何 git 交互都必须失败退出，避免 launchd / 定时任务长时间挂起。
        env["GIT_TERMINAL_PROMPT"] = "0"
        # 仓库可能保留上一次 ClashMac 使用的端口；显式采用本次运行探测到的
        # 代理，避免 repo-local http.proxy 覆盖 run_scraper.sh 的环境变量。
        proxy_url = env.get("HTTPS_PROXY") or env.get("HTTP_PROXY")
        if args and args[0] == "git" and proxy_url:
            args = [
                "git",
                "-c", f"http.proxy={proxy_url}",
                "-c", f"https.proxy={proxy_url}",
                *args[1:],
            ]
        result = subprocess.run(
            args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
        if result.stdout.strip():
            log(f"📄 {step_name} stdout: {result.stdout.strip()}")
        if result.returncode != 0:
            if result.stderr.strip():
                log(f"❌ {step_name} stderr: {result.stderr.strip()}")
            raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
        if result.stderr.strip():
            log(f"⚠️ {step_name} stderr: {result.stderr.strip()}")

    def push_with_retry():
        last_error = None
        for attempt in range(1, 4):
            try:
                log(f"📤 git push 尝试 {attempt}/3...")
                run_git(["git", "push", "origin", "main"], "git push", timeout=300)
                return
            except subprocess.TimeoutExpired as e:
                last_error = e
                log(f"⏱️ git push 第 {attempt}/3 次超时。")
            except subprocess.CalledProcessError as e:
                last_error = e
                log(f"❌ git push 第 {attempt}/3 次失败 (exit code {e.returncode})。")

        raise last_error

    try:
        log("🔄 正在推送更新至 GitHub...")
        run_git(["git", "add", "reservoirs.db"], "git add")
        for cache_path in GENERATED_WECHAT_CACHE_FILES:
            relative_path = os.path.relpath(cache_path, repo_path)
            if relative_path.startswith("../") or os.path.isabs(relative_path):
                raise RuntimeError(f"拒绝暂存仓库外的公众号缓存: {cache_path}")
            run_git(["git", "add", "--", relative_path], "git add 微信公众号缓存")

        commit_msg = f"Auto update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        run_git(["git", "commit", "-m", commit_msg], "git commit")

        push_with_retry()
        log("🚀 数据同步成功！")
    except subprocess.TimeoutExpired as e:
        log(f"⏱️ Git 操作超时: {e.cmd}，已终止本次推送，避免任务卡死。")
        raise
    except subprocess.CalledProcessError as e:
        combined_output = f"{getattr(e, 'stdout', '')}\n{getattr(e, 'stderr', '')}".lower()
        if isinstance(e.cmd, (list, tuple)) and len(e.cmd) >= 2 and e.cmd[1] == "commit":
            if "nothing to commit" in combined_output or "working tree clean" in combined_output:
                log("😴 Git 没有新的变更，跳过推送。")
                return

        log(f"💥 Git 同步失败 (exit code {e.returncode})")
        raise
    except Exception as e:
        log(f"⚠️ Git 操作失败: {e}")

if __name__ == "__main__":
    init_db()
    added_count = fetch_and_store_data()
    if added_count > 0 or GENERATED_WECHAT_CACHE_FILES:
        log(f"💾 本次更新了 {added_count} 条数据。")
        git_push_data()
    else:
        log("😴 数据与上一次完全一致，无需上传。")
