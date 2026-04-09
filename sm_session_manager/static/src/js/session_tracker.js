/** @odoo-module **/

import { session } from "@web/session";
import { rpc } from "@web/core/network/rpc";

// Track session once after page load when user is logged in
if (session.uid) {
    rpc("/web/session/sm_check_login", {}).catch(() => {});
}
