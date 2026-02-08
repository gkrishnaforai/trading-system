"""
Base Data Source Interface
Follows SOLID: Dependency Inversion Principle
Abstracts data source implementations from business logic
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum


class DataSourceType(Enum):
    """Supported data source types"""
    FMP = "fmp"
    BLOOMBERG = "bloomberg"
    REUTERS = "reuters"
    FACTSET = "factset"


@dataclass
class StockGrade:
    """Standardized stock grade data structure"""
    symbol: str
    grade_date: date
    grading_company: str
    previous_grade: Optional[str]
    new_grade: str
    action: str  # upgrade, downgrade, maintain, initiate, suspend
    price_at_grade: Optional[float] = None
    volume_at_grade: Optional[int] = None
    market_cap_at_grade: Optional[int] = None
    data_source: str = "unknown"
    source_id: Optional[str] = None


@dataclass
class ConsensusData:
    """Standardized consensus data structure"""
    symbol: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    consensus_rating: str
    consensus_score: float
    total_analysts: int
    data_source: str = "unknown"
    fetched_at: Optional[datetime] = None


class BaseDataSource(ABC):
    """Abstract base class for data sources
    
    Implements Dependency Inversion Principle - business logic depends on abstractions,
    not concrete implementations. Allows easy addition of new data sources.
    """
    
    def __init__(self, name: DataSourceType):
        self.name = name
        self._grade_mappings = {}
        self._action_mappings = {}
        self._company_mappings = {}
    
    @abstractmethod
    async def get_stock_grades(self, symbol: str) -> List[Dict[str, Any]]:
        """Get stock grades from data source"""
        pass
    
    @abstractmethod
    async def get_consensus_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get consensus data from data source"""
        pass
    
    @abstractmethod
    async def validate_symbol(self, symbol: str) -> bool:
        """Validate if symbol exists in data source"""
        pass
    
    def normalize_grade(self, grade: str) -> str:
        """Normalize grade to internal standard
        
        Template Method Pattern - provides default implementation
        that can be overridden by subclasses
        """
        return self._grade_mappings.get(grade, grade)
    
    def normalize_action(self, action: str) -> str:
        """Normalize action to internal standard"""
        return self._action_mappings.get(action, action)
    
    def normalize_company(self, company: str) -> str:
        """Normalize company name to internal standard"""
        return self._company_mappings.get(company, company)
    
    def to_stock_grade(self, external_data: Dict[str, Any]) -> StockGrade:
        """Convert external data to standardized StockGrade
        
        Factory Method Pattern - creates standardized objects
        from external data source format
        """
        return StockGrade(
            symbol=external_data['symbol'],
            grade_date=self._parse_date(external_data['date']),
            grading_company=self.normalize_company(external_data['gradingCompany']),
            previous_grade=self.normalize_grade(external_data.get('previousGrade')),
            new_grade=self.normalize_grade(external_data['newGrade']),
            action=self.normalize_action(external_data['action']),
            price_at_grade=external_data.get('price'),
            volume_at_grade=external_data.get('volume'),
            market_cap_at_grade=external_data.get('marketCap'),
            data_source=self.name.value,
            source_id=external_data.get('id')
        )
    
    def to_consensus_data(self, external_data: Dict[str, Any]) -> ConsensusData:
        """Convert external data to standardized ConsensusData"""
        total_analysts = sum([
            external_data.get('strongBuy', 0),
            external_data.get('buy', 0),
            external_data.get('hold', 0),
            external_data.get('sell', 0),
            external_data.get('strongSell', 0)
        ])
        
        consensus_score = (
            (external_data.get('strongBuy', 0) * 2) +
            (external_data.get('buy', 0) * 1) +
            (external_data.get('hold', 0) * 0) +
            (external_data.get('sell', 0) * -1) +
            (external_data.get('strongSell', 0) * -2)
        ) / total_analysts if total_analysts > 0 else 0
        
        return ConsensusData(
            symbol=external_data['symbol'],
            strong_buy=external_data.get('strongBuy', 0),
            buy=external_data.get('buy', 0),
            hold=external_data.get('hold', 0),
            sell=external_data.get('sell', 0),
            strong_sell=external_data.get('strongSell', 0),
            consensus_rating=external_data.get('consensus'),
            consensus_score=round(consensus_score, 2),
            total_analysts=total_analysts,
            data_source=self.name.value,
            fetched_at=datetime.utcnow()
        )
    
    def _parse_date(self, date_str: str) -> date:
        """Parse date string - can be overridden for different formats"""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            # Try alternative formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"Unable to parse date: {date_str}")
    
    def add_mapping(self, mapping_type: str, external: str, internal: str):
        """Add mapping for normalization"""
        if mapping_type == 'grade':
            self._grade_mappings[external] = internal
        elif mapping_type == 'action':
            self._action_mappings[external] = internal
        elif mapping_type == 'company':
            self._company_mappings[external] = internal
    
    def get_mappings(self) -> Dict[str, Dict[str, str]]:
        """Get all mappings for storage/retrieval"""
        return {
            'grade': self._grade_mappings,
            'action': self._action_mappings,
            'company': self._company_mappings
        }


class DataSourceError(Exception):
    """Custom exception for data source errors"""
    pass


class DataSourceUnavailableError(DataSourceError):
    """Raised when data source is not available"""
    pass


class DataSourceRateLimitError(DataSourceError):
    """Raised when data source rate limit is exceeded"""
    pass
