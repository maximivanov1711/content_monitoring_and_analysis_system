import requests
from typing import Optional

# N8N webhook URL for sending notifications
WEBHOOK_URL = "https://n8n-srza.onrender.com/webhook/6fd58f01-cd16-4182-a5e5-ddf666a91517"

NOTIFICATIONS_ENABLED = True

def notify(message: str, notification_type: str = "private", additional_data: Optional[dict] = None) -> bool:
    """
    Send notification via n8n webhook.
    
    Args:
        message (str): Notification message
        type (str): Notification type (warning, error, info, success)
        additional_data (dict, optional): Additional data to include in notification
        
    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    if not NOTIFICATIONS_ENABLED:
        return True
    
    try:
        # Prepare payload
        payload = {
            "message": message,
            "type": notification_type
        }
        
        # Add any additional data
        if additional_data:
            payload.update(additional_data)
        
        # Send notification with retry logic
        response = requests.post(
                WEBHOOK_URL,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Content-Monitor/1.0'
                }
            )
            
        # Check if request was successful
        response.raise_for_status()

        return True
        
    except Exception as e:
        return False


if __name__ == "__main__":
    notify("Test notification")