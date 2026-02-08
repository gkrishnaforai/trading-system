"""
Universal Alert System Plugins
Industry-standard pluggable components for ANY event type
Follows SOLID principles and DRY implementation
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
import aiohttp
import os
from abc import ABC, abstractmethod

from app.database import db
from app.observability.logging import get_logger
from app.observability.metrics import get_metrics

logger = get_logger("universal_plugins")
metrics = get_metrics()

# ============================================================================
# DATA SOURCE PLUGINS - Collect data from ANY external source
# ============================================================================

class EarningsCalendarPlugin:
    """Plugin for collecting earnings calendar data"""
    
    def __init__(self):
        self.name = "earnings_calendar"
        self.supported_event_types = ["earnings_date", "earnings_surprise", "guidance_update"]
    
    async def collect_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect earnings calendar data from external APIs"""
        try:
            sources = config.get('sources', ['fmp'])
            events = []
            
            for source in sources:
                if source == 'fmp':
                    events.extend(await self._fetch_fmp_earnings(config))
                elif source == 'alpha_vantage':
                    events.extend(await self._fetch_av_earnings(config))
            
            logger.info(f"📊 Collected {len(events)} earnings events from {len(sources)} sources")
            metrics.increment('earnings_events_collected_total', len(events))
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error collecting earnings data: {e}")
            metrics.increment('earnings_collection_errors_total')
            return []
    
    async def _fetch_fmp_earnings(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch earnings data from FMP API"""
        try:
            api_key = config.get('fmp_api_key')
            if not api_key:
                logger.warning("⚠️ No FMP API key provided")
                return []
            
            url = f"https://financialmodelingprep.com/api/v3/earning_calendar"
            headers = {'apikey': api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._transform_earnings_data(data, 'fmp')
                    else:
                        logger.error(f"❌ FMP API error: {response.status}")
                        return []
                        
        except Exception as e:
            logger.error(f"❌ Error fetching FMP earnings: {e}")
            return []
    
    async def _fetch_av_earnings(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch earnings data from Alpha Vantage API"""
        try:
            api_key = config.get('alpha_vantage_api_key')
            if not api_key:
                logger.warning("⚠️ No Alpha Vantage API key provided")
                return []
            
            # Alpha Vantage earnings endpoint
            url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&apikey={api_key}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._transform_earnings_data(data.get('earningsCalendar', []), 'alpha_vantage')
                    else:
                        logger.error(f"❌ Alpha Vantage API error: {response.status}")
                        return []
                        
        except Exception as e:
            logger.error(f"❌ Error fetching Alpha Vantage earnings: {e}")
            return []
    
    def _transform_earnings_data(self, raw_data: List[Dict], source: str) -> List[Dict[str, Any]]:
        """Transform raw earnings data to universal event format"""
        events = []
        
        for item in raw_data:
            try:
                # Create universal event for earnings date
                event = {
                    'event_type': 'earnings_date',
                    'entity_type': 'stock',
                    'entity_id': item.get('symbol', '').upper(),
                    'event_data': {
                        'symbol': item.get('symbol', '').upper(),
                        'company_name': item.get('name', ''),
                        'earnings_date': item.get('date'),
                        'eps_estimate': item.get('epsEstimated'),
                        'eps_actual': item.get('epsActual'),
                        'revenue_estimate': item.get('revenueEstimated'),
                        'revenue_actual': item.get('revenueActual'),
                        'time': item.get('time', 'TBD'),
                        'source': source
                    },
                    'event_timestamp': self._parse_date(item.get('date')),
                    'data_source': source,
                    'confidence_score': 0.9
                }
                
                # Add surprise data if available
                if item.get('epsActual') and item.get('epsEstimated'):
                    eps_surprise = float(item.get('epsActual')) - float(item.get('epsEstimated'))
                    event['event_data']['eps_surprise'] = eps_surprise
                    event['event_data']['eps_surprise_percent'] = (eps_surprise / float(item.get('epsEstimated'))) * 100
                
                events.append(event)
                
            except Exception as e:
                logger.warning(f"⚠️ Error transforming earnings data: {e}")
                continue
        
        return events
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime"""
        try:
            if date_str:
                return datetime.strptime(date_str, '%Y-%m-%d')
        except:
            pass
        return datetime.now()
    
    def get_event_types(self) -> List[str]:
        return self.supported_event_types
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sources": {"type": "array", "items": {"type": "string"}},
                "fmp_api_key": {"type": "string"},
                "alpha_vantage_api_key": {"type": "string"}
            },
            "required": ["sources"]
        }

class AnalystGradesPlugin:
    """Plugin for collecting analyst grade changes"""
    
    def __init__(self):
        self.name = "analyst_grades"
        self.supported_event_types = ["grade_change", "consensus_update", "price_target_change"]
    
    async def collect_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect analyst grade changes"""
        try:
            sources = config.get('sources', ['fmp'])
            symbols = config.get('symbols')
            days = int(config.get('days', 7))
            events = []
            
            for source in sources:
                if source == 'fmp':
                    events.extend(await self._fetch_fmp_grades({
                        **config,
                        'symbols': symbols,
                        'days': days
                    }))
            
            logger.info(f"📈 Collected {len(events)} analyst grade events")
            metrics.increment('grade_events_collected_total', len(events))
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error collecting analyst grades: {e}")
            return []
    
    async def _fetch_fmp_grades(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch analyst grades from FMP"""
        try:
            symbols = config.get('symbols')
            days = int(config.get('days', 7))

            query = """
                SELECT symbol, grade_date, grading_company,
                       previous_grade, new_grade, action,
                       data_source, source_id,
                       created_at, updated_at
                FROM stock_grades
                WHERE COALESCE(updated_at, created_at, grade_date) >= NOW() - (:days || ' days')::interval
            """

            params: Dict[str, Any] = {'days': days}
            if symbols:
                query += " AND symbol = ANY(:symbols)"
                params['symbols'] = [s.upper() for s in symbols]

            query += " ORDER BY grade_date DESC LIMIT 1000"

            rows = db.execute_query(query, params)

            raw = []
            for row in rows or []:
                grade_date = row.get('grade_date')
                action = row.get('action')
                action_l = str(action or '').lower()
                if 'upgrade' in action_l:
                    change_type = 'upgrade'
                elif 'downgrade' in action_l:
                    change_type = 'downgrade'
                elif 'maintain' in action_l:
                    change_type = 'maintain'
                else:
                    change_type = 'maintain'

                row_source_id = row.get('source_id')
                if not row_source_id:
                    symbol = (row.get('symbol') or '').upper()
                    grading_company = row.get('grading_company') or ''
                    grade_date_str = grade_date.isoformat() if hasattr(grade_date, 'isoformat') else str(grade_date)
                    previous_grade = row.get('previous_grade') or ''
                    new_grade = row.get('new_grade') or ''
                    data_source = row.get('data_source') or 'local'
                    row_source_id = f"grade_change:{data_source}:{symbol}:{grading_company}:{grade_date_str}:{previous_grade}->{new_grade}:{action or ''}"

                raw.append({
                    'symbol': row.get('symbol'),
                    'companyName': '',
                    'ratingCompanyName': row.get('grading_company'),
                    'previousRating': row.get('previous_grade'),
                    'rating': row.get('new_grade'),
                    'ratingChangeDate': grade_date.isoformat() if hasattr(grade_date, 'isoformat') else str(grade_date),
                    'previousRatingScore': None,
                    'ratingScore': None,
                    'change_type': change_type,
                    'action': action,
                    'source_id': row_source_id,
                    'data_source': row.get('data_source') or 'local'
                })

            events = self._transform_grade_data(raw, 'local_db')
            for event in events:
                if 'change_type' in raw[0] and isinstance(event.get('event_data'), dict) and 'change_type' not in event['event_data']:
                    pass
            
            for event in events:
                if isinstance(event.get('event_data'), dict):
                    # Prefer action from DB if present in raw payload
                    event['event_data']['change_type'] = event['event_data'].get('change_type') or event['event_data'].get('action')

            return events
                        
        except Exception as e:
            logger.error(f"❌ Error fetching FMP grades: {e}")
            return []
    
    def _transform_grade_data(self, raw_data: List[Dict], source: str) -> List[Dict[str, Any]]:
        """Transform grade data to universal event format"""
        events = []
        
        for item in raw_data:
            try:
                event = {
                    'event_type': 'grade_change',
                    'entity_type': 'stock',
                    'entity_id': item.get('symbol', '').upper(),
                    'source_id': item.get('source_id'),
                    'event_data': {
                        'symbol': item.get('symbol', '').upper(),
                        'company_name': item.get('companyName', ''),
                        'rating': item.get('rating'),
                        'rating_score': item.get('ratingScore'),
                        'previous_rating': item.get('previousRating'),
                        'previous_rating_score': item.get('previousRatingScore'),
                        'rating_change_date': item.get('ratingChangeDate'),
                        # Standardize on grading_company; keep analyst_company for backward-compat.
                        'grading_company': item.get('ratingCompanyName', ''),
                        'analyst_company': item.get('ratingCompanyName', ''),
                        'source': source,
                        # change_type is normalized (upgrade/downgrade/maintain). action preserves the raw provider action if available.
                        'change_type': item.get('change_type'),
                        'action': item.get('action') or item.get('change_type'),
                        # Aliases for templates/UI
                        'previous_grade': item.get('previousRating'),
                        'new_grade': item.get('rating'),
                    },
                    'event_timestamp': self._parse_date(item.get('ratingChangeDate')),
                    'data_source': source,
                    'confidence_score': 0.85
                }
                
                # Calculate change type
                if not event['event_data'].get('change_type') and item.get('previousRatingScore') and item.get('ratingScore'):
                    score_change = item.get('ratingScore') - item.get('previousRatingScore')
                    if score_change > 0:
                        event['event_data']['change_type'] = 'upgrade'
                    elif score_change < 0:
                        event['event_data']['change_type'] = 'downgrade'
                    else:
                        event['event_data']['change_type'] = 'maintain'
                
                events.append(event)
                
            except Exception as e:
                logger.warning(f"⚠️ Error transforming grade data: {e}")
                continue
        
        return events
    
    def _parse_date(self, date_str: str) -> datetime:
        try:
            if date_str:
                return datetime.strptime(date_str, '%Y-%m-%d')
        except:
            pass
        return datetime.now()
    
    def get_event_types(self) -> List[str]:
        return self.supported_event_types
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sources": {"type": "array", "items": {"type": "string"}},
                "fmp_api_key": {"type": "string"}
            },
            "required": ["sources"]
        }

class PriceMovementsPlugin:
    """Plugin for collecting price movement data"""
    
    def __init__(self):
        self.name = "price_movements"
        self.supported_event_types = ["price_change", "volume_spike", "volatility_breakout"]
    
    async def collect_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect price movement data"""
        try:
            symbols = config.get('symbols', [])
            threshold_percent = config.get('threshold_percent', 5.0)
            events = []
            
            # Get current prices and compare with previous close
            for symbol in symbols:
                price_events = await self._analyze_price_movement(symbol, threshold_percent)
                events.extend(price_events)
            
            logger.info(f"💰 Collected {len(events)} price movement events")
            metrics.increment('price_events_collected_total', len(events))
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error collecting price movements: {e}")
            return []
    
    async def _analyze_price_movement(self, symbol: str, threshold_percent: float) -> List[Dict[str, Any]]:
        """Analyze price movement for a symbol"""
        try:
            # This would integrate with your existing market data system
            # For now, return mock data structure
            
            events = []
            
            # Mock price change event
            events.append({
                'event_type': 'price_change',
                'entity_type': 'stock',
                'entity_id': symbol.upper(),
                'event_data': {
                    'symbol': symbol.upper(),
                    'current_price': 150.25,
                    'previous_close': 142.50,
                    'price_change': 7.75,
                    'price_change_percent': 5.44,
                    'volume': 10500000,
                    'avg_volume': 8500000,
                    'source': 'market_data'
                },
                'event_timestamp': datetime.now(),
                'data_source': 'market_data',
                'confidence_score': 0.95
            })
            
            return events
            
        except Exception as e:
            logger.error(f"❌ Error analyzing price movement for {symbol}: {e}")
            return []
    
    def get_event_types(self) -> List[str]:
        return self.supported_event_types
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "threshold_percent": {"type": "number"}
            },
            "required": ["symbols"]
        }

# ============================================================================
# ALERT EVALUATOR PLUGINS - Evaluate if events trigger alerts
# ============================================================================

class EarningsAlertEvaluator:
    """Evaluator for earnings-related alerts"""
    
    def __init__(self):
        self.name = "earnings_evaluator"
        self.supported_alert_types = ["earnings", "earnings_preview", "earnings_surprise"]
    
    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate if event triggers earnings alert"""
        try:
            event_type = event.get('event_type')
            event_data = event.get('event_data', {})
            alert_filters = alert.get('event_filters', {})
            trigger_conditions = alert.get('trigger_conditions', {})
            
            # Check if event type matches alert
            if event_type not in ['earnings_date', 'earnings_surprise']:
                return {'should_trigger': False, 'reason': 'Event type not supported'}
            
            # Check symbol filters
            entity_filters = alert.get('entity_filters', {})
            if 'symbols' in entity_filters:
                if event.get('entity_id') not in entity_filters['symbols']:
                    return {'should_trigger': False, 'reason': 'Symbol not in alert filter'}
            
            # Check earnings date proximity
            if event_type == 'earnings_date':
                return self._evaluate_earnings_date(event_data, alert_filters, trigger_conditions)
            
            # Check earnings surprise
            elif event_type == 'earnings_surprise':
                return self._evaluate_earnings_surprise(event_data, alert_filters, trigger_conditions)
            
            return {'should_trigger': False, 'reason': 'No matching evaluation criteria'}
            
        except Exception as e:
            logger.error(f"❌ Error evaluating earnings alert: {e}")
            return {'should_trigger': False, 'reason': f'Evaluation error: {str(e)}'}
    
    def _evaluate_earnings_date(self, event_data: Dict, alert_filters: Dict, trigger_conditions: Dict) -> Dict[str, Any]:
        """Evaluate earnings date alert"""
        try:
            earnings_date = event_data.get('earnings_date')
            if not earnings_date:
                return {'should_trigger': False, 'reason': 'No earnings date'}
            
            # Parse earnings date
            earnings_dt = datetime.strptime(earnings_date, '%Y-%m-%d').date()
            today = datetime.now().date()
            days_until = (earnings_dt - today).days
            
            # Check if within alert window
            min_days = alert_filters.get('min_days_ahead', 1)
            max_days = alert_filters.get('max_days_ahead', 30)
            
            if min_days <= days_until <= max_days:
                match_score = self._calculate_match_score(days_until, event_data)
                urgency = self._calculate_urgency(days_until, event_data)
                
                return {
                    'should_trigger': True,
                    'match_score': match_score,
                    'urgency_level': urgency,
                    'trigger_reason': f"Earnings in {days_until} days for {event_data.get('symbol')}",
                    'trigger_details': {
                        'symbol': event_data.get('symbol'),
                        'earnings_date': earnings_date,
                        'days_until': days_until,
                        'company_name': event_data.get('company_name'),
                        'eps_estimate': event_data.get('eps_estimate'),
                        'time': event_data.get('time', 'TBD')
                    }
                }
            
            return {'should_trigger': False, 'reason': f'Earnings date not within alert window ({days_until} days)'}
            
        except Exception as e:
            logger.error(f"❌ Error evaluating earnings date: {e}")
            return {'should_trigger': False, 'reason': f'Date evaluation error: {str(e)}'}
    
    def _evaluate_earnings_surprise(self, event_data: Dict, alert_filters: Dict, trigger_conditions: Dict) -> Dict[str, Any]:
        """Evaluate earnings surprise alert"""
        try:
            surprise_percent = event_data.get('eps_surprise_percent', 0)
            min_surprise = alert_filters.get('min_surprise_percent', 5.0)
            
            if abs(surprise_percent) >= min_surprise:
                direction = 'beat' if surprise_percent > 0 else 'miss'
                match_score = min(abs(surprise_percent) * 2, 100)
                urgency = 'high' if abs(surprise_percent) > 20 else 'medium'
                
                return {
                    'should_trigger': True,
                    'match_score': match_score,
                    'urgency_level': urgency,
                    'trigger_reason': f"{event_data.get('symbol')} {direction} earnings by {abs(surprise_percent):.1f}%",
                    'trigger_details': {
                        'symbol': event_data.get('symbol'),
                        'eps_actual': event_data.get('eps_actual'),
                        'eps_estimate': event_data.get('eps_estimate'),
                        'surprise_percent': surprise_percent,
                        'direction': direction,
                        'company_name': event_data.get('company_name')
                    }
                }
            
            return {'should_trigger': False, 'reason': f'Surprise {surprise_percent:.1f}% below threshold {min_surprise}%'}
            
        except Exception as e:
            logger.error(f"❌ Error evaluating earnings surprise: {e}")
            return {'should_trigger': False, 'reason': f'Surprise evaluation error: {str(e)}'}
    
    def _calculate_match_score(self, days_until: int, event_data: Dict) -> float:
        """Calculate match score for earnings alert"""
        # Higher score for closer earnings dates
        if days_until <= 3:
            return 90.0
        elif days_until <= 7:
            return 75.0
        elif days_until <= 14:
            return 60.0
        else:
            return 45.0
    
    def _calculate_urgency(self, days_until: int, event_data: Dict) -> str:
        """Calculate urgency level"""
        if days_until <= 1:
            return 'critical'
        elif days_until <= 3:
            return 'high'
        elif days_until <= 7:
            return 'medium'
        else:
            return 'low'
    
    def get_supported_alert_types(self) -> List[str]:
        return self.supported_alert_types


class SignalGeneratedAlertEvaluator:
    """Evaluator for signal generation alerts"""

    def __init__(self):
        self.name = "signal_generated_evaluator"
        self.supported_alert_types = ["signal_generated"]

    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> Dict[str, Any]:
        try:
            event_type = event.get('event_type')
            event_data = event.get('event_data', {})
            if event_type != 'signal_generated':
                return {'should_trigger': False, 'reason': 'Event type not supported'}

            # Check symbol filters
            entity_filters = alert.get('entity_filters', {})
            if 'symbols' in entity_filters:
                if event.get('entity_id') not in entity_filters['symbols']:
                    return {'should_trigger': False, 'reason': 'Symbol not in alert filter'}

            signal_value = str(event_data.get('signal') or '').strip().upper()
            if signal_value not in {'BUY', 'SELL', 'HOLD'}:
                return {'should_trigger': False, 'reason': 'Invalid signal value'}

            alert_filters = alert.get('event_filters', {})

            allowed_signals = alert_filters.get('signals')
            if isinstance(allowed_signals, list) and allowed_signals:
                allowed_norm = {str(s).strip().upper() for s in allowed_signals if str(s).strip()}
                if allowed_norm and signal_value not in allowed_norm:
                    return {'should_trigger': False, 'reason': f'Signal {signal_value} not in allowed list'}

            confidence = float(event_data.get('confidence') or 0.0)
            min_conf = float(alert_filters.get('min_confidence', 0.0) or 0.0)
            if confidence < min_conf:
                return {'should_trigger': False, 'reason': f'Confidence {confidence:.2f} below threshold {min_conf:.2f}'}

            match_score = min(100.0, max(0.0, confidence * 100.0))
            urgency = 'high' if signal_value in {'BUY', 'SELL'} and confidence >= 0.7 else 'medium'

            return {
                'should_trigger': True,
                'match_score': match_score,
                'urgency_level': urgency,
                'trigger_reason': f"Signal {signal_value} for {event_data.get('symbol')} (conf={confidence:.2f})",
                'trigger_details': {
                    'symbol': event_data.get('symbol'),
                    'signal': signal_value,
                    'confidence': confidence,
                    'engine': event_data.get('engine'),
                    'asset_type': event_data.get('asset_type'),
                    'target_date': event_data.get('target_date'),
                    'run_id': event_data.get('run_id'),
                },
            }
        except Exception as e:
            logger.error(f"❌ Error evaluating signal generated alert: {e}")
            return {'should_trigger': False, 'reason': f'Evaluation error: {str(e)}'}

    def get_supported_alert_types(self) -> List[str]:
        return self.supported_alert_types


class ConsensusUpdateAlertEvaluator:
    def __init__(self):
        self.name = "consensus_update_evaluator"
        self.supported_alert_types = ["consensus_update"]

    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> Dict[str, Any]:
        try:
            event_type = event.get('event_type')
            event_data = event.get('event_data', {})
            if event_type != 'consensus_update':
                return {'should_trigger': False, 'reason': 'Event type not supported'}

            entity_filters = alert.get('entity_filters', {})
            if 'symbols' in entity_filters:
                if event.get('entity_id') not in entity_filters['symbols']:
                    return {'should_trigger': False, 'reason': 'Symbol not in alert filter'}

            prev_c = event_data.get('previous_consensus')
            new_c = event_data.get('new_consensus')
            if prev_c == new_c:
                return {'should_trigger': False, 'reason': 'Consensus did not change'}

            alert_filters = alert.get('event_filters', {})
            min_analysts = int(alert_filters.get('min_analyst_count', 0) or 0)
            total_analysts = int(event_data.get('total_analysts', 0) or 0)
            if total_analysts < min_analysts:
                return {'should_trigger': False, 'reason': f'Analyst count {total_analysts} below threshold {min_analysts}'}

            match_score = 80.0
            urgency = 'high'
            return {
                'should_trigger': True,
                'match_score': match_score,
                'urgency_level': urgency,
                'trigger_reason': f"Consensus changed for {event_data.get('symbol')} from {prev_c} to {new_c}",
                'trigger_details': {
                    'symbol': event_data.get('symbol'),
                    'previous_consensus': prev_c,
                    'new_consensus': new_c,
                    'total_analysts': total_analysts,
                    'distribution': event_data.get('distribution', {}),
                }
            }
        except Exception as e:
            logger.error(f"❌ Error evaluating consensus update alert: {e}")
            return {'should_trigger': False, 'reason': f'Evaluation error: {str(e)}'}

    def get_supported_alert_types(self) -> List[str]:
        return self.supported_alert_types


class PriceTargetChangeAlertEvaluator:
    def __init__(self):
        self.name = "price_target_change_evaluator"
        self.supported_alert_types = ["price_target_change"]

    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> Dict[str, Any]:
        try:
            event_type = event.get('event_type')
            event_data = event.get('event_data', {})
            if event_type != 'price_target_change':
                return {'should_trigger': False, 'reason': 'Event type not supported'}

            entity_filters = alert.get('entity_filters', {})
            if 'symbols' in entity_filters:
                if event.get('entity_id') not in entity_filters['symbols']:
                    return {'should_trigger': False, 'reason': 'Symbol not in alert filter'}

            old_pt = event_data.get('old_price_target')
            new_pt = event_data.get('new_price_target')
            if old_pt is None or new_pt is None:
                return {'should_trigger': False, 'reason': 'Missing price target values'}

            try:
                old_pt_f = float(old_pt)
                new_pt_f = float(new_pt)
            except Exception:
                return {'should_trigger': False, 'reason': 'Invalid price target values'}

            if old_pt_f == new_pt_f:
                return {'should_trigger': False, 'reason': 'Price target did not change'}

            change_pct = ((new_pt_f - old_pt_f) / old_pt_f) * 100 if old_pt_f != 0 else 0.0
            alert_filters = alert.get('event_filters', {})
            min_change_pct = float(alert_filters.get('min_change_percent', 0) or 0)
            if abs(change_pct) < min_change_pct:
                return {'should_trigger': False, 'reason': f'Change {change_pct:.1f}% below threshold {min_change_pct:.1f}%'}

            match_score = min(abs(change_pct) * 5, 100.0)
            urgency = 'high' if abs(change_pct) >= 10 else 'medium'

            return {
                'should_trigger': True,
                'match_score': match_score,
                'urgency_level': urgency,
                'trigger_reason': f"Price target changed for {event_data.get('symbol')} from {old_pt_f} to {new_pt_f}",
                'trigger_details': {
                    'symbol': event_data.get('symbol'),
                    'old_price_target': old_pt_f,
                    'new_price_target': new_pt_f,
                    'change_percent': change_pct,
                    'old_rating': event_data.get('old_rating'),
                    'new_rating': event_data.get('new_rating'),
                    'change_type': event_data.get('change_type'),
                }
            }
        except Exception as e:
            logger.error(f"❌ Error evaluating price target change alert: {e}")
            return {'should_trigger': False, 'reason': f'Evaluation error: {str(e)}'}

    def get_supported_alert_types(self) -> List[str]:
        return self.supported_alert_types

class GradeChangeAlertEvaluator:
    """Evaluator for analyst grade change alerts"""
    
    def __init__(self):
        self.name = "grade_change_evaluator"
        self.supported_alert_types = ["grade_change", "consensus_alert", "price_target_change"]
    
    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate if event triggers grade change alert"""
        try:
            event_type = event.get('event_type')
            event_data = event.get('event_data', {})
            alert_filters = alert.get('event_filters', {})
            
            if event_type != 'grade_change':
                return {'should_trigger': False, 'reason': 'Event type not supported'}
            
            # Check symbol filters
            entity_filters = alert.get('entity_filters', {})
            if 'symbols' in entity_filters:
                if event.get('entity_id') not in entity_filters['symbols']:
                    return {'should_trigger': False, 'reason': 'Symbol not in alert filter'}
            
            # Check change type filters
            change_type = event_data.get('change_type')
            include_upgrades = alert_filters.get('include_upgrades', True)
            include_downgrades = alert_filters.get('include_downgrades', True)
            include_maintains = alert_filters.get('include_maintains', False)
            
            if change_type == 'upgrade' and not include_upgrades:
                return {'should_trigger': False, 'reason': 'Upgrades not included in alert'}
            elif change_type == 'downgrade' and not include_downgrades:
                return {'should_trigger': False, 'reason': 'Downgrades not included in alert'}
            elif change_type == 'maintain' and not include_maintains:
                return {'should_trigger': False, 'reason': 'Maintains not included in alert'}
            
            # Check tier-1 firm filter
            tier_1_firms_only = alert_filters.get('tier_1_firms_only', False)
            if tier_1_firms_only:
                tier_1_firms = {
                    'Goldman Sachs', 'Morgan Stanley', 'J.P. Morgan', 'Bank of America',
                    'Citigroup', 'Credit Suisse', 'Barclays', 'UBS', 'Deutsche Bank'
                }
                firm = event_data.get('grading_company') or event_data.get('analyst_company')
                if firm not in tier_1_firms:
                    return {'should_trigger': False, 'reason': 'Not a tier-1 firm'}
            
            # Calculate match score and urgency
            match_score = self._calculate_match_score(change_type, event_data)
            urgency = self._calculate_urgency(change_type, event_data)

            symbol = event_data.get('symbol') or event.get('entity_id')
            firm = event_data.get('grading_company') or event_data.get('analyst_company')
            action = event_data.get('action') or change_type
            previous_grade = event_data.get('previous_grade') or event_data.get('previous_rating')
            new_grade = event_data.get('new_grade') or event_data.get('rating')
            company = event_data.get('company_name')
            change_date = event_data.get('rating_change_date')

            grade_line = None
            if previous_grade and new_grade and previous_grade != new_grade:
                grade_line = f"{previous_grade} -> {new_grade}"
            elif new_grade:
                grade_line = str(new_grade)

            parts = [p for p in [firm, action] if p]
            who = " ".join([str(p) for p in parts]).strip()
            headline = f"{who} — {symbol}" if who and symbol else (symbol or who or "Grade change")
            if grade_line:
                headline = f"{headline}: {grade_line}"

            return {
                'should_trigger': True,
                'match_score': match_score,
                'urgency_level': urgency,
                'trigger_reason': headline,
                'trigger_details': {
                    # Keys aligned with EmailChannel template_data
                    'event_type': event_type,
                    'symbol': symbol,
                    'company': company,
                    'change_type': str(change_type or ''),
                    'previous_grade': previous_grade,
                    'new_grade': new_grade,
                    'analyst': firm,
                    'source': event_data.get('source') or event.get('data_source'),
                    'trigger_reason': headline,
                    'triggered_at': change_date,

                    # Backward-compat / richer context
                    'company_name': company,
                    'grading_company': firm,
                    'analyst_company': firm,
                    'action': action,
                    'previous_rating': previous_grade,
                    'new_rating': new_grade,
                    'rating_change_date': change_date,
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error evaluating grade change alert: {e}")
            return {'should_trigger': False, 'reason': f'Evaluation error: {str(e)}'}
    
    def _calculate_match_score(self, change_type: str, event_data: Dict) -> float:
        """Calculate match score for grade change"""
        base_score = 70.0
        
        # Bonus for tier-1 firms
        tier_1_firms = {
            'Goldman Sachs', 'Morgan Stanley', 'J.P. Morgan', 'Bank of America',
            'Citigroup', 'Credit Suisse', 'Barclays', 'UBS', 'Deutsche Bank'
        }
        if event_data.get('analyst_company') in tier_1_firms:
            base_score += 20.0
        
        # Bonus for significant changes
        if change_type in ['upgrade', 'downgrade']:
            base_score += 10.0
        
        return min(base_score, 100.0)
    
    def _calculate_urgency(self, change_type: str, event_data: Dict) -> str:
        """Calculate urgency level"""
        if change_type == 'upgrade':
            return 'medium'
        elif change_type == 'downgrade':
            return 'high'
        else:
            return 'low'
    
    def get_supported_alert_types(self) -> List[str]:
        return self.supported_alert_types

class PriceMovementAlertEvaluator:
    """Evaluator for price movement alerts"""
    
    def __init__(self):
        self.name = "price_movement_evaluator"
        self.supported_alert_types = ["price_alert", "volume_alert", "volatility_alert"]
    
    async def evaluate(self, event: Dict[str, Any], alert: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate if event triggers price movement alert"""
        try:
            event_type = event.get('event_type')
            event_data = event.get('event_data', {})
            alert_filters = alert.get('event_filters', {})
            
            if event_type != 'price_change':
                return {'should_trigger': False, 'reason': 'Event type not supported'}
            
            # Check symbol filters
            entity_filters = alert.get('entity_filters', {})
            if 'symbols' in entity_filters:
                if event.get('entity_id') not in entity_filters['symbols']:
                    return {'should_trigger': False, 'reason': 'Symbol not in alert filter'}
            
            # Check price change threshold
            price_change_percent = event_data.get('price_change_percent', 0)
            min_change_percent = alert_filters.get('min_change_percent', 5.0)
            
            if abs(price_change_percent) < min_change_percent:
                return {'should_trigger': False, 'reason': f'Price change {price_change_percent:.1f}% below threshold {min_change_percent}%'}
            
            # Calculate match score and urgency
            match_score = min(abs(price_change_percent) * 5, 100.0)
            urgency = 'critical' if abs(price_change_percent) > 15 else 'high' if abs(price_change_percent) > 10 else 'medium'
            
            direction = 'up' if price_change_percent > 0 else 'down'
            
            return {
                'should_trigger': True,
                'match_score': match_score,
                'urgency_level': urgency,
                'trigger_reason': f"{event_data.get('symbol')} moved {direction} {abs(price_change_percent):.1f}%",
                'trigger_details': {
                    'symbol': event_data.get('symbol'),
                    'current_price': event_data.get('current_price'),
                    'previous_close': event_data.get('previous_close'),
                    'price_change': event_data.get('price_change'),
                    'price_change_percent': price_change_percent,
                    'direction': direction,
                    'volume': event_data.get('volume'),
                    'avg_volume': event_data.get('avg_volume')
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error evaluating price movement alert: {e}")
            return {'should_trigger': False, 'reason': f'Evaluation error: {str(e)}'}
    
    def get_supported_alert_types(self) -> List[str]:
        return self.supported_alert_types

# ============================================================================
# NOTIFICATION PLUGINS - Send notifications via ANY channel
# ============================================================================

class EmailNotificationPlugin:
    """Plugin for sending email notifications"""
    
    def __init__(self):
        self.name = "email_notification"
    
    async def send_notification(self, notification_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send email notification"""
        try:
            recipient = notification_data.get('recipient')
            subject = notification_data.get('subject')
            body = notification_data.get('body')
            html_body = notification_data.get('html_body')
            
            # This would integrate with your existing email service
            # For now, log the notification
            logger.info(f"📧 Email notification sent to {recipient}: {subject}")
            
            metrics.increment('email_notifications_sent_total')
            
            return {
                'success': True,
                'channel': 'email',
                'recipient': recipient,
                'sent_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error sending email notification: {e}")
            metrics.increment('email_notifications_failed_total')
            return {
                'success': False,
                'channel': 'email',
                'error': str(e)
            }

# ============================================================================
# PLUGIN REGISTRY - Dynamic plugin management
# ============================================================================

class PluginRegistry:
    """Registry for managing universal alert plugins"""
    
    def __init__(self):
        self.data_source_plugins = {}
        self.evaluator_plugins = {}
        self.notification_plugins = {}
        
        # Register built-in plugins
        self._register_builtin_plugins()
    
    def _register_builtin_plugins(self):
        """Register built-in plugins"""
        # Data source plugins
        self.register_data_source_plugin('earnings_calendar', EarningsCalendarPlugin())
        self.register_data_source_plugin('analyst_grades', AnalystGradesPlugin())
        self.register_data_source_plugin('price_movements', PriceMovementsPlugin())
        
        # Evaluator plugins
        self.register_evaluator_plugin('earnings', EarningsAlertEvaluator())
        self.register_evaluator_plugin('grade_change', GradeChangeAlertEvaluator())
        self.register_evaluator_plugin('consensus_update', ConsensusUpdateAlertEvaluator())
        self.register_evaluator_plugin('price_target_change', PriceTargetChangeAlertEvaluator())
        self.register_evaluator_plugin('price_movement', PriceMovementAlertEvaluator())
        self.register_evaluator_plugin('signal_generated', SignalGeneratedAlertEvaluator())
        
        # Notification plugins
        self.register_notification_plugin('email', EmailNotificationPlugin())
    
    def register_data_source_plugin(self, name: str, plugin):
        """Register a data source plugin"""
        self.data_source_plugins[name] = plugin
        logger.info(f"✅ Registered data source plugin: {name}")
    
    def register_evaluator_plugin(self, name: str, plugin):
        """Register an evaluator plugin"""
        self.evaluator_plugins[name] = plugin
        logger.info(f"✅ Registered evaluator plugin: {name}")
    
    def register_notification_plugin(self, name: str, plugin):
        """Register a notification plugin"""
        self.notification_plugins[name] = plugin
        logger.info(f"✅ Registered notification plugin: {name}")
    
    def get_data_source_plugin(self, name: str):
        """Get data source plugin by name"""
        return self.data_source_plugins.get(name)
    
    def get_evaluator_plugin(self, name: str):
        """Get evaluator plugin by name"""
        return self.evaluator_plugins.get(name)
    
    def get_notification_plugin(self, name: str):
        """Get notification plugin by name"""
        return self.notification_plugins.get(name)
    
    def list_plugins(self) -> Dict[str, List[str]]:
        """List all registered plugins"""
        return {
            'data_sources': list(self.data_source_plugins.keys()),
            'evaluators': list(self.evaluator_plugins.keys()),
            'notifications': list(self.notification_plugins.keys())
        }

# Global plugin registry
plugin_registry = PluginRegistry()
