# websocket_handlers.py - WebSocket event handlers for real-time statistics
import logging
from flask_socketio import emit, join_room, leave_room
from datetime import datetime

logger = logging.getLogger(__name__)

def register_websocket_handlers(socketio):
    """Register all WebSocket event handlers"""
    
    @socketio.on('connect')
    def handle_connect():
        logger.info("Client connected to WebSocket for real-time updates")
        emit('status', {
            'msg': 'Connected to real-time fantasy football updates',
            'timestamp': str(datetime.now())
        })

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info("Client disconnected from WebSocket")

    @socketio.on('join_statistics')
    def handle_join_statistics():
        """Join real-time statistics updates room"""
        join_room('statistics')
        logger.info("Client joined statistics updates room")
        emit('joined', {
            'room': 'statistics',
            'msg': 'Joined real-time statistics updates'
        })

    @socketio.on('leave_statistics')
    def handle_leave_statistics():
        """Leave statistics updates room"""
        leave_room('statistics')
        logger.info("Client left statistics updates room")
        emit('left', {
            'room': 'statistics',
            'msg': 'Left statistics updates'
        })

    @socketio.on('request_live_stats')
    def handle_request_live_stats():
        """Handle request for current live statistics"""
        try:
            # Import here to avoid circular imports
            import requests
            
            # Get current statistics via API call
            response = requests.get('http://localhost:5000/api/statistics', timeout=5)
            stats = response.json() if response.status_code == 200 else {"error": "Failed to fetch stats"}
            
            # Emit to requesting client
            emit('live_stats_update', {
                'data': stats,
                'timestamp': str(datetime.now()),
                'type': 'full_update'
            })
            
            logger.info("Live statistics sent to client")
            
        except Exception as e:
            logger.error(f"Error sending live statistics: {e}")
            emit('error', {
                'msg': f'Error retrieving statistics: {str(e)}',
                'timestamp': str(datetime.now())
            })

    # Background task to periodically broadcast statistics updates
    def background_statistics_updates():
        """Background task to periodically send statistics updates"""
        import time
        import threading
        
        def stats_updater():
            while True:
                try:
                    # Import here to avoid circular imports
                    import requests
                    
                    # Get current statistics via API call
                    response = requests.get('http://localhost:5000/api/statistics', timeout=5)
                    stats = response.json() if response.status_code == 200 else {"error": "Failed to fetch stats"}
                    
                    # Broadcast to all clients in statistics room
                    socketio.emit('live_stats_update', {
                        'data': stats,
                        'timestamp': str(datetime.now()),
                        'type': 'periodic_update'
                    }, room='statistics')
                    
                    logger.debug("Periodic statistics update broadcasted")
                    
                except Exception as e:
                    logger.error(f"Error in background statistics update: {e}")
                
                # Wait 30 seconds before next update
                time.sleep(30)
        
        # Start background thread
        thread = threading.Thread(target=stats_updater, daemon=True)
        thread.start()
        logger.info("Background statistics update thread started")
    
    # Start background updates
    background_statistics_updates()

    logger.info("WebSocket handlers registered successfully")