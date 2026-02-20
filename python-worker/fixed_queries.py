# Fixed SQL Queries for Admin Dashboard

def get_summary_query(table: str) -> str:
    """Get summary query for a specific table"""
    
    # Summary Queries
    if table == "data_ingestion_events":
        # Use created_at for data_ingestion_events
        return '''
            SELECT 
                'data_ingestion_events' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('data_ingestion_events')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'data_ingestion_events'
                ) as column_count
            FROM data_ingestion_events
        '''
    
    elif table == "share_float":
        # Use created_at for share_float
        return '''
            SELECT 
                'share_float' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('share_float')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'share_float'
                ) as column_count
            FROM share_float
        '''
    
    elif table == "risk_factors":
        # Use created_at for risk_factors
        return '''
            SELECT 
                'risk_factors' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('risk_factors')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'risk_factors'
                ) as column_count
            FROM risk_factors
        '''
    
    elif table == "raw_market_data_daily":
        # Use date for raw_market_data_daily
        return '''
            SELECT 
                'raw_market_data_daily' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(date) = CURRENT_DATE) as today_records,
                MAX(date) as last_updated,
                pg_size_pretty(pg_total_relation_size('raw_market_data_daily')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'raw_market_data_daily'
                ) as column_count
            FROM raw_market_data_daily
        '''
    
    elif table == "indicators_daily":
        # Use date for indicators_daily
        return '''
            SELECT 
                'indicators_daily' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(date) = CURRENT_DATE) as today_records,
                MAX(date) as last_updated,
                pg_size_pretty(pg_total_relation_size('indicators_daily')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'indicators_daily'
                ) as column_count
            FROM indicators_daily
        '''
    
    elif table == "stocks":
        # Use created_at for stocks
        return '''
            SELECT 
                'stocks' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('stocks')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'stocks'
                ) as column_count
            FROM stocks
        '''
    
    elif table == "market_news":
        # Use created_at for market_news
        return '''
            SELECT 
                'market_news' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('market_news')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'market_news'
                ) as column_count
            FROM market_news
        '''
    
    elif table == "earnings_data":
        # Use created_at for earnings_data
        return '''
            SELECT 
                'earnings_data' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('earnings_data')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'earnings_data'
                ) as column_count
            FROM earnings_data
        '''
    
    elif table == "fundamentals_snapshots":
        # Use created_at for fundamentals_snapshots
        return '''
            SELECT 
                'fundamentals_snapshots' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('fundamentals_snapshots')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'fundamentals_snapshots'
                ) as column_count
            FROM fundamentals_snapshots
        '''
    
    elif table == "stock_grades":
        # Use created_at for stock_grades
        return '''
            SELECT 
                'stock_grades' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('stock_grades')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'stock_grades'
                ) as column_count
            FROM stock_grades
        '''
    
    elif table == "stock_consensus_history":
        # No date column found for stock_consensus_history, use basic count
        return '''
            SELECT 
                'stock_consensus_history' as table_name,
                COUNT(*) as total_records,
                0 as today_records,
                NULL as last_updated,
                pg_size_pretty(pg_total_relation_size('stock_consensus_history')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'stock_consensus_history'
                ) as column_count
            FROM stock_consensus_history
        '''
    
    elif table == "financial_ratios":
        # Use created_at for financial_ratios
        return '''
            SELECT 
                'financial_ratios' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('financial_ratios')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'financial_ratios'
                ) as column_count
            FROM financial_ratios
        '''
    
    elif table == "financial_statements":
        # Use created_at for financial_statements
        return '''
            SELECT 
                'financial_statements' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('financial_statements')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'financial_statements'
                ) as column_count
            FROM financial_statements
        '''
    
    elif table == "income_statements":
        # Use created_at for income_statements
        return '''
            SELECT 
                'income_statements' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('income_statements')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'income_statements'
                ) as column_count
            FROM income_statements
        '''
    
    elif table == "balance_sheets":
        # Use created_at for balance_sheets
        return '''
            SELECT 
                'balance_sheets' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('balance_sheets')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'balance_sheets'
                ) as column_count
            FROM balance_sheets
        '''
    
    elif table == "cash_flow_statements":
        # Use created_at for cash_flow_statements
        return '''
            SELECT 
                'cash_flow_statements' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('cash_flow_statements')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'cash_flow_statements'
                ) as column_count
            FROM cash_flow_statements
        '''
    
    elif table == "corporate_actions":
        # Use created_at for corporate_actions
        return '''
            SELECT 
                'corporate_actions' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('corporate_actions')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'corporate_actions'
                ) as column_count
            FROM corporate_actions
        '''
    
    elif table == "fmp_market_news":
        # Use created_at for fmp_market_news
        return '''
            SELECT 
                'fmp_market_news' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('fmp_market_news')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'fmp_market_news'
                ) as column_count
            FROM fmp_market_news
        '''
    
    elif table == "short_interest":
        # Use created_at for short_interest
        return '''
            SELECT 
                'short_interest' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('short_interest')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'short_interest'
                ) as column_count
            FROM short_interest
        '''
    
    elif table == "short_volume":
        # Use created_at for short_volume
        return '''
            SELECT 
                'short_volume' as table_name,
                COUNT(*) as total_records,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_records,
                MAX(created_at) as last_updated,
                pg_size_pretty(pg_total_relation_size('short_volume')) as size_gb,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = 'short_volume'
                ) as column_count
            FROM short_volume
        '''
    
    else:
        raise ValueError(f"Unknown table: {table}")


def get_quality_query(table: str) -> str:
    """Get quality query for a specific table"""
    
    # Quality Queries
    if table == "data_ingestion_events":
        # Use symbol and created_at for data_ingestion_events
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM data_ingestion_events
        '''
    
    elif table == "share_float":
        # Use symbol and created_at for share_float
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM share_float
        '''
    
    elif table == "risk_factors":
        # Use symbol and created_at for risk_factors
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM risk_factors
        '''
    
    elif table == "raw_market_data_daily":
        # Use symbol and date for raw_market_data_daily
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || date) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM raw_market_data_daily
        '''
    
    elif table == "indicators_daily":
        # Use symbol and date for indicators_daily
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND date IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || date) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM indicators_daily
        '''
    
    elif table == "stocks":
        # Use symbol and created_at for stocks
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM stocks
        '''
    
    elif table == "market_news":
        # Use symbol and created_at for market_news
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM market_news
        '''
    
    elif table == "earnings_data":
        # No symbol/date columns for earnings_data, use basic count
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) as total_rows,
                100.0 as null_rate,
                0.0 as duplicate_rate
            FROM earnings_data
        '''
    
    elif table == "fundamentals_snapshots":
        # Use symbol and created_at for fundamentals_snapshots
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM fundamentals_snapshots
        '''
    
    elif table == "stock_grades":
        # Use symbol and created_at for stock_grades
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM stock_grades
        '''
    
    elif table == "stock_consensus_history":
        # Use symbol only for stock_consensus_history (no date column)
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                0.0 as duplicate_rate
            FROM stock_consensus_history
        '''
    
    elif table == "financial_ratios":
        # Use symbol and created_at for financial_ratios
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM financial_ratios
        '''
    
    elif table == "financial_statements":
        # No symbol/date columns for financial_statements, use basic count
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) as total_rows,
                100.0 as null_rate,
                0.0 as duplicate_rate
            FROM financial_statements
        '''
    
    elif table == "income_statements":
        # Use symbol and created_at for income_statements
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM income_statements
        '''
    
    elif table == "balance_sheets":
        # Use symbol and created_at for balance_sheets
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM balance_sheets
        '''
    
    elif table == "cash_flow_statements":
        # Use symbol and created_at for cash_flow_statements
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM cash_flow_statements
        '''
    
    elif table == "corporate_actions":
        # No symbol/date columns for corporate_actions, use basic count
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) as total_rows,
                100.0 as null_rate,
                0.0 as duplicate_rate
            FROM corporate_actions
        '''
    
    elif table == "fmp_market_news":
        # No symbol/date columns for fmp_market_news, use basic count
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) as total_rows,
                100.0 as null_rate,
                0.0 as duplicate_rate
            FROM fmp_market_news
        '''
    
    elif table == "short_interest":
        # Use symbol and created_at for short_interest
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM short_interest
        '''
    
    elif table == "short_volume":
        # Use symbol and created_at for short_volume
        return '''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) as non_null_rows,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND created_at IS NOT NULL) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as null_rate,
                CASE 
                    WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || created_at) * 100.0 / COUNT(*)
                    ELSE 0.0 
                END as duplicate_rate
            FROM short_volume
        '''
    
    else:
        raise ValueError(f"Unknown table: {table}")


# Usage examples:
# query = get_summary_query("raw_market_data_daily")
# quality_query = get_quality_query("raw_market_data_daily")
