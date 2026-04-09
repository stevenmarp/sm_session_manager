import json
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Models that should never be tracked to avoid noise/recursion
SKIP_MODELS = {
    'sm.audit.log', 'sm.user.session',
    'ir.logging', 'ir.cron', 'ir.cron.trigger',
    'bus.bus', 'bus.presence',
    'ir.attachment', 'ir.config_parameter',
    'mail.message', 'mail.mail', 'mail.notification',
    'mail.channel', 'mail.followers',
    'fetchmail.server',
    'base.automation',
    'ir.model.data', 'ir.ui.view', 'ir.translation',
    'res.config.settings',
    'ir.property', 'ir.sequence',
    'ir.autovacuum',
}


class BaseModelExtend(models.AbstractModel):
    _inherit = 'base'

    def _sm_should_track(self):
        """Check if this model should be tracked."""
        if self._name in SKIP_MODELS:
            return False
        if self._transient:
            return False
        # Check if tracking is enabled
        try:
            ICP = self.env['ir.config_parameter'].sudo()
            return ICP.get_param('sm_session_manager.track_operations', 'True') == 'True'
        except Exception:
            return False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._sm_should_track():
            try:
                self.env['sm.audit.log'].log_activity(
                    operation='create',
                    model_name=self._name,
                    res_ids=records.ids,
                )
            except Exception as e:
                _logger.debug("Audit log create failed: %s", e)
        return records

    def write(self, vals):
        if self._sm_should_track() and vals:
            try:
                # Capture changed field names (not values for security)
                changed_fields = list(vals.keys())
                # Filter out computed/internal fields
                changed_fields = [f for f in changed_fields if f in self._fields and not self._fields[f].compute]
                if changed_fields:
                    field_info = json.dumps({'changed_fields': changed_fields}, default=str)
                    res_ids = self.ids
                else:
                    field_info = None
                    res_ids = None
            except Exception:
                field_info = None
                res_ids = None
        else:
            field_info = None
            res_ids = None

        result = super().write(vals)

        if field_info and res_ids:
            try:
                self.env['sm.audit.log'].log_activity(
                    operation='write',
                    model_name=self._name,
                    res_ids=res_ids,
                    field_changes=field_info,
                )
            except Exception as e:
                _logger.debug("Audit log write failed: %s", e)
        return result

    def unlink(self):
        if self._sm_should_track():
            try:
                res_ids = self.ids
                model_name = self._name
                # Get names before deletion
                names = {}
                for rec in self:
                    try:
                        names[rec.id] = rec.display_name or str(rec.id)
                    except Exception:
                        names[rec.id] = str(rec.id)
            except Exception:
                res_ids = None
                model_name = None
                names = {}
        else:
            res_ids = None
            model_name = None
            names = {}

        result = super().unlink()

        if res_ids and model_name:
            try:
                field_info = json.dumps({'deleted_records': names}, default=str) if names else None
                self.env['sm.audit.log'].log_activity(
                    operation='unlink',
                    model_name=model_name,
                    res_ids=res_ids,
                    field_changes=field_info,
                )
            except Exception as e:
                _logger.debug("Audit log unlink failed: %s", e)
        return result
