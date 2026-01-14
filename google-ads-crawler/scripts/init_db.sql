-- Initialize database extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create indexes that might not be created by SQLAlchemy
-- (SQLAlchemy handles most indexes, but we can add custom ones here)

-- Grant permissions (if needed for specific users)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO adscraper;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO adscraper;

-- Optional: Create materialized view for advertiser stats summary
-- This can speed up dashboard queries

-- CREATE MATERIALIZED VIEW IF NOT EXISTS advertiser_summary AS
-- SELECT
--     a.id,
--     a.domain,
--     a.company_name,
--     COUNT(DISTINCT kas.keyword_id) as total_keywords,
--     SUM(kas.appearance_count) as total_appearances,
--     AVG(kas.avg_position) as overall_avg_position,
--     SUM(kas.estimated_spend) as total_estimated_spend
-- FROM advertisers a
-- LEFT JOIN keyword_advertiser_stats kas ON a.id = kas.advertiser_id
-- GROUP BY a.id, a.domain, a.company_name;

-- CREATE UNIQUE INDEX IF NOT EXISTS advertiser_summary_id_idx ON advertiser_summary(id);

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized successfully';
END $$;
