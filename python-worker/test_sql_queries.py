#!/usr/bin/env python3
"""
SQL Query Validation Script
Tests all problematic SQL queries from admin dashboard
"""

import sys
import os
from typing import Dict, List, Tuple, Any

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database import db

class SQLQueryValidator:
    """Validate SQL queries for admin dashboard"""
    
    def __init__(self):
        self.results = []
        
    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test results"""
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
        self.results.append({
            'test': test_name,
            'status': status,
            'details': details
        })
    
    def get_table_columns(self, table_name: str) -> List[str]:
        """Get column names for a table"""
        try:
            query = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = :table_name
                ORDER BY ordinal_position;
            """
            result = db.execute_query(query, {"table_name": table_name})
            return [row['column_name'] for row in result] if result else []
        except Exception as e:
            self.log_test(f"Get Columns {table_name}", "FAIL", str(e))
            return []
    
    def test_safe_summary_query(self, table_name: str) -> bool:
        """Test safe summary query based on available columns"""
        try:
            columns = self.get_table_columns(table_name)
            
            # Determine the best date column to use
            date_column = None
            if 'date' in columns:
                date_column = 'date'
            elif 'created_at' in columns:
                date_column = 'created_at'
            elif 'updated_at' in columns:
                date_column = 'updated_at'
            elif 'published_at' in columns:
                date_column = 'published_at'
            elif 'published_date' in columns:
                date_column = 'published_date'
            elif 'as_of_date' in columns:
                date_column = 'as_of_date'
            elif 'earnings_date' in columns:
                date_column = 'earnings_date'
            elif 'grade_date' in columns:
                date_column = 'grade_date'
            elif 'consensus_date' in columns:
                date_column = 'consensus_date'
            elif 'fiscal_date_ending' in columns:
                date_column = 'fiscal_date_ending'
            elif 'fiscal_date_or_period' in columns:
                date_column = 'fiscal_date_or_period'
            elif 'action_date' in columns:
                date_column = 'action_date'
            elif 'data_date' in columns:
                date_column = 'data_date'
            elif 'ts' in columns:
                date_column = 'ts'
            
            # Build safe query
            if 'symbol' in columns and date_column:
                # Standard case: symbol + date
                query = f"""
                    SELECT 
                        COUNT(*) as total_records,
                        MAX({date_column}) as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table_name}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table_name}'
                        ) as column_count
                    FROM {table_name}
                """
                
                # Quality query
                quality_query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE symbol IS NOT NULL AND {date_column} IS NOT NULL) as non_null_rows,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND {date_column} IS NOT NULL) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as null_rate,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || {date_column}) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as duplicate_rate
                    FROM {table_name}
                """
                
            elif 'symbol' in columns:
                # Symbol only (no date)
                query = f"""
                    SELECT 
                        COUNT(*) as total_records,
                        MAX(CASE WHEN 'updated_at' = ANY(ARRAY[
                            'updated_at', 'created_at', 'published_at', 'published_date'
                        ]) AND updated_at IS NOT NULL THEN updated_at ELSE NULL END) as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table_name}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table_name}'
                        ) as column_count
                    FROM {table_name}
                """
                
                # Quality query
                quality_query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                        CASE 
                            WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                            ELSE 0.0 
                        END as null_rate,
                        0.0 as duplicate_rate
                    FROM {table_name}
                """
                
            elif date_column:
                # Date only (no symbol)
                query = f"""
                    SELECT 
                        COUNT(*) as total_records,
                        MAX({date_column}) as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table_name}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table_name}'
                        ) as column_count
                    FROM {table_name}
                """
                
                # Quality query
                quality_query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) as total_rows,
                        100.0 as null_rate,
                        0.0 as duplicate_rate
                    FROM {table_name}
                """
                
            else:
                # No standard columns, just basic count
                query = f"""
                    SELECT 
                        COUNT(*) as total_records,
                        NULL as last_updated,
                        pg_size_pretty(pg_total_relation_size('{table_name}')) as size_gb,
                        (
                            SELECT COUNT(*) 
                            FROM information_schema.columns 
                            WHERE table_name = '{table_name}'
                        ) as column_count
                    FROM {table_name}
                """
                
                # Quality query
                quality_query = f"""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) as total_rows,
                        100.0 as null_rate,
                        0.0 as duplicate_rate
                    FROM {table_name}
                """
            
            # Test summary query
            result = db.execute_query(query)
            if result:
                row = result[0]
                self.log_test(f"Summary Query {table_name}", "PASS", 
                             f"Records: {row.get('total_records', 0)}, Size: {row.get('size_gb', 'N/A')}")
                
                # Test quality query
                quality_result = db.execute_query(quality_query)
                if quality_result:
                    quality_row = quality_result[0]
                    self.log_test(f"Quality Query {table_name}", "PASS", 
                                 f"Null Rate: {quality_row.get('null_rate', 0):.1f}%")
                    return True
                else:
                    self.log_test(f"Quality Query {table_name}", "FAIL", "No quality results")
                    return False
            else:
                self.log_test(f"Summary Query {table_name}", "FAIL", "No summary results")
                return False
                
        except Exception as e:
            self.log_test(f"Query Test {table_name}", "FAIL", str(e))
            return False
    
    def test_problematic_tables(self) -> Dict[str, Any]:
        """Test tables that had issues"""
        problematic_tables = [
            "data_ingestion_events",
            "share_float", 
            "risk_factors",
            "weekly_aggregation",
            "growth_calculations"
        ]
        
        results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'table_results': {}
        }
        
        print("🔍 Testing Problematic Tables")
        print("=" * 40)
        
        for table in problematic_tables:
            print(f"\nTesting: {table}")
            
            # Check if table exists
            try:
                exists_query = """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = :table_name
                    );
                """
                result = db.execute_query(exists_query, {"table_name": table})
                table_exists = result[0]['exists'] if result else False
                
                if not table_exists:
                    self.log_test(f"Table {table}", "FAIL", "Table does not exist")
                    results['failed_tests'] += 1
                    results['table_results'][table] = {'exists': False, 'status': 'FAIL'}
                    continue
                
                self.log_test(f"Table {table}", "PASS", "Table exists")
                results['passed_tests'] += 1
                results['table_results'][table] = {'exists': True, 'status': 'PASS'}
                
                # Get table info
                columns = self.get_table_columns(table)
                self.log_test(f"Columns {table}", "INFO", f"Found {len(columns)} columns: {', '.join(columns[:5])}{'...' if len(columns) > 5 else ''}")
                
                # Test safe query
                results['total_tests'] += 1
                if self.test_safe_summary_query(table):
                    results['passed_tests'] += 1
                    results['table_results'][table]['query_test'] = 'PASS'
                else:
                    results['failed_tests'] += 1
                    results['table_results'][table]['query_test'] = 'FAIL'
                
            except Exception as e:
                self.log_test(f"Table {table}", "FAIL", str(e))
                results['failed_tests'] += 1
                results['table_results'][table] = {'exists': False, 'status': 'FAIL', 'error': str(e)}
        
        return results
    
    def generate_fixed_queries(self) -> Dict[str, str]:
        """Generate fixed queries for admin.py"""
        fixes = {}
        
        # Get all tables and their columns
        all_tables = [
            "data_ingestion_events", "share_float", "risk_factors",
            "raw_market_data_daily", "indicators_daily", "stocks",
            "market_news", "earnings_data", "fundamentals_snapshots",
            "stock_grades", "stock_consensus_history", "financial_ratios",
            "financial_statements", "income_statements", "balance_sheets",
            "cash_flow_statements", "corporate_actions", "fmp_market_news",
            "short_interest", "short_volume", "share_float", "risk_factors"
        ]
        
        print("\n🔧 Generating Fixed Queries")
        print("=" * 40)
        
        for table in all_tables:
            try:
                columns = self.get_table_columns(table)
                if not columns:
                    continue
                
                # Determine best date column
                date_column = None
                for col in ['date', 'created_at', 'updated_at', 'published_at', 'published_date', 
                           'as_of_date', 'earnings_date', 'grade_date', 'consensus_date', 
                           'fiscal_date_ending', 'fiscal_date_or_period', 'action_date', 
                           'data_date', 'ts']:
                    if col in columns:
                        date_column = col
                        break
                
                # Generate summary query
                if date_column:
                    summary_query = f"""elif table == "{table}":
            # Use {date_column} for {table}
            query = f'''
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE DATE({date_column}) = CURRENT_DATE) as today_records,
                    MAX({date_column}) as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            '''"""
                else:
                    summary_query = f"""elif table == "{table}":
            # No date column found for {table}, use basic count
            query = f'''
                SELECT 
                    '{table}' as table_name,
                    COUNT(*) as total_records,
                    0 as today_records,
                    NULL as last_updated,
                    pg_size_pretty(pg_total_relation_size('{table}')) as size_gb,
                    (
                        SELECT COUNT(*) 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}'
                    ) as column_count
                FROM {table}
            '''"""
                
                # Generate quality query
                if 'symbol' in columns and date_column:
                    quality_query = f"""elif table == "{table}":
            # Use symbol and {date_column} for {table}
            quality_query = f'''
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL AND {date_column} IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL AND {date_column} IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(DISTINCT symbol || {date_column}) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as duplicate_rate
                FROM {table}
            '''"""
                elif 'symbol' in columns:
                    quality_query = f"""elif table == "{table}":
            # Use symbol only for {table} (no date column)
            quality_query = f'''
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE symbol IS NOT NULL) as non_null_rows,
                    CASE 
                        WHEN COUNT(*) > 0 THEN COUNT(*) FILTER (WHERE symbol IS NOT NULL) * 100.0 / COUNT(*)
                        ELSE 0.0 
                    END as null_rate,
                    0.0 as duplicate_rate
                FROM {table}
            '''"""
                else:
                    quality_query = f"""elif table == "{table}":
            # No symbol/date columns for {table}, use basic count
            quality_query = f'''
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) as total_rows,
                    100.0 as null_rate,
                    0.0 as duplicate_rate
                FROM {table}
            '''"""
                
                fixes[table] = {
                    'summary_query': summary_query,
                    'quality_query': quality_query,
                    'has_symbol': 'symbol' in columns,
                    'date_column': date_column,
                    'columns': columns
                }
                
                print(f"✅ Generated queries for {table}")
                
            except Exception as e:
                print(f"❌ Failed to generate queries for {table}: {e}")
        
        return fixes
    
    def run_validation(self) -> Dict[str, Any]:
        """Run complete validation"""
        print("🚀 SQL Query Validation Suite")
        print("=" * 50)
        
        # Test problematic tables
        problematic_results = self.test_problematic_tables()
        
        # Generate fixed queries
        fixed_queries = self.generate_fixed_queries()
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 VALIDATION SUMMARY")
        print("=" * 50)
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r['status'] == 'PASS'])
        failed_tests = len([r for r in self.results if r['status'] == 'FAIL'])
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"📈 Success Rate: {(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "N/A")
        
        return {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'problematic_results': problematic_results,
            'fixed_queries': fixed_queries,
            'detailed_results': self.results
        }

def main():
    """Main validation runner"""
    validator = SQLQueryValidator()
    results = validator.run_validation()
    
    # Save fixed queries to file
    if results['fixed_queries']:
        print(f"\n📝 Fixed queries saved to 'fixed_queries.py'")
        with open('fixed_queries.py', 'w') as f:
            f.write("# Fixed SQL Queries for Admin Dashboard\n\n")
            f.write("# Summary Queries\n")
            for table, queries in results['fixed_queries'].items():
                f.write(f"# {table}\n")
                f.write(queries['summary_query'])
                f.write("\n")
            
            f.write("\n# Quality Queries\n")
            for table, queries in results['fixed_queries'].items():
                f.write(f"# {table}\n")
                f.write(queries['quality_query'])
                f.write("\n")
    
    return results

if __name__ == "__main__":
    main()
