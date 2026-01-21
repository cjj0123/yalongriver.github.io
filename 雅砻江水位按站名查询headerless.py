import sys

import datetime



# --- 日志记录配置 ---

log_file_path = 'scraper_log.txt'

# 重定向标准输出和标准错误到日志文件

sys.stdout = open(log_file_path, 'a', encoding='utf-8')

sys.stderr = open(log_file_path, 'a', encoding='utf-8')



# 打印一条带时间戳的日志，表示脚本开始运行

print(f"\n--- Script started at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

# --- 日志记录配置结束 ---



import sqlite3

import datetime

import json

from playwright.sync_api import sync_playwright



# ==============================================================================

# ---【配置区】---

# ==============================================================================



TARGET_URL = "https://tftb.sczwfw.gov.cn:8085/hos-server/pub/jmas/jmasbucket/jmopen_files/unzip/6e5032129863494a94bb2e2e7a2e9748/sltqszdsksssqxxpc/index.html#/"

DB_FILE = "reservoirs.db"

RESERVOIR_NAMES = ["二滩", "锦屏一级", "官地"]



# ==============================================================================

# ---【代码主体，无需修改】---

# ==============================================================================



def init_db():

    """初始化数据库"""

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.cursor()

    cursor.execute('''

        CREATE TABLE IF NOT EXISTS reservoir_data (

            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, record_time DATETIME NOT NULL,

            water_level REAL, inflow REAL, outflow REAL, capacity_level REAL);

    ''')

    conn.commit()

    conn.close()

    print("数据库初始化完成。")



def fetch_and_store_data():

    """使用Playwright自动化浏览器获取数据，并进行双重JSON解包"""

    print("正在启动自动化浏览器...")

    with sync_playwright() as p:

        browser = None

        try:

            browser = p.chromium.launch(headless=True)

            page = browser.new_page()

            page.set_default_timeout(60000)



            print(f"正在访问目标网站: {TARGET_URL}")

            page.goto(TARGET_URL)



            print("等待页面加载完成并定位关键元素...")

            station_name_input = page.locator('input[placeholder="站名"]')

            station_name_input.wait_for(state="visible")

           

            query_button = page.locator("button.blue_button:has-text('搜索')")

            query_button.wait_for(state="visible")



            print("成功定位到'站名'输入框和'搜索'按钮。")



            all_data = []

            for name in RESERVOIR_NAMES:

                print(f"正在查询水库: {name}...")



                station_name_input.fill("")

                station_name_input.fill(name)

               

                page.wait_for_timeout(500)



                with page.expect_response("**/gateway.do", timeout=15000) as response_info:

                    query_button.click()



                response = response_info.value

                print(f"成功为'{name}'触发查询并捕获到网络响应！")



                if response.ok:

                    outer_data = response.json()

                   

                    # 【【【 关键的最终修正：双重JSON解包 】】】

                    if outer_data.get('data') and isinstance(outer_data['data'], str):

                        # 1. 先把'data'字段的值作为字符串取出来

                        inner_json_string = outer_data['data']

                        # 2. 对这个字符串再做一次JSON解析

                        inner_data = json.loads(inner_json_string)

                       

                        # 3. 从解包后的数据里提取我们真正要的列表

                        if inner_data.get('result', {}).get('data', {}).get('list'):

                            reservoir_list = inner_data['result']['data']['list']

                            found_exact_match = False

                            for item in reservoir_list:

                                # 【【【 关键的最终修正：使用解包后的正确键名 】】】

                                if item.get('zhanming') == name:

                                    all_data.append(item)

                                    found_exact_match = True

                                    print(f"-> 成功解析到 {name} 的精确数据。")

                                    # 为了获取最新的数据，我们只取第一条

                                    break

                            if not found_exact_match:

                                print(f"-> 警告：查询 {name} 后，在返回结果中未找到精确匹配项。")

                        else:

                            print(f"-> 警告：在解包后的JSON中未找到数据列表。")

                    else:

                        print(f"-> 警告：查询 {name} 后，响应中未找到预期的'data'字符串。")

                else:

                    print(f"-> 错误：查询 {name} 时，网络请求失败，状态码: {response.status}")



            # --- 数据存储逻辑 ---

            if not all_data:

                print("\n操作完成：未能获取到任何指定水库的数据。")

            else:

                print("\n操作完成：开始将所有捕获的数据存入数据库...")

                conn = sqlite3.connect(DB_FILE)

                cursor = conn.cursor()

                now = datetime.datetime.now()

               

                for reservoir in all_data:

                    # 【【【 关键的最终修正：使用解包后的正确键名 】】】

                    r_name = reservoir.get("zhanming")

                    water_level_str = reservoir.get("ksw")

                    inflow_str = reservoir.get("rkll")

                    outflow_str = reservoir.get("ckll")

                    # 蓄水量在您的日志里是 xsl，而不是之前猜测的 w 或中文

                    capacity_level_str = reservoir.get("xsl")

                   

                    water_level = float(water_level_str) if water_level_str and water_level_str != "--" else None

                    inflow = float(inflow_str) if inflow_str and inflow_str != "--" else None

                    outflow = float(outflow_str) if outflow_str and outflow_str != "--" else None

                    # 蓄水量单位是万立方米，我们需要换算成亿立方米

                    capacity_level = float(capacity_level_str) / 10000 if capacity_level_str and capacity_level_str != "--" else None

                   

                    cursor.execute('''

                        INSERT INTO reservoir_data (name, record_time, water_level, inflow, outflow, capacity_level)

                        VALUES (?, ?, ?, ?, ?, ?)

                    ''', (r_name, now, water_level, inflow, outflow, capacity_level))

                   

                    print(f"-> 成功存储数据: {r_name} (水位: {water_level})")

               

                conn.commit()

                conn.close()

                print("所有数据已成功存入数据库！")



        except Exception as e:

            print(f"自动化浏览器在执行过程中发生严重错误: {e}")

        finally:

            if browser and browser.is_connected():

                browser.close()

                print("浏览器已关闭。")



if __name__ == "__main__":

    init_db()

    fetch_and_store_data() 

driver.close() # 关闭浏览器
