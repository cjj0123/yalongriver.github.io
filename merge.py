import sqlite3

# 配置路径
OLD_DB = "old_reservoirs.db"  # 你的历史数据文件
NEW_DB = "reservoirs.db"      # 你现在的生产环境文件

def merge_databases():
    conn = sqlite3.connect(NEW_DB)
    cursor = conn.cursor()

    try:
        # 1. 挂载旧数据库，起个别名叫 'old'
        cursor.execute(f"ATTACH DATABASE '{OLD_DB}' AS old")
        
        # 2. 将数据从 old.reservoir_data 导入到现有的 reservoir_data
        # 使用 INSERT OR IGNORE 可以防止因主键或唯一约束导致的报错
        # 如果你想保留所有记录，直接 INSERT INTO 即可
        print("正在合并历史数据...")
        cursor.execute("""
            INSERT INTO reservoir_data (name, record_time, water_level, inflow, outflow, capacity_level)
            SELECT name, record_time, water_level, inflow, outflow, capacity_level 
            FROM old.reservoir_data
        """)
        
        conn.commit()
        # 3. 卸载旧库
        cursor.execute("DETACH DATABASE old")
        print(f"✅ 合并成功！影响行数: {cursor.rowcount}")

    except Exception as e:
        print(f"❌ 合并失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    merge_databases()