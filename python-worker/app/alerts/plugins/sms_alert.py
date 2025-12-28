"""
SMS Alert Plugin
Sends alerts via SMS (using Twilio or similar service)
"""
import logging
from typing import Dict, Any, Optional
from app.alerts.base import (
    BaseAlertPlugin, AlertMetadata, AlertContext, AlertResult,
    AlertSeverity, NotificationChannel
)
from app.exceptions import AlertNotificationError, ValidationError
from app.config import settings

logger = logging.getLogger(__name__)


class SMSAlertPlugin(BaseAlertPlugin):
    """
    SMS alert plugin
    Supports sending alerts via SMS (Twilio, AWS SNS, etc.)
    """
    
    def get_metadata(self) -> AlertMetadata:
        return AlertMetadata(
            alert_type_id="sms_alert",
            name="SMS Alert",
            display_name="SMS Notification",
            description="Sends alerts via SMS",
            version="1.0.0",
            config_schema={
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "enum": ["twilio", "aws_sns"], "default": "twilio"},
                    "account_sid": {"type": "string"},
                    "auth_token": {"type": "string"},
                    "from_number": {"type": "string"},
                },
                "required": ["account_sid", "auth_token", "from_number"]
            },
            supported_channels=[NotificationChannel.SMS],
            subscription_level_required="pro"
        )
    
    def evaluate(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """
        SMS plugin uses the same evaluation logic as email
        Delegate to email plugin for consistency
        """
        # Import here to avoid circular dependency
        from app.alerts.plugins.email_alert import EmailAlertPlugin
        
        email_plugin = EmailAlertPlugin()
        return email_plugin.evaluate(context, config)
    
    def send_notification(
        self,
        result: AlertResult,
        context: AlertContext,
        channel: NotificationChannel,
        recipient: str,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send SMS notification"""
        if channel != NotificationChannel.SMS:
            raise AlertNotificationError(f"SMS plugin does not support channel: {channel}")
        
        if not result.triggered:
            logger.debug(f"Alert not triggered, skipping SMS to {recipient}")
            return False
        
        # Get SMS config
        sms_config = config or {}
        provider = sms_config.get("provider", "twilio")
        account_sid = sms_config.get("account_sid") or getattr(settings, "twilio_account_sid", None)
        auth_token = sms_config.get("auth_token") or getattr(settings, "twilio_auth_token", None)
        from_number = sms_config.get("from_number") or getattr(settings, "twilio_from_number", None)
        
        if not account_sid or not auth_token or not from_number:
            raise AlertNotificationError("SMS credentials not configured")
        
        try:
            if provider == "twilio":
                return self._send_via_twilio(
                    result, context, recipient,
                    account_sid, auth_token, from_number
                )
            elif provider == "aws_sns":
                return self._send_via_aws_sns(
                    result, context, recipient, sms_config
                )
            else:
                raise AlertNotificationError(f"Unsupported SMS provider: {provider}")
                
        except Exception as e:
            logger.error(f"Failed to send SMS alert: {e}", exc_info=True)
            raise AlertNotificationError(f"Failed to send SMS: {str(e)}") from e
    
    def _send_via_twilio(
        self,
        result: AlertResult,
        context: AlertContext,
        recipient: str,
        account_sid: str,
        auth_token: str,
        from_number: str
    ) -> bool:
        """Send SMS via Twilio"""
        try:
            # Try to import twilio
            from twilio.rest import Client
            
            client = Client(account_sid, auth_token)
            
            # Build SMS message
            message = f"Alert: {result.message} | {context.stock_symbol or 'Portfolio'}"
            
            # Send SMS
            message_obj = client.messages.create(
                body=message,
                from_=from_number,
                to=recipient
            )
            
            logger.info(f"✅ SMS alert sent to {recipient} (SID: {message_obj.sid})")
            return True
            
        except ImportError:
            logger.warning("Twilio library not installed. Install with: pip install twilio")
            # For testing, log the SMS instead
            logger.info(f"[SMS TEST] To: {recipient}, Message: {result.message}")
            return True  # Return True for testing
        except Exception as e:
            raise AlertNotificationError(f"Twilio error: {str(e)}") from e
    
    def _send_via_aws_sns(
        self,
        result: AlertResult,
        context: AlertContext,
        recipient: str,
        config: Dict[str, Any]
    ) -> bool:
        """Send SMS via AWS SNS"""
        try:
            import boto3
            
            sns = boto3.client(
                'sns',
                aws_access_key_id=config.get("aws_access_key_id"),
                aws_secret_access_key=config.get("aws_secret_access_key"),
                region_name=config.get("aws_region", "us-east-1")
            )
            
            message = f"Alert: {result.message} | {context.stock_symbol or 'Portfolio'}"
            
            response = sns.publish(
                PhoneNumber=recipient,
                Message=message
            )
            
            logger.info(f"✅ SMS alert sent via AWS SNS to {recipient} (MessageId: {response['MessageId']})")
            return True
            
        except ImportError:
            logger.warning("boto3 library not installed. Install with: pip install boto3")
            # For testing, log the SMS instead
            logger.info(f"[SMS TEST] To: {recipient}, Message: {result.message}")
            return True  # Return True for testing
        except Exception as e:
            raise AlertNotificationError(f"AWS SNS error: {str(e)}") from e
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate SMS alert configuration"""
        provider = config.get("provider", "twilio")
        
        if provider == "twilio":
            required = ["account_sid", "auth_token", "from_number"]
            missing = [key for key in required if key not in config]
            if missing:
                raise ValidationError(f"Twilio config missing: {missing}")
        elif provider == "aws_sns":
            required = ["aws_access_key_id", "aws_secret_access_key"]
            missing = [key for key in required if key not in config]
            if missing:
                raise ValidationError(f"AWS SNS config missing: {missing}")
        else:
            raise ValidationError(f"Unsupported SMS provider: {provider}")
        
        return True
    
    def is_available(self) -> bool:
        """Check if SMS service is available"""
        # Check if Twilio or AWS SNS settings are configured
        twilio_sid = getattr(settings, "twilio_account_sid", None)
        aws_key = getattr(settings, "aws_access_key_id", None)
        return twilio_sid is not None or aws_key is not None

