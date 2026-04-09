import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        """Auto-track sessions on every authenticated request."""
        res = super()._pre_dispatch(rule, args)
        try:
            cls._sm_ensure_session()
        except Exception as e:
            _logger.debug("Session tracking in _pre_dispatch failed: %s", e)
        return res

    @classmethod
    def _sm_ensure_session(cls):
        """Ensure the current authenticated user has a tracked session record."""
        import odoo.http
        req = odoo.http.request
        if not req or not req.session or not req.session.uid:
            return

        uid = req.session.uid
        sid = req.session.sid
        if not sid:
            return

        env = req.env
        if not env:
            return

        # Quick check — only search once per request via a flag on the request
        if getattr(req, '_sm_session_checked', False):
            return
        req._sm_session_checked = True

        existing = env['sm.user.session'].sudo().search([
            ('session_id', '=', sid),
            ('user_id', '=', uid),
        ], limit=1)

        if existing:
            # Update last_activity (at most once per request)
            existing.sudo().write({'last_activity': fields.Datetime.now()})
        else:
            # Auto-create session record
            ip_address = ''
            user_agent = ''
            if hasattr(req, 'httprequest') and req.httprequest:
                ip_address = req.httprequest.environ.get(
                    'HTTP_X_FORWARDED_FOR',
                    req.httprequest.environ.get('REMOTE_ADDR', '')
                )
                if ip_address:
                    ip_address = ip_address.split(',')[0].strip()
                user_agent = req.httprequest.environ.get('HTTP_USER_AGENT', '')

            env['sm.user.session'].sudo().create_session(
                user_id=uid,
                session_token=sid,
                ip_address=ip_address,
                user_agent_str=user_agent,
            )
            _logger.info("Auto-tracked session for user %s from IP %s", uid, ip_address)

    @classmethod
    def _post_logout(cls):
        """Hook into logout to mark session as expired."""
        try:
            import odoo.http
            req = odoo.http.request
            if req and req.session:
                sid = req.session.sid
                uid = req.session.uid or getattr(req.session, 'pre_uid', None)
                if sid and uid and req.env:
                    session_rec = req.env['sm.user.session'].sudo().search([
                        ('session_id', '=', sid),
                        ('state', '=', 'active'),
                    ], limit=1)
                    if session_rec:
                        session_rec.write({
                            'state': 'expired',
                            'logout_date': fields.Datetime.now(),
                        })
        except Exception as e:
            _logger.debug("Failed to track logout: %s", e)
        return super()._post_logout()
