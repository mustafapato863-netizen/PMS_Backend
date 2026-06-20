"""
Socket.io Configuration and Setup
Handles real-time communication for notifications and live data updates.
"""

from socketio import AsyncServer, AsyncNamespace

# Create global Socket.io instance
sio = AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=['*'],
    ping_timeout=60,
    ping_interval=25,
    client_manager=None,
)

# Track connected clients
connected_clients = {}


class NotificationNamespace(AsyncNamespace):
    """Handle notification events."""

    async def on_connect(self, sid, environ):
        """Client connected."""
        connected_clients[sid] = {
            'sid': sid,
            'timestamp': __import__('datetime').datetime.now(),
        }
        print(f"Client {sid} connected. Total: {len(connected_clients)}")

    async def on_disconnect(self, sid):
        """Client disconnected."""
        if sid in connected_clients:
            del connected_clients[sid]
        print(f"Client {sid} disconnected. Total: {len(connected_clients)}")

    async def on_subscribe_team(self, sid, data):
        """Subscribe to team notifications."""
        team_name = data.get('team_name')
        if team_name and sid in connected_clients:
            connected_clients[sid]['team'] = team_name
            print(f"Client {sid} subscribed to team: {team_name}")


# Register namespace
sio.register_namespace(NotificationNamespace('/notifications'))


async def broadcast_notification(notification_data):
    """
    Broadcast notification to all connected clients.
    
    Args:
        notification_data: Dict with keys:
            - type: 'upload' | 'action' | 'error' | 'success' | 'info'
            - message: str
            - team: str (optional, for team-specific notifications)
    """
    if not connected_clients:
        return

    team_filter = notification_data.get('team')

    for sid, client_info in connected_clients.items():
        # Skip if notification is team-specific and client not subscribed
        if team_filter and client_info.get('team') != team_filter:
            continue

        try:
            await sio.emit('notification', notification_data, to=sid, namespace='/notifications')
        except Exception as e:
            print(f"Failed to send notification to {sid}: {e}")


async def broadcast_data_update(event_type, data):
    """
    Broadcast data update to all connected clients.
    
    Args:
        event_type: str - Type of data update (e.g., 'performance_updated')
        data: dict - Update data
    """
    if not connected_clients:
        return

    for sid in connected_clients.keys():
        try:
            await sio.emit(event_type, data, to=sid, namespace='/notifications')
        except Exception as e:
            print(f"Failed to send update to {sid}: {e}")
