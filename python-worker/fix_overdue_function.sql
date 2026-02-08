-- Fix the get_overdue_refreshes function
CREATE OR REPLACE FUNCTION get_overdue_refreshes()
RETURNS TABLE(symbol VARCHAR, data_type VARCHAR, minutes_overdue BIGINT) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.symbol,
        s.data_type,
        ROUND(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.next_refresh))/60)::BIGINT as minutes_overdue
    FROM data_refresh_schedule s
    WHERE s.is_active = TRUE 
      AND s.next_refresh <= CURRENT_TIMESTAMP
    ORDER BY minutes_overdue DESC;
END;
$$ LANGUAGE plpgsql;
