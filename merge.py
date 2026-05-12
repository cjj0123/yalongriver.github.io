import sqlite3
import os

OLD_DB = "old_reservoirs.db"
NEW_DB = "reservoirs.db"

def merge_and_deduplicate():
    if not os.path.exists(OLD_DB):
        print(f"❌ 错误：找不到文件 {OLD_DB}")
        return

    conn = sqlite3.connect(NEW_DB)
    cursor = conn.cursor()

    try:
        # 1. 挂载旧数据库
        cursor.execute(f"ATTACH DATABASE '{OLD_DB}' AS old")
        
        # 2. 合并数据并进行单位转换 (capacity_level * 100)
        print("1️⃣ 正在转换并导入历史数据...")
        cursor.execute("""
            INSERT INTO reservoir_data (name, record_time, water_level, inflow, outflow, capacity_level)
            SELECT 
                name, 
                record_time, 
                water_level, 
                inflow, 
                outflow, 
                (capacity_level * 100) 
            FROM old.reservoir_data
        """)
        
        # 3. 执行去重逻辑
        # 原理：根据 水库名称(name) 和 记录时间(record_time) 分组，保留每组中 ID 最小的记录，删除其余的
        print("2️⃣ 正在清理重复记录...")
        cursor.execute("""
            DELETE FROM reservoir_data 
            WHERE id NOT IN (
                SELECT MIN(id) 
                FROM reservoir_data 
                GROUP BY name, record_time
            )
        """)
        
        conn.commit()
        print(f"✅ 处理完成！当前数据库总条数: {cursor.execute('SELECT COUNT(*) FROM reservoir_data').fetchone()[0]}")

    except Exception as e:
        print(f"❌ 操作失败: {e}")
    finally:
        try:
            cursor.execute("DETACH DATABASE old")
        except:
            pass
        conn.close()

if __name__ == "__main__":
    merge_and_deduplicate()