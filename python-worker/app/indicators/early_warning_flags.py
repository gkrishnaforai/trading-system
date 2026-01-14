"""
Early Warning Flags Engine for Growth Quality Analysis

This module implements a comprehensive system to detect structural deterioration 
in growth quality using fundamental data analysis across four key domains:

1. Revenue Quality Deterioration
2. Margin & Cost Structure Stress  
3. Capital Efficiency & Return Decay
4. Management Signals & Behavioral Shifts

The system uses quarterly financial data to identify early warning signs that may
precede significant growth slowdowns or quality deterioration.
"""

import logging
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Any, Tuple, List, Optional
from enum import Enum
from sqlalchemy import text
from datetime import date

from app.database import db

# Configure logging
logger = logging.getLogger(__name__)


class RiskState(Enum):
    """Overall growth risk classification"""
    GREEN = "GREEN"      # No significant concerns
    YELLOW = "YELLOW"    # Early warning signs detected
    RED = "RED"          # Structural breakdown detected


class DomainRisk(Enum):
    """Domain-specific risk classification"""
    NO_RISK = "NO_RISK"
    EARLY_STRESS = "EARLY_STRESS"
    STRUCTURAL_BREAKDOWN = "STRUCTURAL_BREAKDOWN"


@dataclass
class RevenueQualityFlags:
    """Domain 1: Revenue Quality Deterioration Flags"""
    receivables_vs_revenue_divergence: bool = False
    margin_stress: bool = False
    revenue_vs_volume_divergence: bool = False
    
    def calculate_risk(self) -> DomainRisk:
        """Calculate revenue quality risk level"""
        active_flags = sum([
            self.receivables_vs_revenue_divergence,
            self.margin_stress,
            self.revenue_vs_volume_divergence
        ])
        
        if active_flags >= 2:
            return DomainRisk.STRUCTURAL_BREAKDOWN
        elif active_flags >= 1:
            return DomainRisk.EARLY_STRESS
        else:
            return DomainRisk.NO_RISK


@dataclass
class MarginStressFlags:
    """Domain 2: Margin & Cost Structure Stress Flags"""
    operating_margin_compression: bool = False
    rd_efficiency_decline: bool = False
    
    def calculate_risk(self) -> DomainRisk:
        """Calculate margin stress risk level"""
        active_flags = sum([
            self.operating_margin_compression,
            self.rd_efficiency_decline
        ])
        
        if active_flags >= 2:
            return DomainRisk.STRUCTURAL_BREAKDOWN
        elif active_flags >= 1:
            return DomainRisk.EARLY_STRESS
        else:
            return DomainRisk.NO_RISK


@dataclass
class CapitalEfficiencyFlags:
    """Domain 3: Capital Efficiency & Return Decay Flags"""
    roic_trend_decay: bool = False
    growth_vs_capital_mismatch: bool = False
    incremental_roic_collapse: bool = False
    
    def calculate_risk(self) -> DomainRisk:
        """Calculate capital efficiency risk level"""
        active_flags = sum([
            self.roic_trend_decay,
            self.growth_vs_capital_mismatch,
            self.incremental_roic_collapse
        ])
        
        if active_flags >= 2:
            return DomainRisk.STRUCTURAL_BREAKDOWN
        elif active_flags >= 1:
            return DomainRisk.EARLY_STRESS
        else:
            return DomainRisk.NO_RISK


@dataclass
class ManagementSignalsFlags:
    """Domain 4: Management Signals & Behavioral Shifts Flags"""
    guidance_language_shift: bool = False
    kpi_redefinition_removal: bool = False
    buybacks_rising_debt: bool = False
    
    def calculate_risk(self) -> DomainRisk:
        """Calculate management signals risk level"""
        active_flags = sum([
            self.guidance_language_shift,
            self.kpi_redefinition_removal,
            self.buybacks_rising_debt
        ])
        
        if active_flags >= 2:
            return DomainRisk.STRUCTURAL_BREAKDOWN
        elif active_flags >= 1:
            return DomainRisk.EARLY_STRESS
        else:
            return DomainRisk.NO_RISK


@dataclass
class EarlyWarningResult:
    """Complete early warning analysis result"""
    symbol: str
    analysis_date: date
    overall_risk: RiskState
    revenue_quality: RevenueQualityFlags
    margin_stress: MarginStressFlags
    capital_efficiency: CapitalEfficiencyFlags
    management_signals: ManagementSignalsFlags
    domain_risks: Dict[str, DomainRisk]
    metrics: Dict[str, Any]
    warnings: List[str]
    insights: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'symbol': self.symbol,
            'analysis_date': self.analysis_date.isoformat(),
            'overall_risk': self.overall_risk.value,
            'domain_risks': {
                'revenue_quality': self.domain_risks.get('revenue_quality', DomainRisk.NO_RISK).value,
                'margin_stress': self.domain_risks.get('margin_stress', DomainRisk.NO_RISK).value,
                'capital_efficiency': self.domain_risks.get('capital_efficiency', DomainRisk.NO_RISK).value,
                'management_signals': self.domain_risks.get('management_signals', DomainRisk.NO_RISK).value
            },
            'metrics': self.metrics,
            'warnings': self.warnings,
            'insights': self.insights,
            'revenue_quality': {
                'receivables_vs_revenue_divergence': self.revenue_quality.receivables_vs_revenue_divergence,
                'margin_stress': self.revenue_quality.margin_stress,
                'revenue_vs_volume_divergence': self.revenue_quality.revenue_vs_volume_divergence
            },
            'margin_stress': {
                'operating_margin_compression': self.margin_stress.operating_margin_compression,
                'rd_efficiency_decline': self.margin_stress.rd_efficiency_decline
            },
            'capital_efficiency': {
                'roic_trend_decay': self.capital_efficiency.roic_trend_decay,
                'growth_vs_capital_mismatch': self.capital_efficiency.growth_vs_capital_mismatch,
                'incremental_roic_collapse': self.capital_efficiency.incremental_roic_collapse
            },
            'management_signals': {
                'guidance_language_shift': self.management_signals.guidance_language_shift,
                'kpi_redefinition_removal': self.management_signals.kpi_redefinition_removal,
                'buybacks_rising_debt': self.management_signals.buybacks_rising_debt
            }
        }


class EarlyWarningEngine:
    """
    Early Warning Flags Engine for detecting growth quality deterioration
    
    This engine analyzes quarterly fundamental data across four domains to identify
    early warning signs of growth quality issues before they become apparent in
    stock price movements.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_growth_health(self, symbol: str) -> EarlyWarningResult:
        """
        Perform comprehensive growth health analysis
        
        Args:
            symbol: Stock symbol to analyze
            
        Returns:
            EarlyWarningResult with complete analysis
        """
        try:
            self.logger.info(f"🔍 Starting early warning analysis for {symbol}")
            
            # Get fundamentals data
            data = self._get_fundamentals_data(symbol)
            
            if not data:
                self.logger.warning(f"⚠️ No fundamentals data available for {symbol}")
                return self._create_empty_result(symbol)
            
            # Analyze each domain
            revenue_flags, revenue_metrics = self._analyze_revenue_quality(symbol, data)
            margin_flags, margin_metrics = self._analyze_margin_stress(symbol, data)
            capital_flags, capital_metrics = self._analyze_capital_efficiency(symbol, data)
            mgmt_flags, mgmt_metrics = self._analyze_management_signals(symbol, data)
            
            # Calculate domain risks
            domain_risks = {
                'revenue_quality': revenue_flags.calculate_risk(),
                'margin_stress': margin_flags.calculate_risk(),
                'capital_efficiency': capital_flags.calculate_risk(),
                'management_signals': mgmt_flags.calculate_risk()
            }
            
            # Determine overall risk
            overall_risk = self._calculate_overall_risk(domain_risks)
            
            # Generate warnings and insights
            warnings, insights = self._generate_warnings_insights(
                symbol, domain_risks, revenue_flags, margin_flags, capital_flags, mgmt_flags
            )
            
            # Combine all metrics
            all_metrics = {
                **revenue_metrics,
                **margin_metrics,
                **capital_metrics,
                **mgmt_metrics
            }
            
            result = EarlyWarningResult(
                symbol=symbol,
                analysis_date=date.today(),
                overall_risk=overall_risk,
                revenue_quality=revenue_flags,
                margin_stress=margin_flags,
                capital_efficiency=capital_flags,
                management_signals=mgmt_flags,
                domain_risks=domain_risks,
                metrics=all_metrics,
                warnings=warnings,
                insights=insights
            )
            
            self.logger.info(f"🚨 Early warning analysis complete for {symbol}: {overall_risk.value}")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing growth health for {symbol}: {str(e)}")
            self.logger.error(f"❌ Exception type: {type(e).__name__}")
            import traceback
            self.logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            
            # Return a more informative error
            if "KeyError" in str(type(e)):
                raise ValueError(f"Missing data key in analysis: {str(e)}")
            elif "NoResultFound" in str(e) or "does not exist" in str(e).lower():
                raise ValueError(f"Fundamentals data not found for {symbol}")
            else:
                raise ValueError(f"Analysis failed: {str(e)}")
    
    def _get_fundamentals_data(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive fundamentals data from new table structure"""
        try:
            with db.get_session() as session:
                # Fetch income statement data
                income_query = """
                SELECT fiscal_date_ending, total_revenue, gross_profit, operating_income, 
                       net_income, research_and_development, interest_expense
                FROM income_statements 
                WHERE symbol = :symbol 
                ORDER BY fiscal_date_ending DESC 
                LIMIT 8
                """
                income_result = session.execute(text(income_query), {"symbol": symbol}).fetchall()
                
                # Get balance sheets data
                balance_query = """
                SELECT fiscal_date_ending, total_assets, total_liabilities, net_receivables,
                       cash_and_cash_equivalents, long_term_debt
                FROM balance_sheets 
                WHERE symbol = :symbol 
                ORDER BY fiscal_date_ending DESC 
                LIMIT 8
                """
                balance_result = session.execute(text(balance_query), {"symbol": symbol}).fetchall()
                
                # Get cash flow statements data
                cashflow_query = """
                SELECT fiscal_date_ending, operating_cash_flow, investing_cash_flow,
                       financing_cash_flow, free_cash_flow, capital_expenditures
                FROM cash_flow_statements 
                WHERE symbol = :symbol 
                ORDER BY fiscal_date_ending DESC 
                LIMIT 8
                """
                cashflow_result = session.execute(text(cashflow_query), {"symbol": symbol}).fetchall()
                
                # Get financial ratios data
                ratios_query = """
                SELECT fiscal_date_ending, roe, debt_to_equity, current_ratio,
                       receivables_turnover, days_sales_outstanding, roic
                FROM financial_ratios 
                WHERE symbol = :symbol 
                ORDER BY fiscal_date_ending DESC 
                LIMIT 8
                """
                ratios_result = session.execute(text(ratios_query), {"symbol": symbol}).fetchall()
                
                if not income_result or not balance_result:
                    return {}
                
                # Convert SQLAlchemy Row objects to dictionaries
                income_data = []
                for row in income_result:
                    income_data.append({key: value for key, value in row._mapping.items()})
                
                balance_data = []
                for row in balance_result:
                    balance_data.append({key: value for key, value in row._mapping.items()})
                
                cashflow_data = []
                for row in cashflow_result:
                    cashflow_data.append({key: value for key, value in row._mapping.items()})
                
                ratios_data = []
                for row in ratios_result:
                    ratios_data.append({key: value for key, value in row._mapping.items()})
                
                return {
                    'income_statements': income_data,
                    'balance_sheets': balance_data,
                    'cash_flow_statements': cashflow_data,
                    'financial_ratios': ratios_data
                }
                
        except Exception as e:
            self.logger.error(f"❌ Error fetching fundamentals data for {symbol}: {str(e)}")
            return {}
    
    def _analyze_revenue_quality(self, symbol: str, data: Dict[str, Any]) -> Tuple[RevenueQualityFlags, Dict[str, Any]]:
        """
        Domain 1: Revenue Quality Deterioration Analysis
        
        Detects:
        - Revenue vs Receivables Divergence
        - Revenue Growth vs Volume Growth  
        - Geographic/Segment Growth Concentration
        """
        flags = RevenueQualityFlags()
        metrics = {}
        
        income_data = data.get('income_statements', [])
        balance_data = data.get('balance_sheets', [])
        
        if len(income_data) < 2 or len(balance_data) < 2:
            return flags, metrics
        
        # Convert to DataFrames for easier analysis
        income_df = pd.DataFrame(income_data)
        balance_df = pd.DataFrame(balance_data)
        
        # Sort by date (oldest first for trend calculation)
        income_df['fiscal_date_ending'] = pd.to_datetime(income_df['fiscal_date_ending'])
        balance_df['fiscal_date_ending'] = pd.to_datetime(balance_df['fiscal_date_ending'])
        income_df = income_df.sort_values('fiscal_date_ending')
        balance_df = balance_df.sort_values('fiscal_date_ending')
        
        # Flag 1: Revenue vs Receivables Divergence
        if 'total_revenue' in income_df.columns and 'net_receivables' in balance_df.columns:
            # Calculate growth rates
            revenue_growth = income_df['total_revenue'].pct_change().iloc[-2:]  # Last 2 periods
            receivables_growth = balance_df['net_receivables'].pct_change().iloc[-2:]
            
            # Check if receivables growing faster than revenue for 2+ periods
            if len(receivables_growth) >= 2 and len(revenue_growth) >= 2:
                divergence_periods = sum(1 for i in range(len(receivables_growth)) 
                                       if receivables_growth.iloc[i] > revenue_growth.iloc[i])
                if divergence_periods >= 2:
                    flags.receivables_vs_revenue_divergence = True
                    metrics['receivables_vs_revenue_growth'] = 'divergence_detected'
                else:
                    metrics['receivables_vs_revenue_growth'] = 'normal'
            else:
                metrics['receivables_vs_revenue_growth'] = 'insufficient_data'
        
        # Flag 2: Revenue Growth Quality (using operating margin trends)
        if 'operating_income' in income_df.columns and 'total_revenue' in income_df.columns:
            income_df['operating_margin'] = income_df['operating_income'] / income_df['total_revenue']
            margin_trend = income_df['operating_margin'].iloc[-2:].pct_change()
            
            # Check if margins are declining while revenue grows
            revenue_growth = income_df['total_revenue'].pct_change().iloc[-2:]
            margin_decline = sum(1 for i in range(len(margin_trend)) if margin_trend.iloc[i] < 0)
            revenue_growth_positive = sum(1 for i in range(len(revenue_growth)) if revenue_growth.iloc[i] > 0)
            
            if margin_decline >= 1 and revenue_growth_positive >= 1:
                flags.margin_stress = True
                metrics['margin_trend'] = 'declining_with_growth'
            else:
                metrics['margin_trend'] = 'stable'
        
        return flags, metrics
    
    def _analyze_margin_stress(self, symbol: str, data: Dict[str, Any]) -> Tuple[MarginStressFlags, Dict[str, Any]]:
        """
        Domain 2: Margin & Cost Structure Stress Analysis
        
        Detects:
        - Operating Margin Compression
        - SG&A vs Revenue Growth Divergence
        - R&D Efficiency Decline
        """
        flags = MarginStressFlags()
        metrics = {}
        
        income_data = data.get('income_statements', [])
        ratios_data = data.get('financial_ratios', [])
        
        if len(income_data) < 2:
            return flags, metrics
        
        # Convert to DataFrames
        income_df = pd.DataFrame(income_data)
        income_df['fiscal_date_ending'] = pd.to_datetime(income_df['fiscal_date_ending'])
        income_df = income_df.sort_values('fiscal_date_ending')
        
        # Flag 1: Operating Margin Compression
        if 'operating_income' in income_df.columns and 'total_revenue' in income_df.columns:
            income_df['operating_margin'] = income_df['operating_income'] / income_df['total_revenue']
            margins = income_df['operating_margin'].dropna()
            
            if len(margins) >= 2:
                margin_trend = margins.iloc[-1] - margins.iloc[0]  # Change over period
                if margin_trend < -0.02:  # More than 2% decline
                    flags.operating_margin_compression = True
                    metrics['margin_trend'] = 'compressing'
                else:
                    metrics['margin_trend'] = 'stable'
        
        # Flag 2: R&D Efficiency (using ratios data if available)
        if ratios_data:
            ratios_df = pd.DataFrame(ratios_data)
            if 'roe' in ratios_df.columns:
                roe_trend = ratios_df['roe'].iloc[-2:].pct_change().dropna()
                if len(roe_trend) > 0 and roe_trend.iloc[-1] < -0.1:  # 10% ROE decline
                    flags.rd_efficiency_decline = True
                    metrics['roe_trend'] = 'declining'
                else:
                    metrics['roe_trend'] = 'stable'
        
        return flags, metrics
    
    def _analyze_capital_efficiency(self, symbol: str, data: Dict[str, Any]) -> Tuple[CapitalEfficiencyFlags, Dict[str, Any]]:
        """
        Domain 3: Capital Efficiency & Return Decay Analysis
        
        Detects:
        - ROIC Trend Decay
        - Growth vs Capital Mismatch
        - Incremental ROIC Collapse
        """
        flags = CapitalEfficiencyFlags()
        metrics = {}
        
        ratios_data = data.get('financial_ratios', [])
        income_data = data.get('income_statements', [])
        balance_data = data.get('balance_sheets', [])
        
        if not ratios_data or len(ratios_data) < 2:
            return flags, metrics
        
        # Convert to DataFrames
        ratios_df = pd.DataFrame(ratios_data)
        ratios_df['fiscal_date_ending'] = pd.to_datetime(ratios_df['fiscal_date_ending'])
        ratios_df = ratios_df.sort_values('fiscal_date_ending')
        
        # Flag 1: ROIC Trend Decay
        if 'roic' in ratios_df.columns:
            roic_values = ratios_df['roic'].dropna()
            if len(roic_values) >= 2:
                roic_trend = roic_values.iloc[-1] - roic_values.iloc[0]
                if roic_trend < -0.03:  # More than 3% ROIC decline
                    flags.roic_trend_decay = True
                    metrics['roic_trend'] = 'declining'
                else:
                    metrics['roic_trend'] = 'stable'
        
        # Flag 2: Growth vs Capital Mismatch
        if income_data and balance_data:
            income_df = pd.DataFrame(income_data)
            balance_df = pd.DataFrame(balance_data)
            
            if 'total_revenue' in income_df.columns and 'total_assets' in balance_df.columns:
                # Calculate revenue growth vs asset growth
                revenue_growth = income_df['total_revenue'].pct_change().iloc[-1]
                asset_growth = balance_df['total_assets'].pct_change().iloc[-1]
                
                if revenue_growth < asset_growth * 0.8:  # Revenue growing much slower than assets
                    flags.growth_vs_capital_mismatch = True
                    metrics['growth_vs_capital'] = 'inefficient'
                else:
                    metrics['growth_vs_capital'] = 'efficient'
        
        return flags, metrics
    
    def _analyze_management_signals(self, symbol: str, data: Dict[str, Any]) -> Tuple[ManagementSignalsFlags, Dict[str, Any]]:
        """
        Domain 4: Management Signals & Behavioral Shifts Analysis
        
        Note: This domain requires qualitative data that may not be available
        in standard financial statements. For now, we use proxy indicators.
        """
        flags = ManagementSignalsFlags()
        metrics = {}
        
        # For now, use debt levels as a proxy for management behavior
        balance_data = data.get('balance_sheets', [])
        ratios_data = data.get('financial_ratios', [])
        
        if ratios_data:
            ratios_df = pd.DataFrame(ratios_data)
            if 'debt_to_equity' in ratios_df.columns:
                debt_ratio = ratios_df['debt_to_equity'].iloc[-1]
                if debt_ratio > 1.0:  # High debt might indicate aggressive management
                    flags.buybacks_rising_debt = True
                    metrics['debt_level'] = 'high'
                else:
                    metrics['debt_level'] = 'moderate'
        
        return flags, metrics
    
    def _calculate_overall_risk(self, domain_risks: Dict[str, DomainRisk]) -> RiskState:
        """Calculate overall growth risk from domain risks"""
        risk_scores = {
            DomainRisk.NO_RISK: 0,
            DomainRisk.EARLY_STRESS: 1,
            DomainRisk.STRUCTURAL_BREAKDOWN: 2
        }
        
        total_score = sum(risk_scores[risk] for risk in domain_risks.values())
        
        if total_score >= 6:  # 2+ domains with structural breakdown
            return RiskState.RED
        elif total_score >= 3:  # 3+ domains with early stress or 1+ with breakdown
            return RiskState.YELLOW
        else:
            return RiskState.GREEN
    
    def _generate_warnings_insights(self, symbol: str, domain_risks: Dict[str, DomainRisk],
                                  revenue_flags: RevenueQualityFlags, margin_flags: MarginStressFlags,
                                  capital_flags: CapitalEfficiencyFlags, mgmt_flags: ManagementSignalsFlags) -> Tuple[List[str], List[str]]:
        """Generate warnings and insights based on analysis"""
        warnings = []
        insights = []
        
        # Revenue Quality warnings
        if revenue_flags.receivables_vs_revenue_divergence:
            warnings.append("🔴 Receivables growing faster than revenue - potential revenue quality issues")
        
        if revenue_flags.margin_stress:
            warnings.append("🔴 Margins declining while revenue grows - pricing pressure or cost inflation")
        
        # Margin Stress warnings
        if margin_flags.operating_margin_compression:
            warnings.append("🔴 Operating margin compression detected")
        
        if margin_flags.rd_efficiency_decline:
            warnings.append("🔴 R&D efficiency declining - innovation pipeline concerns")
        
        # Capital Efficiency warnings
        if capital_flags.roic_trend_decay:
            warnings.append("🔴 ROIC trend decay - capital allocation concerns")
        
        if capital_flags.growth_vs_capital_mismatch:
            warnings.append("🔴 Growth vs capital mismatch - inefficient expansion")
        
        # Management Signals warnings
        if mgmt_flags.buybacks_rising_debt:
            warnings.append("🔴 High debt levels - potential aggressive financial management")
        
        # Generate insights
        high_risk_domains = [domain for domain, risk in domain_risks.items() 
                           if risk == DomainRisk.STRUCTURAL_BREAKDOWN]
        
        if high_risk_domains:
            insights.append(f"⚠️ Structural breakdown detected in: {', '.join(high_risk_domains)}")
        
        if domain_risks['revenue_quality'] == DomainRisk.NO_RISK:
            insights.append("✅ Revenue quality appears healthy")
        
        if domain_risks['margin_stress'] == DomainRisk.NO_RISK:
            insights.append("✅ Margin structure appears stable")
        
        return warnings, insights
    
    def _create_empty_result(self, symbol: str) -> EarlyWarningResult:
        """Create empty result when no data is available"""
        return EarlyWarningResult(
            symbol=symbol,
            analysis_date=date.today(),
            overall_risk=RiskState.GREEN,
            revenue_quality=RevenueQualityFlags(),
            margin_stress=MarginStressFlags(),
            capital_efficiency=CapitalEfficiencyFlags(),
            management_signals=ManagementSignalsFlags(),
            domain_risks={},
            metrics={},
            warnings=["⚠️ Insufficient data for comprehensive analysis"],
            insights=[]
        )
