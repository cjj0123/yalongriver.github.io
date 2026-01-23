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

def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservoir_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT NOT NULL, 
            record_time DATETIME NOT NULL,
            water_level REAL, 
            inflow REAL, 
            outflow REAL, 
            capacity_level REAL
    );
    ''')
    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成。")

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
        val_capacity = safe_float(res.get("xsl")) / 100.0  # 换算为亿立方米

        # --- 去重核心逻辑 ---
        # 获取该水库最新的一条记录
        cursor.execute('''
            SELECT water_level, inflow, outflow, capacity_level 
            FROM reservoir_data 
            WHERE name = ? 
            ORDER BY record_time DESC LIMIT 1
        ''', (val_name,))
        last_record = cursor.fetchone()

        # 对比核心数值（若数值完全一致则跳过）
        if last_record:
            if (val_water_level == last_record[0] and 
                val_inflow == last_record[1] and 
                val_outflow == last_record[2] and 
                val_capacity == last_record[3]):
                print(f"⏭️ {val_name} 数据未变化，跳过写入。")
                continue

        # 写入新数据
        cursor.execute('''
            INSERT INTO reservoir_data (name, record_time, water_level, inflow, outflow, capacity_level)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (val_name, now, val_water_level, val_inflow, val_outflow, val_capacity))
        new_records_count += 1
        print(f"✅ {val_name} 数据已更新: 水位 {val_water_level}m")
        
    conn.commit()
    conn.close()
    return new_records_count

def fetch_and_store_data():
    print("🚀 启动自动化浏览器...")
    new_rows = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            print(f"🔗 正在访问页面...")
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            all_data = []
            page.wait_for_selector('input[placeholder="站名"]', timeout=30000)
            
            for name in RESERVOIR_NAMES:
                print(f"🔍 正在查询: {name}...")
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
                    print(f"❌ 查询 {name} 失败: {e}")

            if all_data:
                new_rows = save_to_sqlite(all_data) 
            else:
                print("⚠️ 未抓取到有效数据。")

        except Exception as e:
            print(f"💥 严重错误: {e}")
        finally:
            browser.close()
    return new_rows

def git_push_data():
    try:
        # 获取仓库根目录，防止在 OneDrive 路径下执行错误
        repo_path = os.path.dirname(os.path.abspath(__file__))
        os.chdir(repo_path)
        
        print("🔄 正在推送更新至 GitHub...")
        subprocess.run(["git", "add", "reservoirs.db"], check=True)
        
        # 产生 commit 信息
        commit_msg = f"Auto update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        
        subprocess.run(["git", "push"], check=True)
        print("🚀 数据同步成功！")
    except subprocess.CalledProcessError:
        print("💡 Git 提示：没有检测到文件变化，跳过推送。")
    except Exception as e:
        print(f"⚠️ Git 操作失败: {e}")

if __name__ == "__main__":
    init_db()
    # 只有当数据库有新行写入时，才触发 Git 推送
    added_count = fetch_and_store_data()
    if added_count > 0:
        print(f"💾 本次更新了 {added_count} 条数据。")
        git_push_data()
    else:
        print("😴 数据与上一次完全一致，无需上传。")