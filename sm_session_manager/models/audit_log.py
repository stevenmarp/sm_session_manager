import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SmAuditLog(models.Model):
    _name = 'sm.audit.log'
    _description = 'User Activity Audit Log'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    user_id = fields.Many2one('res.users', string='User', required=True, index=True, ondelete='cascade')
    session_id = fields.Many2one('sm.user.session', string='Session', index=True, ondelete='set null')
    operation = fields.Selection([
        ('create', 'Create'),
        ('write', 'Update'),
        ('unlink', 'Delete'),
        ('read', 'Read'),
    ], string='Operation', required=True, index=True)
    model_name = fields.Char(string='Model', required=True, index=True)
    model_description = fields.Char(string='Model Description')
    res_id = fields.Integer(string='Record ID')
    res_name = fields.Char(string='Record Name')
    field_changes = fields.Text(string='Field Changes')
    ip_address = fields.Char(string='IP Address', compute='_compute_ip_address', store=True)
    direct_ip = fields.Char(string='Direct IP')
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now, required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('session_id', 'session_id.ip_address', 'direct_ip')
    def _compute_ip_address(self):
        for rec in self:
            rec.ip_address = rec.direct_ip or (rec.session_id.ip_address if rec.session_id else '')

    @api.depends('user_id', 'operation', 'model_name', 'res_name')
    def _compute_display_name(self):
        for rec in self:
            parts = [
                rec.user_id.name or '',
                dict(self._fields['operation'].selection).get(rec.operation, ''),
                rec.model_description or rec.model_name or '',
            ]
            if rec.res_name:
                parts.append(rec.res_name)
            rec.display_name = ' - '.join(filter(None, parts))

    @api.model
    def log_activity(self, operation, model_name, res_ids=None, field_changes=None):
        """Create audit log entries for an operation."""
        user = self.env.user
        if not user or user._is_superuser():
            return

        # Skip logging for audit log model itself to avoid recursion
        skip_models = [
            'sm.audit.log', 'sm.user.session',
            'ir.logging', 'bus.bus', 'bus.presence',
            'ir.attachment',  # too noisy
            'mail.message', 'mail.mail',  # mail related
            'ir.cron',  # cron
        ]
        if model_name in skip_models:
            return

        # Find active session for current user
        session = self._find_current_session()

        # Get current IP directly from request
        direct_ip = self._get_current_ip()

        # Get model description
        model_desc = ''
        try:
            ir_model = self.env['ir.model'].sudo().search([('model', '=', model_name)], limit=1)
            if ir_model:
                model_desc = ir_model.name
        except Exception:
            pass

        vals_list = []
        if res_ids:
            for res_id in (res_ids if isinstance(res_ids, (list, tuple)) else [res_ids]):
                # Try to get record name
                res_name = ''
                try:
                    record = self.env[model_name].sudo().browse(res_id)
                    if record.exists():
                        res_name = record.display_name or ''
                        # Truncate long names
                        if len(res_name) > 200:
                            res_name = res_name[:197] + '...'
                except Exception:
                    pass

                vals_list.append({
                    'user_id': user.id,
                    'session_id': session.id if session else False,
                    'operation': operation,
                    'model_name': model_name,
                    'model_description': model_desc,
                    'res_id': res_id,
                    'res_name': res_name,
                    'field_changes': field_changes if field_changes else False,
                    'direct_ip': direct_ip,
                })
        else:
            vals_list.append({
                'user_id': user.id,
                'session_id': session.id if session else False,
                'operation': operation,
                'model_name': model_name,
                'model_description': model_desc,
                'field_changes': field_changes if field_changes else False,
                'direct_ip': direct_ip,
            })

        try:
            self.sudo().create(vals_list)
        except Exception as e:
            _logger.warning("Failed to create audit log: %s", e)

    def _get_current_ip(self):
        """Get IP address directly from current HTTP request."""
        try:
            import odoo.http
            req = odoo.http.request
            if req and hasattr(req, 'httprequest') and req.httprequest:
                ip = req.httprequest.environ.get(
                    'HTTP_X_FORWARDED_FOR',
                    req.httprequest.environ.get('REMOTE_ADDR', '')
                )
                if ip:
                    return ip.split(',')[0].strip()
        except Exception:
            pass
        return ''

    def _find_current_session(self):
        """Find the current active session for the logged-in user."""
        try:
            import odoo.http
            request = odoo.http.request
            if request and hasattr(request, 'session') and request.session:
                session_token = request.session.sid
                if session_token:
                    return self.env['sm.user.session'].sudo().search([
                        ('session_id', '=', session_token),
                        ('user_id', '=', self.env.uid),
                        ('state', '=', 'active'),
                    ], limit=1)
        except Exception:
            pass
        return self.env['sm.user.session']

    @api.model
    def _cron_cleanup_old_logs(self):
        """Cron job to clean up old audit log records."""
        from datetime import timedelta
        ICP = self.env['ir.config_parameter'].sudo()
        cleanup_days = int(ICP.get_param('sm_session_manager.log_cleanup_days', '90'))
        if cleanup_days <= 0:
            return

        cutoff = fields.Datetime.now() - timedelta(days=cleanup_days)
        old_logs = self.sudo().search([('timestamp', '<', cutoff)])
        if old_logs:
            count = len(old_logs)
            old_logs.unlink()
            _logger.info("Cleaned up %d old audit log records", count)
