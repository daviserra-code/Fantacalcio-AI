# league_chat.py - Real-time chat for fantasy leagues
import logging
from datetime import datetime
from flask import request
from flask_socketio import emit, join_room, leave_room, rooms
from flask_login import current_user
from app import socketio, db
from models import UserLeague
from sqlalchemy import text

LOG = logging.getLogger("league_chat")

# In-memory message store (TODO: Move to Redis or PostgreSQL)
league_messages = {}
active_users = {}

@socketio.on('join_league_chat')
def handle_join_league(data):
    """User joins a league chat room"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return
    
    league_id = data.get('league_id')
    if not league_id:
        emit('error', {'message': 'League ID required'})
        return
    
    # Verify user has access to this league
    league = UserLeague.query.filter_by(
        id=league_id,
        user_id=current_user.id
    ).first()
    
    if not league:
        emit('error', {'message': 'Access denied to this league'})
        return
    
    room_name = f'league_{league_id}'
    join_room(room_name)
    
    # Track active user
    if league_id not in active_users:
        active_users[league_id] = set()
    active_users[league_id].add(current_user.id)
    
    # Send join notification
    emit('user_joined', {
        'user_id': current_user.id,
        'username': current_user.username,
        'timestamp': datetime.now().isoformat(),
        'active_count': len(active_users[league_id])
    }, room=room_name)
    
    # Send recent messages to new user
    if league_id in league_messages:
        emit('message_history', {
            'messages': league_messages[league_id][-50:]  # Last 50 messages
        })
    
    LOG.info(f"User {current_user.username} joined league chat {league_id}")

@socketio.on('leave_league_chat')
def handle_leave_league(data):
    """User leaves a league chat room"""
    if not current_user.is_authenticated:
        return
    
    league_id = data.get('league_id')
    if not league_id:
        return
    
    room_name = f'league_{league_id}'
    leave_room(room_name)
    
    # Remove from active users
    if league_id in active_users:
        active_users[league_id].discard(current_user.id)
    
    # Send leave notification
    emit('user_left', {
        'user_id': current_user.id,
        'username': current_user.username,
        'timestamp': datetime.now().isoformat(),
        'active_count': len(active_users.get(league_id, set()))
    }, room=room_name)
    
    LOG.info(f"User {current_user.username} left league chat {league_id}")

@socketio.on('send_message')
def handle_send_message(data):
    """User sends a message to league chat"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return
    
    league_id = data.get('league_id')
    message_text = data.get('message', '').strip()
    
    if not league_id or not message_text:
        emit('error', {'message': 'League ID and message required'})
        return
    
    # Verify user is in this league
    league = UserLeague.query.filter_by(
        id=league_id,
        user_id=current_user.id
    ).first()
    
    if not league:
        emit('error', {'message': 'Access denied'})
        return
    
    # Create message object
    message = {
        'id': f"{league_id}_{datetime.now().timestamp()}",
        'league_id': league_id,
        'user_id': current_user.id,
        'username': current_user.username,
        'message': message_text,
        'timestamp': datetime.now().isoformat(),
        'is_pro': current_user.is_pro
    }
    
    # Store message
    if league_id not in league_messages:
        league_messages[league_id] = []
    league_messages[league_id].append(message)
    
    # Keep only last 100 messages per league
    if len(league_messages[league_id]) > 100:
        league_messages[league_id] = league_messages[league_id][-100:]
    
    # Broadcast to all users in league
    room_name = f'league_{league_id}'
    emit('new_message', message, room=room_name)
    
    LOG.info(f"Message sent in league {league_id} by {current_user.username}")

@socketio.on('typing')
def handle_typing(data):
    """User is typing indicator"""
    if not current_user.is_authenticated:
        return
    
    league_id = data.get('league_id')
    is_typing = data.get('is_typing', False)
    
    if not league_id:
        return
    
    room_name = f'league_{league_id}'
    emit('user_typing', {
        'user_id': current_user.id,
        'username': current_user.username,
        'is_typing': is_typing
    }, room=room_name, include_self=False)

@socketio.on('delete_message')
def handle_delete_message(data):
    """Delete a message (only message author or league admin)"""
    if not current_user.is_authenticated:
        return
    
    league_id = data.get('league_id')
    message_id = data.get('message_id')
    
    if not league_id or not message_id:
        return
    
    # Find and delete message
    if league_id in league_messages:
        messages = league_messages[league_id]
        for i, msg in enumerate(messages):
            if msg['id'] == message_id:
                # Check if user owns the message
                if msg['user_id'] == current_user.id:
                    messages.pop(i)
                    
                    room_name = f'league_{league_id}'
                    emit('message_deleted', {
                        'message_id': message_id
                    }, room=room_name)
                    
                    LOG.info(f"Message {message_id} deleted by {current_user.username}")
                    return
                else:
                    emit('error', {'message': 'Not authorized to delete this message'})
                    return

@socketio.on('get_active_users')
def handle_get_active_users(data):
    """Get list of active users in league"""
    if not current_user.is_authenticated:
        return
    
    league_id = data.get('league_id')
    if not league_id:
        return
    
    active_user_ids = list(active_users.get(league_id, set()))
    
    # TODO: Fetch user details from database
    emit('active_users', {
        'league_id': league_id,
        'user_ids': active_user_ids,
        'count': len(active_user_ids)
    })

def get_league_chat_stats(league_id: int) -> dict:
    """Get chat statistics for a league"""
    if league_id not in league_messages:
        return {
            'total_messages': 0,
            'active_users': 0,
            'last_message': None
        }
    
    messages = league_messages[league_id]
    return {
        'total_messages': len(messages),
        'active_users': len(active_users.get(league_id, set())),
        'last_message': messages[-1] if messages else None
    }

# Cleanup function to run periodically
def cleanup_inactive_users():
    """Remove inactive users from active_users tracking"""
    # TODO: Implement heartbeat system to detect disconnected users
    pass
