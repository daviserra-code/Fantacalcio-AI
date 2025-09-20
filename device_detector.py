# -*- coding: utf-8 -*-
"""
Device Detection Utility for FantacalcioAI
Determines device type to serve appropriate UI:
- Mobile devices: Current mobile-friendly UI
- Desktop/Tablet/iPad: New web-like UI
"""

import re
from flask import request


class DeviceDetector:
    """Device detection utility to differentiate mobile vs desktop/tablet."""
    
    # Mobile device patterns - these get the mobile UI
    MOBILE_PATTERNS = [
        r'Mobile',
        r'Android.*Mobile',
        r'iPhone',
        r'iPod',
        r'BlackBerry',
        r'Opera Mini',
        r'Windows Phone',
        r'webOS',
        r'Fennec',
    ]
    
    # Tablet patterns - these get the desktop UI (web-like)
    TABLET_PATTERNS = [
        r'iPad',
        r'Android(?!.*Mobile)',  # Android tablet (not mobile)
        r'Tablet',
        r'PlayBook',
        r'Kindle',
    ]
    
    @classmethod
    def is_mobile_device(cls) -> bool:
        """
        Detect if the current request is from a mobile device.
        
        Returns:
            bool: True if mobile device, False if desktop/tablet
        """
        user_agent = request.headers.get('User-Agent', '').strip()
        
        if not user_agent:
            # No user agent, default to desktop UI
            return False
        
        # Check for tablet patterns FIRST - these get desktop UI
        # This prevents iPads from being classified as mobile
        
        # Special case for iPadOS 13+ that sends desktop-like UA with Macintosh + Mobile
        if re.search(r'Macintosh.*Mobile', user_agent, re.IGNORECASE):
            return False  # Treat as tablet/desktop
        
        for pattern in cls.TABLET_PATTERNS:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return False
        
        # Then check for mobile patterns
        for pattern in cls.MOBILE_PATTERNS:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return True
        
        # Default: assume desktop/laptop for unknown devices
        return False
    
    @classmethod
    def get_device_type(cls) -> str:
        """
        Get descriptive device type for logging/debugging.
        
        Returns:
            str: 'mobile', 'tablet', or 'desktop'
        """
        user_agent = request.headers.get('User-Agent', '').strip()
        
        if not user_agent:
            return 'desktop'
        
        # Check tablet first (includes iPad)
        
        # Special case for iPadOS 13+ that sends desktop-like UA with Macintosh + Mobile
        if re.search(r'Macintosh.*Mobile', user_agent, re.IGNORECASE):
            return 'tablet'
        
        for pattern in cls.TABLET_PATTERNS:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return 'tablet'
        
        # Then check mobile
        for pattern in cls.MOBILE_PATTERNS:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return 'mobile'
        
        return 'desktop'
    
    @classmethod
    def get_ui_mode(cls) -> str:
        """
        Get UI mode for the current device.
        
        Returns:
            str: 'mobile' for mobile UI, 'desktop' for web-like UI
        """
        return 'mobile' if cls.is_mobile_device() else 'desktop'


def is_mobile_device() -> bool:
    """Convenience function for device detection."""
    return DeviceDetector.is_mobile_device()


def get_device_type() -> str:
    """Convenience function to get device type."""
    return DeviceDetector.get_device_type()


def get_ui_mode() -> str:
    """Convenience function to get UI mode."""
    return DeviceDetector.get_ui_mode()