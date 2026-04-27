"""创建数据库的临时脚本"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# 连接参数
conn_params = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "123456"
}

db_name = "langgraphdb"

try:
    # 连接到 PostgreSQL 服务器
    conn = psycopg2.connect(**conn_params)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    # 检查数据库是否存在
    cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
    exists = cursor.fetchone()

    if not exists:
        cursor.execute(f"CREATE DATABASE {db_name}")
        print(f"✅ 数据库 '{db_name}' 创建成功!")
    else:
        print(f"ℹ️  数据库 '{db_name}' 已存在")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ 错误: {e}")
