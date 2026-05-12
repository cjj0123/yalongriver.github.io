import sys
import datetime
import sqlite3
import json
import subprocess
import os
from playwright.sync_api import sync_playwright

# --- 配置区 ---
TARGET_URL = "https://tftb.sczwfw.gov.cn:8085/hos-server/pub/jmas/jmasbucket/jmopen_files/unzip/6e5032129863494a94bb2e2e7a2e9748/sltqszdsksssqxxpc/index.html#/"
DB_FILE = "reservoirs.db"
RESERVOIR_NAMES = ["二滩", "锦屏一级", "官地"]
LOG_FILE = "scrape.log"

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
    if 'percentage' not in columns:
        cursor.execute('ALTER TABLE reservoir_data ADD COLUMN percentage REAL')
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
        val_capacity = safe_float(res.get("xsl")) / 100.0

        # --- 去重核心逻辑 ---
        cursor.execute('''
            SELECT water_level, inflow, outflow, capacity_level 
            FROM reservoir_data 
            WHERE name = ? 
            ORDER BY record_time DESC LIMIT 1
        ''', (val_name,))
        last_record = cursor.fetchone()

        if last_record:
            if (val_water_level == last_record[0] and 
                val_inflow == last_record[1] and 
                val_outflow == last_record[2] and 
                val_capacity == last_record[3]):
                log(f"⏭️ {val_name} 数据未变化，跳过写入。")
                continue

        cursor.execute('''
            INSERT INTO reservoir_data (name, record_time, water_level, inflow, outflow, capacity_level)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (val_name, now, val_water_level, val_inflow, val_outflow, val_capacity))
        new_records_count += 1
        log(f"✅ {val_name} 数据已更新: 水位 {val_water_level}m")

    conn.commit()
    conn.close()
    return new_records_count

def fetch_and_store_data():
    log("🚀 启动自动化浏览器...")
    new_rows = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            log(f"🔗 正在访问页面...")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

            all_data = []
            page.wait_for_selector('input[placeholder="站名"]', timeout=30000)

            for name in RESERVOIR_NAMES:
                log(f"🔍 正在查询: {name}...")
                input_box = page.locator('input[placeholder="站名"]')
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

            if all_data:
                new_rows = save_to_sqlite(all_data)
            else:
                log("⚠️ 未抓取到有效数据。")

        except Exception as e:
            log(f"💥 严重错误: {e}")
        finally:
            browser.close()
    return new_rows

def git_push_data():
    try:
        repo_path = os.path.dirname(os.path.abspath(__file__))
        os.chdir(repo_path)

        log("🔄 正在推送更新至 GitHub...")
        subprocess.run(["git", "add", "reservoirs.db"], check=True)

        commit_msg = f"Auto update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)

        subprocess.run(["git", "push"], check=True)
        log("🚀 数据同步成功！")
    except subprocess.CalledProcessError as e:
        log(f"💡 Git 提示：跳过推送 (exit code {e.returncode})")
    except Exception as e:
        log(f"⚠️ Git 操作失败: {e}")

if __name__ == "__main__":
    init_db()
    added_count = fetch_and_store_data()
    if added_count > 0:
        log(f"💾 本次更新了 {added_count} 条数据。")
        git_push_data()
    else:
        log("😴 数据与上一次完全一致，无需上传。")
