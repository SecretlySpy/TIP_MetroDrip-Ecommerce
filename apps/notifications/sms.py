"""SMS notification adapter using Semaphore (D-5).

Gracefully falls back to a log message if the API key is unconfigured or the network request fails,
ensuring order confirmation and webhook handlers do not crash if SMS fails.
"""

import logging
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SEMAPHORE_API_KEY = getattr(settings, "SEMAPHORE_API_KEY", os.environ.get("SEMAPHORE_API_KEY", ""))
SEMAPHORE_SENDER_NAME = getattr(settings, "SEMAPHORE_SENDER_NAME", os.environ.get("SEMAPHORE_SENDER_NAME", "MetroDrip"))

def send_sms(phone_number, message):
    """Send an SMS via Semaphore, failing gracefully on error."""
    if not SEMAPHORE_API_KEY:
        logger.info(f"SMS mocked for {phone_number}: {message}")
        return False
        
    try:
        response = requests.post(
            "https://api.semaphore.co/api/v4/messages",
            data={
                "apikey": SEMAPHORE_API_KEY,
                "number": phone_number,
                "message": message,
                "sendername": SEMAPHORE_SENDER_NAME
            },
            timeout=5
        )
        response.raise_for_status()
        logger.info(f"SMS sent successfully to {phone_number}")
        return True
    except Exception as e:
        logger.warning(f"Failed to send SMS to {phone_number}: {str(e)}")
        return False
