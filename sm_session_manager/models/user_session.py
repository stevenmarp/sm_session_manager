import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from user_agents import parse as ua_parse
except ImportError:
    ua_parse = None
    _logger.warning("user_agents library not installed. Install with: pip install user-agents")


class SmUserSession(models.Model):
    _name = 'sm.user.session'
    _description = 'User Session'
    _order = 'login_date desc'
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', string='User', required=True, index=True, ondelete='cascade')
    session_id = fields.Char(string='Session Token', required=True, index=True)
    login_date = fields.Datetime(string='Login Date', default=fields.Datetime.now, required=True)
    logout_date = fields.Datetime(string='Logout Date')
    ip_address = fields.Char(string='IP Address')
    user_agent = fields.Char(string='User Agent (Raw)')
    browser = fields.Char(string='Browser')
    operating_system = fields.Char(string='Operating System')
    device = fields.Char(string='Device')
    is_mobile = fields.Boolean(string='Is Mobile')
    geo_city = fields.Char(string='City')
    geo_country = fields.Char(string='Country')
    state = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('killed', 'Killed'),
    ], string='Status', default='active', required=True, index=True)
    last_activity = fields.Datetime(string='Last Activity', default=fields.Datetime.now)
    audit_log_ids = fields.One2many('sm.audit.log', 'session_id', string='Activity Logs')
    audit_log_count = fields.Integer(string='Activity Count', compute='_compute_audit_log_count')

    @api.depends('audit_log_ids')
    def _compute_audit_log_count(self):
        for rec in self:
            rec.audit_log_count = len(rec.audit_log_ids)

    def _parse_user_agent(self, ua_string):
        """Parse user agent string to extract browser, OS, device info."""
        if not ua_string or not ua_parse:
            return {}
        try:
            ua = ua_parse(ua_string)
            return {
                'browser': f"{ua.browser.family} {ua.browser.version_string}",
                'operating_system': f"{ua.os.family} {ua.os.version_string}",
                'device': ua.device.family,
                'is_mobile': ua.is_mobile,
            }
        except Exception:
            return {}

    def _resolve_geoip(self, ip_address):
        """Try to resolve IP to city/country using Odoo's GeoIP if available."""
        if not ip_address:
            return {}
        try:
            geo = self.env['ir.http']._geoip_resolve(ip_address) if hasattr(self.env['ir.http'], '_geoip_resolve') else {}
            if geo:
                return {
                    'geo_city': geo.get('city', ''),
                    'geo_country': geo.get('country_name', ''),
                }
        except Exception:
            pass
        return {}

    @api.model
    def create_session(self, user_id, session_token, ip_address=None, user_agent_str=None):
        """Create a new session record when user logs in."""
        vals = {
            'user_id': user_id,
            'session_id': session_token,
            'ip_address': ip_address,
            'user_agent': user_agent_str,
            'state': 'active',
        }
        # Parse user agent
        ua_data = self._parse_user_agent(user_agent_str)
        vals.update(ua_data)

        # GeoIP
        geo_data = self._resolve_geoip(ip_address)
        vals.update(geo_data)

        session = self.sudo().create(vals)

        # Send email notification if enabled
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('sm_session_manager.notify_new_login', 'False') == 'True':
            session._send_login_notification()

        return session

    def _send_login_notification(self):
        """Send email notification to user about new login."""
        self.ensure_one()
        template = self.env.ref('sm_session_manager.mail_template_new_login', raise_if_not_found=False)
        if template:
            try:
                template.send_mail(self.id, force_send=True)
            except Exception as e:
                _logger.warning("Failed to send login notification: %s", e)

    def action_kill_session(self):
        """Kill/force logout a session."""
        for rec in self:
            if rec.state != 'active':
                continue
            rec.write({
                'state': 'killed',
                'logout_date': fields.Datetime.now(),
            })
            # Invalidate the session in Odoo's session store
            rec._invalidate_http_session()
        return True

    def _invalidate_http_session(self):
        """Remove the session from the session store to force logout."""
        self.ensure_one()
        try:
            import odoo.http
            session_store = odoo.http.root.session_store
            if session_store and self.session_id:
                session_store.delete(self.session_id)
        except Exception as e:
            _logger.warning("Could not invalidate HTTP session %s: %s", self.session_id, e)

    def action_view_audit_logs(self):
        """Open related audit logs."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Activity Logs'),
            'res_model': 'sm.audit.log',
            'view_mode': 'tree,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id},
        }

    @api.model
    def _cron_auto_kill_sessions(self):
        """Cron job to auto-kill expired sessions."""
        ICP = self.env['ir.config_parameter'].sudo()
        kill_mode = ICP.get_param('sm_session_manager.auto_kill_mode', 'none')
        if kill_mode == 'none':
            return

        duration_hours = float(ICP.get_param('sm_session_manager.session_duration_hours', '24'))
        if duration_hours <= 0:
            return

        cutoff = fields.Datetime.now() - timedelta(hours=duration_hours)
        domain = [('state', '=', 'active')]

        if kill_mode == 'inactive':
            # Kill sessions inactive for longer than duration
            domain.append(('last_activity', '<', cutoff))
        elif kill_mode == 'active':
            # Kill sessions older than duration regardless
            domain.append(('login_date', '<', cutoff))

        sessions = self.sudo().search(domain)
        for session in sessions:
            session.write({
                'state': 'expired',
                'logout_date': fields.Datetime.now(),
            })
            session._invalidate_http_session()

        if sessions:
            _logger.info("Auto-killed %d expired sessions (mode: %s)", len(sessions), kill_mode)

    @api.model
    def _cron_cleanup_old_sessions(self):
        """Cron job to clean up old session records."""
        ICP = self.env['ir.config_parameter'].sudo()
        cleanup_days = int(ICP.get_param('sm_session_manager.cleanup_days', '90'))
        if cleanup_days <= 0:
            return

        cutoff = fields.Datetime.now() - timedelta(days=cleanup_days)
        old_sessions = self.sudo().search([
            ('state', 'in', ['expired', 'killed']),
            ('login_date', '<', cutoff),
        ])
        if old_sessions:
            count = len(old_sessions)
            old_sessions.unlink()
            _logger.info("Cleaned up %d old session records", count)
