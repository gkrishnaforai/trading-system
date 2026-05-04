"""
Price Targets Repository
Handles storage and retrieval of price targets data
"""
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.repositories.base_repository import BaseRepository


class PriceTargetsRepository(BaseRepository):
    """Repository for price targets data"""
    
    def store_price_targets(self, symbol: str, targets: List[Dict[str, Any]]) -> bool:
        """Store price targets in database"""
        try:
            rows = []
            for target in targets:
                row = {
                    'stock_symbol': symbol,
                    'target_date': self._parse_date(target.get('targetDate')),
                    'analyst_name': target.get('analystName'),
                    'analyst_firm': target.get('analystFirm'),
                    'price_target': target.get('priceTarget'),
                    'rating': target.get('rating'),
                    'price_when_posted': target.get('priceWhenPosted'),
                    'published_at': self._parse_date(target.get('publishedAt')),
                    'created_at': datetime.utcnow(),
                    'payload': target
                }
                rows.append(row)
            
            # Create table if not exists
            self._ensure_table()
            
            # Upsert price targets
            BaseRepository.upsert_many(
                table='price_targets',
                unique_columns=['stock_symbol', 'target_date', 'analyst_name'],
                rows=rows
            )
            
            return True
            
        except Exception as e:
            print(f"Error storing price targets for {symbol}: {e}")
            return False
    
    def get_recent_targets(self, symbol: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent price targets for a symbol"""
        try:
            query = """
            SELECT payload, target_date, analyst_name, price_target, rating
            FROM price_targets
            WHERE stock_symbol = %s
              AND target_date >= NOW() - INTERVAL '%s days'
            ORDER BY target_date DESC
            """
            result = db.execute_query(query, (symbol, days))
            return [dict(row) for row in result]
        except Exception:
            return []
    
    def get_consensus_target(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get consensus price target for a symbol"""
        try:
            query = """
            SELECT 
                AVG(price_target) as consensus_target,
                COUNT(*) as analyst_count,
                MAX(target_date) as latest_date
            FROM price_targets
            WHERE stock_symbol = %s
              AND target_date >= NOW() - INTERVAL '30 days'
            """
            result = db.execute_query(query, (symbol,))
            if result:
                return dict(result[0])
            return None
        except Exception:
            return None
    
    def _ensure_table(self):
        """Ensure price_targets table exists"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS price_targets (
            stock_symbol VARCHAR(20) NOT NULL,
            target_date DATE NOT NULL,
            analyst_name VARCHAR(100),
            analyst_firm VARCHAR(100),
            price_target DECIMAL(10,2),
            rating VARCHAR(20),
            price_when_posted DECIMAL(10,2),
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payload JSONB,
            PRIMARY KEY (stock_symbol, target_date, analyst_name)
        );
        
        CREATE INDEX IF NOT EXISTS idx_price_targets_symbol_date ON price_targets(stock_symbol, target_date DESC);
        CREATE INDEX IF NOT EXISTS idx_price_targets_symbol_target ON price_targets(stock_symbol, price_target);
        """
        db.execute_query(create_table_sql)
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None
