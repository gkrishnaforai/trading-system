-- Essential Scheduler Functions
-- Run this to create the core scheduler functions

-- Function to schedule symbol refresh
CREATE OR REPLACE FUNCTION schedule_symbol_refresh(
    p_symbol VARCHAR,
    p_data_type VARCHAR,
    p_interval INTEGER DEFAULT 15
)
RETURNS BOOLEAN AS $$
BEGIN
    INSERT INTO data_refresh_schedule (
        symbol, data_type, refresh_interval, next_refresh, is_active
    ) VALUES (
        UPPER(p_symbol), 
        p_data_type, 
        p_interval, 
        CURRENT_TIMESTAMP + INTERVAL '1 minute',
        TRUE
    )
    ON CONFLICT (symbol, data_type) 
    DO UPDATE SET
        refresh_interval = EXCLUDED.refresh_interval,
        next_refresh = EXCLUDED.next_refresh,
        is_active = EXCLUDED.is_active,
        updated_at = CURRENT_TIMESTAMP;
    
    RETURN TRUE;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Error scheduling refresh for % %: %', p_symbol, p_data_type, SQLERRM;
    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Function to remove symbol schedule
CREATE OR REPLACE FUNCTION remove_symbol_schedule(
    p_symbol VARCHAR,
    p_data_type VARCHAR DEFAULT NULL
)
RETURNS INTEGER AS $$
BEGIN
    IF p_data_type IS NOT NULL THEN
        DELETE FROM data_refresh_schedule 
        WHERE symbol = UPPER(p_symbol) AND data_type = p_data_type;
        RETURN 1;
    ELSE
        DELETE FROM data_refresh_schedule 
        WHERE symbol = UPPER(p_symbol);
        RETURN (SELECT COUNT(*) FROM data_refresh_schedule WHERE symbol = UPPER(p_symbol));
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to get overdue refreshes
CREATE OR REPLACE FUNCTION get_overdue_refreshes()
RETURNS TABLE(symbol VARCHAR, data_type VARCHAR, minutes_overdue INTEGER) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.symbol,
        s.data_type,
        EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - s.next_refresh))/60 as minutes_overdue
    FROM data_refresh_schedule s
    WHERE s.is_active = TRUE 
      AND s.next_refresh <= CURRENT_TIMESTAMP
    ORDER BY minutes_overdue DESC;
END;
$$ LANGUAGE plpgsql;
