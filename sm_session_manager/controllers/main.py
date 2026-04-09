import logging

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


def _get_client_ip():
    """Extract client IP from request, handling proxy headers."""
    ip_address = request.httprequest.environ.get(
        'HTTP_X_FORWARDED_FOR',
        request.httprequest.environ.get('REMOTE_ADDR', '')
    )
    if ip_address:
        ip_address = ip_address.split(',')[0].strip()
    return ip_address


class SessionManagerController(http.Controller):

    @http.route('/web/session/sm_check_login', type='json', auth='user', readonly=True)
    def check_and_track_session(self):
        """Called after login to track the session. This avoids overriding authenticate."""
        try:
            session_token = request.session.sid
            uid = request.session.uid
            if not uid or not session_token:
                return False

            # Check if this session is already tracked
            existing = request.env['sm.user.session'].sudo().search([
                ('session_id', '=', session_token),
                ('user_id', '=', uid),
            ], limit=1)
            if existing:
                # Update last activity
                existing.sudo().write({'last_activity': fields.Datetime.now()})
                return True

            ip_address = _get_client_ip()
            user_agent = request.httprequest.environ.get('HTTP_USER_AGENT', '')

            request.env['sm.user.session'].sudo().create_session(
                user_id=uid,
                session_token=session_token,
                ip_address=ip_address,
                user_agent_str=user_agent,
            )
            _logger.info("Session tracked for user %s from IP %s", uid, ip_address)
            return True
        except Exception as e:
            _logger.warning("Failed to track session: %s", e)
            return False

    @http.route('/web/session/sm_kill_my_session', type='json', auth='user')
    def kill_my_session(self, session_db_id):
        """Kill a specific session belonging to the current user."""
        try:
            session_rec = request.env['sm.user.session'].sudo().search([
                ('id', '=', int(session_db_id)),
                ('state', '=', 'active'),
            ], limit=1)
            if session_rec:
                # Check access: user can kill own, manager can kill any
                if (session_rec.user_id.id != request.env.uid
                        and not request.env.user.has_group('sm_session_manager.group_session_manager')):
                    return {'error': 'Access denied'}
                session_rec.action_kill_session()
                return {'success': True}
            return {'error': 'Session not found'}
        except Exception as e:
            _logger.warning("Failed to kill session: %s", e)
            return {'error': str(e)}
