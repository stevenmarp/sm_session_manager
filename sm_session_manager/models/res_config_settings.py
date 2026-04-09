from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sm_notify_new_login = fields.Boolean(
        string='Email Notification on New Login',
        config_parameter='sm_session_manager.notify_new_login',
        help='Send an email to the user whenever a new login session is detected.',
    )
    sm_auto_kill_mode = fields.Selection([
        ('none', 'None (Do not auto-kill)'),
        ('inactive', 'Inactive (Kill only when user is inactive)'),
        ('active', 'Active (Kill after duration regardless)'),
    ], string='Auto Kill Session Mode',
        config_parameter='sm_session_manager.auto_kill_mode',
        default='none',
        help='None: No auto kill.\n'
             'Inactive: Session killed only after user is inactive for the duration.\n'
             'Active: Session killed after the duration, even if user is active.',
    )
    sm_session_duration_hours = fields.Float(
        string='Session Duration (Hours)',
        config_parameter='sm_session_manager.session_duration_hours',
        default=24.0,
        help='Duration in hours after which sessions are auto-killed based on the mode.',
    )
    sm_cleanup_days = fields.Integer(
        string='Cleanup Old Sessions After (Days)',
        config_parameter='sm_session_manager.cleanup_days',
        default=90,
        help='Automatically delete session records older than this many days.',
    )
    sm_log_cleanup_days = fields.Integer(
        string='Cleanup Audit Logs After (Days)',
        config_parameter='sm_session_manager.log_cleanup_days',
        default=90,
        help='Automatically delete audit log records older than this many days.',
    )
    sm_track_operations = fields.Boolean(
        string='Track User Operations (Create/Write/Delete)',
        config_parameter='sm_session_manager.track_operations',
        default=True,
        help='Enable automatic tracking of create, write, and unlink operations.',
    )
