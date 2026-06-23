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
            'teams': set(),
            'rooms': {'global'},
            'global_subscriber': True,
            'role': None,
        }
        await self.enter_room(sid, 'global')
        print(f"Client {sid} connected. Total: {len(connected_clients)}")

    async def on_disconnect(self, sid):
        """Client disconnected."""
        if sid in connected_clients:
            del connected_clients[sid]
        print(f"Client {sid} disconnected. Total: {len(connected_clients)}")

    async def on_join_room(self, sid, data):
        """Join a socket room."""
        room = data.get('room')
        if not room or sid not in connected_clients:
            return
        await self.enter_room(sid, room)
        if 'rooms' not in connected_clients[sid]:
            connected_clients[sid]['rooms'] = set()
        connected_clients[sid]['rooms'].add(room)
        print(f"Client {sid} joined room: {room}")

    async def on_leave_room(self, sid, data):
        """Leave a socket room."""
        room = data.get('room')
        if not room or sid not in connected_clients:
            return
        await self.leave_room(sid, room)
        if 'rooms' in connected_clients[sid]:
            connected_clients[sid]['rooms'].discard(room)
        print(f"Client {sid} left room: {room}")

    async def on_subscribe_team(self, sid, data):
        """Subscribe to team notifications."""
        team_names = data.get('team_names')
        team_name = data.get('team_name')
        is_global = bool(data.get('global'))
        role = data.get('role')
        if sid not in connected_clients:
            return

        client = connected_clients[sid]
        if role:
            client['role'] = role
            if role == 'Admin':
                await self.enter_room(sid, 'admin')
                if 'rooms' not in client:
                    client['rooms'] = set()
                client['rooms'].add('admin')

        client['global_subscriber'] = is_global or (not team_name and not team_names)
        if team_names:
            client['teams'] = set(team_names)
            for t in team_names:
                await self.enter_room(sid, f"team_{t}")
                if 'rooms' not in client:
                    client['rooms'] = set()
                client['rooms'].add(f"team_{t}")
            print(f"Client {sid} subscribed to teams: {team_names}")
        elif team_name:
            client['teams'] = {team_name}
            client['global_subscriber'] = False
            await self.enter_room(sid, f"team_{team_name}")
            if 'rooms' not in client:
                client['rooms'] = set()
            client['rooms'].add(f"team_{team_name}")
            print(f"Client {sid} subscribed to team: {team_name}")
        elif is_global:
            client['teams'] = set()
            print(f"Client {sid} subscribed globally")


# Register namespace
sio.register_namespace(NotificationNamespace('/notifications'))


def save_notification_to_db(notification_data: dict, db=None) -> str | None:
    """Save notification and create recipients in the database."""
    from config.database import SessionLocal
    from models.models import Notification, NotificationRecipient, User, UserTeamAssignment, Team
    import uuid
    from datetime import datetime, timezone

    is_local_db = False
    if db is None:
        db = SessionLocal()
        is_local_db = True

    try:
        ntype = notification_data.get('type', 'info')
        db_type = 'system'
        if ntype == 'action':
            db_type = 'action_recorded'
        elif ntype == 'upload':
            db_type = 'data_upload'
        elif ntype == 'error':
            db_type = 'warning'
        elif ntype == 'success':
            db_type = 'system'

        title_map = {
            'action': 'Action Assigned',
            'upload': 'Data Uploaded',
            'error': 'System Error',
            'success': 'Operation Success',
            'info': 'System Info'
        }
        title = title_map.get(ntype, 'Notification')

        team_name = notification_data.get('team')
        
        notification = Notification(
            id=uuid.uuid4(),
            type=db_type,
            title=title,
            message=notification_data.get('message', ''),
            room=f"team_{team_name}" if team_name else "global",
            payload=notification_data.get('data'),
            created_at=datetime.now(timezone.utc)
        )
        db.add(notification)
        db.flush()

        recipient_user_ids = set()

        # Active Admin users always receive notifications
        admins = db.query(User).filter(User.role == 'Admin', User.is_active == True).all()
        for admin in admins:
            recipient_user_ids.add(admin.id)

        # If team-scoped, active Managers assigned to that team also receive notifications
        if team_name:
            managers = (
                db.query(User)
                .join(UserTeamAssignment, User.id == UserTeamAssignment.user_id)
                .join(Team, UserTeamAssignment.team_id == Team.id)
                .filter(
                    User.role == 'Manager',
                    User.is_active == True,
                    Team.name == team_name,
                    Team.is_active == True
                )
                .all()
            )
            for manager in managers:
                recipient_user_ids.add(manager.id)

        for user_id in recipient_user_ids:
            recipient = NotificationRecipient(
                id=uuid.uuid4(),
                notification_id=notification.id,
                user_id=user_id,
                is_read=False,
                created_at=datetime.now(timezone.utc)
            )
            db.add(recipient)

        if is_local_db:
            db.commit()
        else:
            db.flush()

        return str(notification.id)
    except Exception as e:
        if is_local_db:
            db.rollback()
        print(f"Failed to save notification to database: {e}")
        return None
    finally:
        if is_local_db:
            db.close()


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

    # Save notification to DB and attach ID to payload
    db_id = save_notification_to_db(notification_data)
    if db_id:
        notification_data['id'] = db_id

    team_filter = notification_data.get('team')

    for sid, client_info in connected_clients.items():
        is_admin = client_info.get('role') == 'Admin' or 'admin' in client_info.get('rooms', set())
        
        if is_admin:
            pass
        elif team_filter:
            client_teams = client_info.get('teams') or set()
            if team_filter not in client_teams and not client_info.get('global_subscriber'):
                continue
        elif not client_info.get('global_subscriber'):
            continue

        try:
            await sio.emit('notification', notification_data, to=sid, namespace='/notifications')
        except Exception as e:
            print(f"Failed to send notification to {sid}: {e}")


async def broadcast_action_recorded(action_data):
    """Broadcast corrective-action updates to all authorized clients."""
    if not connected_clients:
        return

    team_filter = action_data.get('team')

    for sid, client_info in connected_clients.items():
        is_admin = client_info.get('role') == 'Admin' or 'admin' in client_info.get('rooms', set())
        
        if is_admin:
            pass
        elif team_filter:
            client_teams = client_info.get('teams') or set()
            if team_filter not in client_teams and not client_info.get('global_subscriber'):
                continue
        elif not client_info.get('global_subscriber'):
            continue

        try:
            await sio.emit('action_recorded', action_data, to=sid, namespace='/notifications')
        except Exception as e:
            print(f"Failed to send action record to {sid}: {e}")


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
