-- EMCT migration: signals去重 + UNIQUE约束
-- 日期: 2026-07-18
-- 执行: sqlite3 backend/backend/data/emct.db < this_file.sql

-- Step 1: 清理每组(code,date)重复，保留最新id
DELETE FROM signals WHERE id NOT IN (
    SELECT MAX(id) FROM signals GROUP BY code, date
);
SELECT changes() AS 'duplicates_removed';

-- Step 2: 加唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_code_date ON signals(code, date);

-- Step 3: 验证
SELECT COUNT(*) AS 'total_remaining' FROM signals;
SELECT COUNT(*) AS 'duplicate_groups' FROM (
    SELECT code, date, COUNT(*) as cnt FROM signals
    GROUP BY code, date HAVING cnt > 1
);
