"""
Database Statistics API
Provides table record counts and statistics for UI components
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from typing import Dict, Any, List
from app.database import get_db
from app.observability.logging import get_logger

logger = get_logger("db_stats_api")

router = APIRouter(tags=["database-stats"])

@router.get("/table-stats")
async def get_table_stats() -> Dict[str, Any]:
    """Get record counts for all data tables"""
    try:
        from app.database import get_db
        db = get_db()
        
        # Define tables to check
        tables = [
            "raw_market_data_daily",
            "raw_market_data_intraday", 
            "indicators_daily",
            "fundamentals_snapshots",
            "financial_statements",
            "financial_ratios",
            "stock_news",
            "earnings_data",
            "stock_insights_snapshots",
            "short_interest",
            "short_volume",
            "share_float",
            "risk_factors",
            "analyst_ratings",
            "price_targets", 
            "consensus_data",
            "stock_grades"
        ]
        
        stats = {}
        
        for table in tables:
            try:
                # Get record count
                count_query = f"SELECT COUNT(*) as count FROM {table}"
                result = db.execute_query(count_query)
                count = result[0]['count'] if result else 0
                
                # Get latest date if available
                latest_date = None
                date_columns = {
                    "raw_market_data_daily": "date",
                    "raw_market_data_intraday": "ts",
                    "fundamentals_snapshots": "as_of_date", 
                    "financial_statements": "fiscal_period",
                    "financial_ratios": "fiscal_date_ending",
                    "indicators_daily": "date",
                    "stock_news": "published_at",
                    "earnings_data": "earnings_date",
                    "stock_insights_snapshots": "generated_at",
                    "short_interest": "settlement_date",
                    "short_volume": "date",
                    "share_float": "date",
                    "risk_factors": "filing_date",
                    "analyst_ratings": "rating_date",
                    "price_targets": "target_date",
                    "consensus_data": "consensus_date",
                    "stock_grades": "grade_date"
                }
                
                if table in date_columns and count > 0:
                    date_col = date_columns[table]
                    date_query = f"SELECT MAX({date_col}) as latest FROM {table}"
                    date_result = db.execute_query(date_query)
                    latest_date = date_result[0]['latest'] if date_result else None
                
                stats[table] = {
                    "record_count": count,
                    "latest_date": str(latest_date) if latest_date else None
                }
                
            except Exception as e:
                logger.warning(f"Error getting stats for table {table}: {e}")
                stats[table] = {
                    "record_count": 0,
                    "latest_date": None,
                    "error": str(e)
                }
        
        return {
            "success": True,
            "tables": stats,
            "total_tables": len(tables)
        }
        
    except Exception as e:
        logger.error(f"Error getting table stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/data-type-stats")
async def get_data_type_stats() -> Dict[str, Any]:
    """Get statistics by data type"""
    try:
        # Get table stats first
        table_stats_response = await get_table_stats()
        table_stats = table_stats_response["tables"]
        
        # Map data types to tables
        data_type_mapping = {
            "price_historical": "raw_market_data_daily",
            "price_intraday_5m": "raw_market_data_intraday",
            "fundamentals": "fundamentals_snapshots",
            "income_statements": "financial_statements",
            "balance_sheets": "financial_statements", 
            "cash_flow_statements": "financial_statements",
            "financial_ratios": "financial_ratios",
            "indicators": "indicators_daily",
            "news": "stock_news",
            "earnings": "earnings_data",
            "key_metrics_ttm": "stock_insights_snapshots",
            "financial_growth": "stock_insights_snapshots",
            "stock_grades": "stock_insights_snapshots",
            "analyst_ratings": "stock_insights_snapshots",
            "price_targets": "stock_insights_snapshots",
            "consensus_data": "stock_insights_snapshots",
            "institutional_buying": "stock_insights_snapshots",
            "earnings_transcripts": "stock_insights_snapshots",
            "short_interest": "short_interest",
            "short_volume": "short_volume",
            "share_float": "share_float",
            "risk_factors": "risk_factors"
        }
        
        data_type_stats = {}
        
        for data_type, table in data_type_mapping.items():
            if table in table_stats:
                data_type_stats[data_type] = {
                    "table": table,
                    "record_count": table_stats[table]["record_count"],
                    "latest_date": table_stats[table]["latest_date"]
                }
            else:
                data_type_stats[data_type] = {
                    "table": table,
                    "record_count": 0,
                    "latest_date": None,
                    "error": "Table not found"
                }
        
        return {
            "success": True,
            "data_types": data_type_stats,
            "total_data_types": len(data_type_mapping)
        }
        
    except Exception as e:
        logger.error(f"Error getting data type stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/profile-stats/{profile_name}")
async def get_profile_stats(profile_name: str) -> Dict[str, Any]:
    """Get statistics for a specific profile"""
    try:
        # Import profiles
        from app.ingestion.profiles import get_profile
        
        try:
            profile = get_profile(profile_name)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")
        
        # Get data type stats
        data_type_stats_response = await get_data_type_stats()
        all_data_type_stats = data_type_stats_response["data_types"]
        
        # Calculate profile-specific stats
        profile_data_types = [dt.value for dt in profile.data_types]
        profile_stats = {
            "profile_name": profile_name,
            "data_types_count": len(profile.data_types),
            "window_days": profile.window_days,
            "data_types": {}
        }
        
        total_records = 0
        
        for data_type in profile_data_types:
            if data_type in all_data_type_stats:
                stats = all_data_type_stats[data_type]
                profile_stats["data_types"][data_type] = stats
                total_records += stats["record_count"]
            else:
                profile_stats["data_types"][data_type] = {
                    "record_count": 0,
                    "latest_date": None,
                    "error": "Data type not found"
                }
        
        profile_stats["total_records"] = total_records
        
        return {
            "success": True,
            "profile": profile_stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profile stats for {profile_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/all-profiles-stats")
async def get_all_profiles_stats() -> Dict[str, Any]:
    """Get statistics for all profiles"""
    try:
        from app.ingestion.profiles import INGESTION_PROFILES
        
        profiles_stats = {}
        
        for profile_name in INGESTION_PROFILES.keys():
            try:
                profile_response = await get_profile_stats(profile_name)
                profiles_stats[profile_name] = profile_response["profile"]
            except Exception as e:
                logger.warning(f"Error getting stats for profile {profile_name}: {e}")
                profiles_stats[profile_name] = {
                    "error": str(e),
                    "data_types_count": 0,
                    "total_records": 0
                }
        
        return {
            "success": True,
            "profiles": profiles_stats,
            "total_profiles": len(INGESTION_PROFILES)
        }
        
    except Exception as e:
        logger.error(f"Error getting all profiles stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-analyst-ratings-storage")
async def test_analyst_ratings_storage():
    """Test calling analyst ratings storage method directly"""
    try:
        from app.services.optimized_fmp_loader import OptimizedFMLoader
        from app.database import get_db
        
        # Create loader instance
        loader = OptimizedFMLoader()
        
        # Test with mock data
        mock_ratings = [
            {
                "analystName": "Test Analyst",
                "analystFirm": "Test Firm", 
                "rating": "BUY",
                "ratingAction": "UPGRADE",
                "priceTarget": 100.50,
                "publishedAt": "2026-02-21T10:00:00Z",
                "ratingDate": "2026-02-21"
            }
        ]
        
        # Test storage directly
        symbol = "TEST"
        stored_count = 0
        
        try:
            # Use direct database access like stock grades for consistency
            from app.database import get_db
            db = get_db()
            
            for rating in mock_ratings:
                try:
                    # Parse rating date
                    rating_date = rating.get("ratingDate") or rating.get("publishedAt")
                    if not rating_date:
                        continue
                    
                    from datetime import datetime
                    if isinstance(rating_date, str):
                        try:
                            rating_date = datetime.fromisoformat(rating_date.replace('Z', '+00:00')).date()
                        except:
                            rating_date = datetime.now().date()
                    elif isinstance(rating_date, datetime):
                        rating_date = rating_date.date()
                    
                    # Insert using direct SQL
                    query = """
                        INSERT INTO analyst_ratings (
                            symbol, rating_date, analyst_name, analyst_firm, rating, 
                            rating_action, price_target, published_at, payload
                        ) VALUES (
                            :symbol, :rating_date, :analyst_name, :analyst_firm, :rating,
                            :rating_action, :price_target, :published_at, :payload
                        )
                    """
                    
                    import json
                    
                    params = {
                        "symbol": symbol,
                        "rating_date": rating_date,
                        "analyst_name": rating.get("analystName", ""),
                        "analyst_firm": rating.get("analystFirm", ""),
                        "rating": rating.get("rating"),
                        "rating_action": rating.get("ratingAction"),
                        "price_target": rating.get("priceTarget"),
                        "published_at": rating.get("publishedAt"),
                        "payload": json.dumps(rating) if rating else "{}"
                    }
                    
                    db.execute_query(query, params)
                    stored_count += 1
                    
                except Exception as rating_error:
                    return {
                        "success": False,
                        "error": f"Could not store individual rating: {rating_error}"
                    }
            
            return {
                "success": True,
                "message": f"✅ Stored {stored_count} analyst ratings in database for {symbol}"
            }
            
        except Exception as db_error:
            return {
                "success": False,
                "error": f"Database error: {db_error}"
            }
        
    except Exception as e:
        logger.error(f"Error testing analyst ratings storage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-analyst-ratings-insert")
async def test_analyst_ratings_insert():
    """Test inserting data into analyst_ratings table"""
    try:
        from app.database import get_db
        from datetime import date
        
        db = get_db()
        
        # Test insert
        test_query = """
            INSERT INTO analyst_ratings (
                symbol, rating_date, analyst_name, analyst_firm, rating, 
                rating_action, price_target, published_at, payload
            ) VALUES (
                :symbol, :rating_date, :analyst_name, :analyst_firm, :rating,
                :rating_action, :price_target, :published_at, :payload
            )
        """
        
        import json

        params = {
            "symbol": "TEST",
            "rating_date": date.today(),
            "analyst_name": "Test Analyst",
            "analyst_firm": "Test Firm",
            "rating": "BUY",
            "rating_action": "UPGRADE",
            "price_target": 100.50,
            "published_at": "2026-02-21T10:00:00Z",
            "payload": json.dumps({"test": True})
        }
        
        db.execute_query(test_query, params)
        
        return {
            "success": True,
            "message": "Test data inserted successfully into analyst_ratings table"
        }
        
    except Exception as e:
        logger.error(f"Error testing analyst ratings insert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-table-columns")
async def check_table_columns(table_names: List[str]):
    """Check column names for specific tables"""
    try:
        from app.database import get_db
        db = get_db()
        
        results = {}
        
        for table_name in table_names:
            try:
                # Get column information
                columns_query = """
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = :table_name 
                    ORDER BY ordinal_position
                """
                columns = db.execute_query(columns_query, {"table_name": table_name})
                results[table_name] = {
                    "exists": True,
                    "columns": [{"name": col["column_name"], "type": col["data_type"]} for col in columns]
                }
            except Exception as e:
                results[table_name] = {
                    "exists": False,
                    "error": str(e)
                }
        
        return {"success": True, "results": results}
        
    except Exception as e:
        logger.error(f"Error checking table columns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-tables")
async def create_missing_tables():
    """Create missing database tables for analyst data"""
    try:
        from app.database import get_db
        db = get_db()
        
        # Create tables using SQLAlchemy models
        from app.db_storage.models import Base, AnalystRatings, PriceTargets, ConsensusData
        from sqlalchemy import create_engine
        
        # Get database engine from the database module
        engine = db.engine if hasattr(db, 'engine') else None
        if not engine:
            # Fallback: create engine from database URL
            from app.config import settings
            engine = create_engine(settings.DATABASE_URL)
        
        # Create all tables
        Base.metadata.create_all(engine)
        
        logger.info("✅ Created missing database tables")
        
        return {
            "success": True,
            "message": "Missing database tables created successfully",
            "tables_created": ["analyst_ratings", "price_targets", "consensus_data"]
        }
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))
