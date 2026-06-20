"""
Socket.io Service
Handles socket event emission for real-time notifications.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from config.socket_config import broadcast_notification, broadcast_data_update


class SocketNotificationService:
    """Service for emitting socket notifications."""

    @staticmethod
    async def notify_file_upload(filename: str, team_name: str, status: str = 'success'):
        """Emit file upload notification."""
        await broadcast_notification({
            'type': 'upload',
            'message': f"File '{filename}' uploaded successfully for {team_name}",
            'team': team_name,
            'timestamp': datetime.now().isoformat(),
            'data': {
                'filename': filename,
                'team_name': team_name,
                'status': status,
            },
        })

    @staticmethod
    async def notify_action_assigned(employee_name: str, action_type: str, team_name: str):
        """Emit action assigned notification."""
        await broadcast_notification({
            'type': 'action',
            'message': f"{action_type} assigned to {employee_name} in {team_name}",
            'team': team_name,
            'timestamp': datetime.now().isoformat(),
            'data': {
                'employee_name': employee_name,
                'action_type': action_type,
                'team_name': team_name,
            },
        })

    @staticmethod
    async def notify_performance_updated(team_name: str, metric_name: str, new_value: float):
        """Emit performance data update."""
        await broadcast_data_update('performance_updated', {
            'team_name': team_name,
            'metric_name': metric_name,
            'new_value': new_value,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    async def notify_error(error_message: str, user_id: Optional[str] = None):
        """Emit error notification."""
        await broadcast_notification({
            'type': 'error',
            'message': error_message,
            'timestamp': datetime.now().isoformat(),
            'data': {
                'user_id': user_id,
            },
        })

    @staticmethod
    async def notify_success(success_message: str, team_name: Optional[str] = None):
        """Emit success notification."""
        await broadcast_notification({
            'type': 'success',
            'message': success_message,
            'team': team_name,
            'timestamp': datetime.now().isoformat(),
        })

    @staticmethod
    async def notify_info(info_message: str, team_name: Optional[str] = None):
        """Emit info notification."""
        await broadcast_notification({
            'type': 'info',
            'message': info_message,
            'team': team_name,
            'timestamp': datetime.now().isoformat(),
        })
