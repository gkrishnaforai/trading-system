"""
Email Alert Plugin
Sends alerts via email
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from app.alerts.base import (
    BaseAlertPlugin, AlertMetadata, AlertContext, AlertResult,
    AlertSeverity, NotificationChannel
)
from app.exceptions import AlertNotificationError, ValidationError
from app.config import settings

logger = logging.getLogger(__name__)


class EmailAlertPlugin(BaseAlertPlugin):
    """
    Email alert plugin
    Supports multiple alert types: price_threshold, signal_change, etc.
    """
    
    def get_metadata(self) -> AlertMetadata:
        return AlertMetadata(
            alert_type_id="email_alert",
            name="Email Alert",
            display_name="Email Notification",
            description="Sends alerts via email",
            version="1.0.0",
            config_schema={
                "type": "object",
                "properties": {
                    "smtp_host": {"type": "string"},
                    "smtp_port": {"type": "integer", "default": 587},
                    "smtp_user": {"type": "string"},
                    "smtp_password": {"type": "string"},
                    "from_email": {"type": "string"},
                },
                "required": ["smtp_host", "smtp_user", "smtp_password", "from_email"]
            },
            supported_channels=[NotificationChannel.EMAIL],
            subscription_level_required="basic"
        )
    
    def evaluate(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """
        Evaluate alert condition based on alert type
        
        This is a generic evaluator - specific alert types
        (price_threshold, signal_change, etc.) have their own logic
        """
        alert_type = config.get("alert_type", "generic")
        
        if alert_type == "price_threshold":
            return self._evaluate_price_threshold(context, config)
        elif alert_type == "signal_change":
            return self._evaluate_signal_change(context, config)
        elif alert_type == "volume_spike":
            return self._evaluate_volume_spike(context, config)
        elif alert_type == "rsi_extreme":
            return self._evaluate_rsi_extreme(context, config)
        elif alert_type == "macd_crossover":
            return self._evaluate_macd_crossover(context, config)
        elif alert_type == "portfolio_risk":
            return self._evaluate_portfolio_risk(context, config)
        else:
            # Generic alert - always triggers (for testing)
            return AlertResult(
                triggered=True,
                message=f"Generic alert for {context.stock_symbol or 'portfolio'}",
                severity=AlertSeverity.INFO
            )
    
    def _evaluate_price_threshold(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """Evaluate price threshold alert"""
        if context.current_price is None:
            return AlertResult(
                triggered=False,
                message="No price data available",
                severity=AlertSeverity.INFO
            )
        
        threshold = config.get("threshold")
        direction = config.get("direction", "above")
        
        if threshold is None:
            raise ValidationError("Price threshold alert requires 'threshold' in config")
        
        triggered = False
        if direction == "above" and context.current_price >= threshold:
            triggered = True
        elif direction == "below" and context.current_price <= threshold:
            triggered = True
        
        if triggered:
            return AlertResult(
                triggered=True,
                message=f"Price {direction} threshold: ${context.current_price:.2f} {'>=' if direction == 'above' else '<='} ${threshold:.2f}",
                severity=AlertSeverity.WARNING,
                metadata={"price": context.current_price, "threshold": threshold}
            )
        
        return AlertResult(
            triggered=False,
            message="Price threshold not reached",
            severity=AlertSeverity.INFO
        )
    
    def _evaluate_signal_change(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """Evaluate signal change alert"""
        if context.signal is None:
            return AlertResult(
                triggered=False,
                message="No signal data available",
                severity=AlertSeverity.INFO
            )
        
        from_signal = config.get("from_signal")
        to_signal = config.get("to_signal")
        
        # Check if signal changed to target signal
        if to_signal and context.signal == to_signal:
            if from_signal is None or context.metadata.get("previous_signal") == from_signal:
                return AlertResult(
                    triggered=True,
                    message=f"Signal changed to {to_signal}",
                    severity=AlertSeverity.WARNING,
                    metadata={"signal": context.signal}
                )
        
        return AlertResult(
            triggered=False,
            message="Signal change condition not met",
            severity=AlertSeverity.INFO
        )
    
    def _evaluate_volume_spike(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """Evaluate volume spike alert"""
        if context.volume is None or context.metadata is None:
            return AlertResult(
                triggered=False,
                message="No volume data available",
                severity=AlertSeverity.INFO
            )
        
        multiplier = config.get("multiplier", 2.0)
        avg_volume = context.metadata.get("avg_volume")
        
        if avg_volume is None:
            return AlertResult(
                triggered=False,
                message="No average volume data available",
                severity=AlertSeverity.INFO
            )
        
        if context.volume >= (avg_volume * multiplier):
            return AlertResult(
                triggered=True,
                message=f"Volume spike detected: {context.volume:,} ({context.volume/avg_volume:.1f}x average)",
                severity=AlertSeverity.WARNING,
                metadata={"volume": context.volume, "avg_volume": avg_volume}
            )
        
        return AlertResult(
            triggered=False,
            message="Volume spike condition not met",
            severity=AlertSeverity.INFO
        )
    
    def _evaluate_rsi_extreme(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """Evaluate RSI extreme alert"""
        if context.indicators is None:
            return AlertResult(
                triggered=False,
                message="No indicator data available",
                severity=AlertSeverity.INFO
            )
        
        rsi = context.indicators.get("rsi")
        if rsi is None:
            return AlertResult(
                triggered=False,
                message="No RSI data available",
                severity=AlertSeverity.INFO
            )
        
        level = config.get("level", 70)
        direction = config.get("direction", "overbought")
        
        triggered = False
        if direction == "overbought" and rsi >= level:
            triggered = True
        elif direction == "oversold" and rsi <= (100 - level):
            triggered = True
        
        if triggered:
            return AlertResult(
                triggered=True,
                message=f"RSI {direction}: {rsi:.1f}",
                severity=AlertSeverity.WARNING,
                metadata={"rsi": rsi, "level": level}
            )
        
        return AlertResult(
            triggered=False,
            message="RSI extreme condition not met",
            severity=AlertSeverity.INFO
        )
    
    def _evaluate_macd_crossover(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """Evaluate MACD crossover alert"""
        if context.indicators is None:
            return AlertResult(
                triggered=False,
                message="No indicator data available",
                severity=AlertSeverity.INFO
            )
        
        macd_line = context.indicators.get("macd")
        macd_signal = context.indicators.get("macd_signal")
        
        if macd_line is None or macd_signal is None:
            return AlertResult(
                triggered=False,
                message="No MACD data available",
                severity=AlertSeverity.INFO
            )
        
        direction = config.get("direction", "bullish")
        previous_macd = context.metadata.get("previous_macd")
        previous_signal = context.metadata.get("previous_macd_signal")
        
        triggered = False
        if direction == "bullish" and macd_line > macd_signal:
            if previous_macd is not None and previous_macd <= previous_signal:
                triggered = True
        elif direction == "bearish" and macd_line < macd_signal:
            if previous_macd is not None and previous_macd >= previous_signal:
                triggered = True
        
        if triggered:
            return AlertResult(
                triggered=True,
                message=f"MACD {direction} crossover detected",
                severity=AlertSeverity.WARNING,
                metadata={"macd": macd_line, "signal": macd_signal}
            )
        
        return AlertResult(
            triggered=False,
            message="MACD crossover condition not met",
            severity=AlertSeverity.INFO
        )
    
    def _evaluate_portfolio_risk(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """Evaluate portfolio risk alert"""
        if context.metadata is None:
            return AlertResult(
                triggered=False,
                message="No portfolio data available",
                severity=AlertSeverity.INFO
            )
        
        risk_threshold = config.get("risk_threshold", 0.1)  # 10% default
        portfolio_risk = context.metadata.get("portfolio_risk")
        
        if portfolio_risk is None:
            return AlertResult(
                triggered=False,
                message="No portfolio risk data available",
                severity=AlertSeverity.INFO
            )
        
        if portfolio_risk >= risk_threshold:
            return AlertResult(
                triggered=True,
                message=f"Portfolio risk exceeds threshold: {portfolio_risk:.1%} >= {risk_threshold:.1%}",
                severity=AlertSeverity.CRITICAL,
                metadata={"risk": portfolio_risk, "threshold": risk_threshold}
            )
        
        return AlertResult(
            triggered=False,
            message="Portfolio risk within acceptable range",
            severity=AlertSeverity.INFO
        )
    
    def send_notification(
        self,
        result: AlertResult,
        context: AlertContext,
        channel: NotificationChannel,
        recipient: str,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send email notification"""
        if channel != NotificationChannel.EMAIL:
            raise AlertNotificationError(f"Email plugin does not support channel: {channel}")
        
        if not result.triggered:
            logger.debug(f"Alert not triggered, skipping email to {recipient}")
            return False
        
        # Get SMTP config from plugin config or settings
        smtp_config = config or {}
        smtp_host = smtp_config.get("smtp_host") or getattr(settings, "smtp_host", "smtp.gmail.com")
        smtp_port = smtp_config.get("smtp_port", 587)
        smtp_user = smtp_config.get("smtp_user") or getattr(settings, "smtp_user", None)
        smtp_password = smtp_config.get("smtp_password") or getattr(settings, "smtp_password", None)
        from_email = smtp_config.get("from_email") or smtp_user
        
        if not smtp_user or not smtp_password:
            raise AlertNotificationError("SMTP credentials not configured")
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = recipient
            msg['Subject'] = f"Trading Alert: {context.stock_symbol or 'Portfolio'}"
            
            # Build email body
            body = f"""
Trading Alert Notification

Alert Type: {result.message}
Severity: {result.severity.value.upper()}
Symbol: {context.stock_symbol or 'Portfolio'}
Portfolio: {context.portfolio_id or 'N/A'}

Timestamp: {result.timestamp}

---
This is an automated alert from Trading System.
"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            
            logger.info(f"✅ Email alert sent to {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}", exc_info=True)
            raise AlertNotificationError(f"Failed to send email: {str(e)}") from e
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate alert configuration"""
        alert_type = config.get("alert_type")
        if alert_type is None:
            raise ValidationError("Alert config must include 'alert_type'")
        
        # Validate based on alert type
        if alert_type == "price_threshold":
            if "threshold" not in config:
                raise ValidationError("Price threshold alert requires 'threshold'")
        elif alert_type == "signal_change":
            if "to_signal" not in config:
                raise ValidationError("Signal change alert requires 'to_signal'")
        elif alert_type == "volume_spike":
            if "multiplier" in config and not isinstance(config["multiplier"], (int, float)):
                raise ValidationError("Volume spike 'multiplier' must be a number")
        
        return True
    
    def is_available(self) -> bool:
        """Check if email service is available"""
        # Check if SMTP settings are configured
        smtp_host = getattr(settings, "smtp_host", None)
        smtp_user = getattr(settings, "smtp_user", None)
        return smtp_host is not None and smtp_user is not None

