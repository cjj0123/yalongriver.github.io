import sqlite3

def remove_duplicates():
    # 连接数据库
    conn = sqlite3.connect('reservoirs.db')
    cursor = conn.cursor()

    try:
        # 1. 统计清理前的总数
        cursor.execute("SELECT COUNT(*) FROM reservoir_data")
        total_before = cursor.fetchone()[0]
        print(f"📊 当前数据库共有 {total_before} 条记录。")

        # 2. 执行去重 SQL
        # 逻辑：按照名称、水位、入库、出库、蓄水量分组
        # 保留每一组中 ID 最小的那条，删除其他 ID
        dedup_sql = """
        DELETE FROM reservoir_data 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM reservoir_data 
            GROUP BY name, water_level, inflow, outflow, capacity_level
        );
        """
        cursor.execute(dedup_sql)
        
        # 3. 统计清理后的总数
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM reservoir_data")
        total_after = cursor.fetchone()[0]
        
        print(f"✅ 清理完成！")
        print(f"🧹 删除了 {total_before - total_after} 条重复记录。")
        print(f"📦 剩余唯一记录: {total_after} 条。")

    except Exception as e:
        print(f"❌ 清理失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    remove_duplicates()