import sqlite3

def run_fix():
    # 1. 连接数据库
    conn = sqlite3.connect('reservoirs.db')
    cursor = conn.cursor()

    try:
        # 2. 执行你提供的 SQL 语句
        print("🚀 正在批量修正 capacity_level (放大100倍)...")
        sql = "UPDATE reservoir_data SET capacity_level = capacity_level * 100 WHERE capacity_level < 1 AND capacity_level > 0;"
        cursor.execute(sql)
        
        # 3. 提交更改并查看影响行数
        conn.commit()
        print(f"✅ 修正完成！共处理了 {cursor.rowcount} 条记录。")

    except Exception as e:
        print(f"❌ 运行失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_fix()