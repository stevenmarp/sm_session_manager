#!/usr/bin/env python3
"""
Test script for sm_session_manager module.
Tests all major flows: login tracking, audit logs, session kill, settings.
"""

import json
import sys
import time
import xmlrpc.client
import requests

URL = "http://localhost:8444"
DB = "uno_db_fresh"
USER = "admin"
PASS = "admin"

PASS_OK = False
results = []

def log(test_name, passed, detail=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append((test_name, passed, detail))
    print(f"  {status}: {test_name}")
    if detail:
        print(f"         {detail}")

def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ==============================================================
# TEST 1: Login via JSON-RPC (authenticate) + session tracking
# ==============================================================
separator("TEST 1: Login & Session Tracking")

session = requests.Session()
try:
    # Authenticate via JSON-RPC
    resp = session.post(f"{URL}/web/session/authenticate", json={
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "db": DB,
            "login": USER,
            "password": PASS,
        }
    }, headers={"Content-Type": "application/json"})
    data = resp.json()
    
    if "result" in data and data["result"].get("uid"):
        uid = data["result"]["uid"]
        log("JSON-RPC login", True, f"uid={uid}")
        PASS_OK = True
    elif "result" in data and data["result"].get("mfa"):
        log("JSON-RPC login", True, "MFA required (login works but MFA enabled)")
        uid = None
    else:
        log("JSON-RPC login", False, f"Response: {json.dumps(data, indent=2)[:300]}")
        uid = None
except Exception as e:
    log("JSON-RPC login", False, str(e))
    uid = None

# Trigger session tracking
if PASS_OK:
    try:
        resp2 = session.post(f"{URL}/web/session/sm_check_login", json={
            "jsonrpc": "2.0",
            "method": "call",
            "params": {}
        }, headers={"Content-Type": "application/json"})
        data2 = resp2.json()
        if "result" in data2 and data2["result"]:
            log("Session tracking endpoint", True, "Session tracked successfully")
        else:
            log("Session tracking endpoint", False, f"Response: {json.dumps(data2)[:200]}")
    except Exception as e:
        log("Session tracking endpoint", False, str(e))

# XML-RPC setup for further tests
common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

try:
    uid_rpc = common.authenticate(DB, USER, PASS, {})
    log("XML-RPC authenticate", True, f"uid={uid_rpc}")
except Exception as e:
    log("XML-RPC authenticate", False, str(e))
    uid_rpc = None
    
if not uid_rpc:
    print("\n❌ Cannot continue tests without authentication")
    sys.exit(1)

# Check session records
try:
    sessions = models.execute_kw(DB, uid_rpc, PASS, 'sm.user.session', 'search_read', 
        [[]], {'fields': ['user_id', 'session_id', 'ip_address', 'browser', 'operating_system', 'state', 'login_date'], 'limit': 5})
    if sessions:
        log("Session records exist", True, f"Found {len(sessions)} session(s)")
        for s in sessions[:3]:
            print(f"         Session: user={s['user_id']}, ip={s['ip_address']}, browser={s['browser']}, state={s['state']}")
    else:
        log("Session records exist", False, "No sessions found - tracking may not be working via JSON-RPC")
except Exception as e:
    log("Session records exist", False, str(e))


# ==============================================================
# TEST 2: Audit Log - CRUD Tracking
# ==============================================================
separator("TEST 2: Audit Log - CRUD Tracking")

# Count existing logs
try:
    log_count_before = models.execute_kw(DB, uid_rpc, PASS, 'sm.audit.log', 'search_count', [[]])
    log("Read audit log count", True, f"Current count: {log_count_before}")
except Exception as e:
    log("Read audit log count", False, str(e))
    log_count_before = 0

# CREATE test: create a partner
test_partner_id = None
try:
    test_partner_id = models.execute_kw(DB, uid_rpc, PASS, 'res.partner', 'create', [{'name': 'SM Test Partner Session Manager'}])
    log("Create test partner", True, f"partner_id={test_partner_id}")
except Exception as e:
    log("Create test partner", False, str(e))

time.sleep(1)

# Check if audit log was created
try:
    log_count_after_create = models.execute_kw(DB, uid_rpc, PASS, 'sm.audit.log', 'search_count', [[]])
    created = log_count_after_create > log_count_before
    log("Audit log for CREATE", created, f"Before: {log_count_before}, After: {log_count_after_create}")
except Exception as e:
    log("Audit log for CREATE", False, str(e))
    log_count_after_create = log_count_before

# WRITE test: update the partner
if test_partner_id:
    try:
        models.execute_kw(DB, uid_rpc, PASS, 'res.partner', 'write', [[test_partner_id], {'name': 'SM Test Partner UPDATED'}])
        log("Write test partner", True)
    except Exception as e:
        log("Write test partner", False, str(e))

    time.sleep(1)

    try:
        log_count_after_write = models.execute_kw(DB, uid_rpc, PASS, 'sm.audit.log', 'search_count', [[]])
        written = log_count_after_write > log_count_after_create
        log("Audit log for WRITE", written, f"Before: {log_count_after_create}, After: {log_count_after_write}")
    except Exception as e:
        log("Audit log for WRITE", False, str(e))
        log_count_after_write = log_count_after_create

# Check audit log details
try:
    recent_logs = models.execute_kw(DB, uid_rpc, PASS, 'sm.audit.log', 'search_read', 
        [[('model_name', '=', 'res.partner')]], 
        {'fields': ['user_id', 'operation', 'model_name', 'res_name', 'field_changes', 'timestamp'], 'limit': 5, 'order': 'id desc'})
    if recent_logs:
        log("Audit log detail content", True, f"Found {len(recent_logs)} partner log(s)")
        for l in recent_logs[:3]:
            fc = l.get('field_changes') or ''
            print(f"         Log: op={l['operation']}, model={l['model_name']}, record={l['res_name']}, fields={fc[:80]}")
    else:
        log("Audit log detail content", False, "No partner audit logs found")
except Exception as e:
    log("Audit log detail content", False, str(e))

# UNLINK test: delete the partner
if test_partner_id:
    try:
        log_count_before_unlink = models.execute_kw(DB, uid_rpc, PASS, 'sm.audit.log', 'search_count', [[]])
        models.execute_kw(DB, uid_rpc, PASS, 'res.partner', 'unlink', [[test_partner_id]])
        log("Unlink test partner", True)
        time.sleep(1)
        log_count_after_unlink = models.execute_kw(DB, uid_rpc, PASS, 'sm.audit.log', 'search_count', [[]])
        unlinked = log_count_after_unlink > log_count_before_unlink
        log("Audit log for UNLINK", unlinked, f"Before: {log_count_before_unlink}, After: {log_count_after_unlink}")
    except Exception as e:
        log("Unlink test partner", False, str(e))


# ==============================================================
# TEST 3: Session Kill
# ==============================================================
separator("TEST 3: Session Kill")

try:
    active_sessions = models.execute_kw(DB, uid_rpc, PASS, 'sm.user.session', 'search_read', 
        [[('state', '=', 'active')]], {'fields': ['id', 'user_id', 'state', 'session_id'], 'limit': 5})
    if active_sessions:
        log("Find active sessions", True, f"Found {len(active_sessions)} active session(s)")
        
        # Test kill via action_kill_session (we'll kill the first non-current one if possible, 
        # or just test the method exists)
        test_session = active_sessions[0]
        try:
            # Verify the action exists and can be called
            result = models.execute_kw(DB, uid_rpc, PASS, 'sm.user.session', 'action_kill_session', [[test_session['id']]])
            log("Kill session action", True, f"Killed session id={test_session['id']}")
            
            # Verify session state changed
            killed_session = models.execute_kw(DB, uid_rpc, PASS, 'sm.user.session', 'read', [[test_session['id']]], {'fields': ['state', 'logout_date']})
            if killed_session and killed_session[0]['state'] == 'killed':
                log("Session state after kill", True, f"state={killed_session[0]['state']}, logout_date={killed_session[0]['logout_date']}")
            else:
                log("Session state after kill", False, f"Unexpected state: {killed_session}")
        except Exception as e:
            log("Kill session action", False, str(e))
    else:
        log("Find active sessions", False, "No active sessions found to test kill")
except Exception as e:
    log("Find active sessions", False, str(e))


# ==============================================================
# TEST 4: Settings / Config
# ==============================================================
separator("TEST 4: Settings & Configuration")

# Test reading config parameters
try:
    # Check ICP values
    params_to_check = [
        'sm_session_manager.notify_new_login',
        'sm_session_manager.auto_kill_mode', 
        'sm_session_manager.session_duration_hours',
        'sm_session_manager.cleanup_days',
        'sm_session_manager.log_cleanup_days',
        'sm_session_manager.track_operations',
    ]
    for param in params_to_check:
        val = models.execute_kw(DB, uid_rpc, PASS, 'ir.config_parameter', 'search_read', 
            [[('key', '=', param)]], {'fields': ['key', 'value']})
        if val:
            print(f"         Config: {param} = {val[0]['value']}")
    log("Config parameters accessible", True)
except Exception as e:
    log("Config parameters accessible", False, str(e))

# Test views load
try:
    # Session list view
    views = models.execute_kw(DB, uid_rpc, PASS, 'ir.ui.view', 'search_read', 
        [[('model', '=', 'sm.user.session')]], {'fields': ['name', 'type']})
    view_types = [v['type'] for v in views]
    log("Session views registered", True, f"Types: {view_types}")
except Exception as e:
    log("Session views registered", False, str(e))

try:
    # Audit log views
    views = models.execute_kw(DB, uid_rpc, PASS, 'ir.ui.view', 'search_read', 
        [[('model', '=', 'sm.audit.log')]], {'fields': ['name', 'type']})
    view_types = [v['type'] for v in views]
    log("Audit log views registered", True, f"Types: {view_types}")
except Exception as e:
    log("Audit log views registered", False, str(e))

# Test menus exist
try:
    menus = models.execute_kw(DB, uid_rpc, PASS, 'ir.ui.menu', 'search_read', 
        [[('name', 'ilike', 'session manager')]], {'fields': ['name', 'complete_name']})
    if menus:
        log("Menu items exist", True, f"Found {len(menus)} menu(s)")
        for m in menus:
            print(f"         Menu: {m['complete_name']}")
    else:
        log("Menu items exist", False, "No menus found")
except Exception as e:
    log("Menu items exist", False, str(e))

# Test crons exist
try:
    crons = models.execute_kw(DB, uid_rpc, PASS, 'ir.cron', 'search_read', 
        [[('name', 'ilike', 'Session Manager')]], {'fields': ['name', 'active', 'interval_number', 'interval_type']})
    if crons:
        log("Cron jobs exist", True, f"Found {len(crons)} cron(s)")
        for c in crons:
            print(f"         Cron: {c['name']} (active={c['active']}, every {c['interval_number']} {c['interval_type']})")
    else:
        log("Cron jobs exist", False, "No crons found")
except Exception as e:
    log("Cron jobs exist", False, str(e))

# Test security groups
try:
    groups = models.execute_kw(DB, uid_rpc, PASS, 'res.groups', 'search_read', 
        [[('category_id.name', '=', 'Session Manager')]], {'fields': ['name', 'full_name']})
    if groups:
        log("Security groups exist", True, f"Found {len(groups)} group(s)")
        for g in groups:
            print(f"         Group: {g['full_name']}")
    else:
        log("Security groups exist", False, "No groups found")
except Exception as e:
    log("Security groups exist", False, str(e))


# ==============================================================
# TEST 5: Web pages load (basic HTTP checks)
# ==============================================================
separator("TEST 5: Web Page Load Tests")

web_session = requests.Session()
# Login first
web_session.post(f"{URL}/web/session/authenticate", json={
    "jsonrpc": "2.0", "method": "call",
    "params": {"db": DB, "login": USER, "password": PASS}
}, headers={"Content-Type": "application/json"})

# Test action loads
for action_name, path in [
    ("Session list", "/odoo/session-manager"),
]:
    try:
        resp = web_session.get(f"{URL}{path}", allow_redirects=True)
        log(f"Page load: {action_name}", resp.status_code == 200, f"HTTP {resp.status_code}")
    except Exception as e:
        log(f"Page load: {action_name}", False, str(e))


# ==============================================================
# SUMMARY
# ==============================================================
separator("TEST SUMMARY")

passed = sum(1 for _, p, _ in results if p)
failed = sum(1 for _, p, _ in results if not p)
total = len(results)

print(f"\n  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
if failed:
    print(f"\n  Failed tests:")
    for name, p, detail in results:
        if not p:
            print(f"    ❌ {name}: {detail}")
print(f"\n{'='*60}")

# Cleanup: nothing to clean, test partner already deleted

sys.exit(0 if failed == 0 else 1)
