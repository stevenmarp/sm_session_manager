{
    'name': 'Session Manager & User Audit',
    'version': '18.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Track user sessions, audit activities, manage login security & get notified on new logins',
    'description': """
Session Manager & User Audit
=============================
Track every user's activities, operations & sessions.

Features:
- Session tracking with IP, browser, OS, device info
- User activity audit (create, write, unlink operations)
- Kill/force logout any active session
- Email notification on new login
- Auto session expiry (active/inactive modes)
- Auto cleanup old audit logs
- GeoIP location tracking
- Access rights: User vs Manager
    """,
    'author': 'Steven Marp',
    'website': 'https://apps.odoo.com/apps/modules/browse?repo_maintainer_id=512936',
    'license': 'LGPL-3',
    'depends': ['base', 'base_setup', 'mail'],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'data/mail_template_data.xml',
        'views/session_views.xml',
        'views/audit_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'external_dependencies': {
        'python': ['user_agents'],
    },
    'assets': {
        'web.assets_backend': [
            'sm_session_manager/static/src/js/session_tracker.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/banner.gif'],
    'price': 178.92,
    'currency': 'USD',
}
