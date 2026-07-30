import time
import json
import os
import csv
import threading
import math
import urllib.request
import urllib.error
from datetime import datetime, time as dt_time, timedelta
from gpiozero import Button, OutputDevice

try:
    from flask import Flask, jsonify, request
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("WARNING: Flask not installed.")

print("Initializing EMS System...")
time.sleep(3)

try:
    from RPLCD.i2c import CharLCD
    lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2, dotsize=8)
    LCD_CONNECTED = True
except Exception:
    LCD_CONNECTED = False
    print("WARNING: LCD NOT found.")

DATA_FILE = "/home/daulat123/ems_state.json"
LOG_FILE  = "/home/daulat123/ems_log.csv"
LCD_CYCLE_TIME_NORMAL = 5.0
LCD_CYCLE_TIME = LCD_CYCLE_TIME_NORMAL

RENDER_SERVER_URL = "https://your-future-app-name.onrender.com/ping"
DEFAULT_API_KEY = "change_this_to_a_long_random_password_12345"

SOCIETY_ID = "GP001"
SERVER_PUSH_URL = "https://your-udyogconnect-server.com/api/pi/sync"
FIRMWARE_VERSION = "2.1.0"
BOOT_TIME = time.time()

last_hardware_action_time = 0
HARDWARE_COOLDOWN_SECONDS = 5
last_cloud_error_log_time = 0
MAX_LOCAL_LOG_LINES = 10000

current_api_key = DEFAULT_API_KEY
custom_lcd_lines = None
custom_lcd_expire = 0

emergency_stop_active = False
last_24h_log_date = ""

MAX_WINGS_ALLOWED = 10
MAX_EVENT_QUEUE_SIZE = 100

quota_lock_until = 0
reset_day_lock_until = 0
pending_new_days = {}
pending_cycle_start = False
boot_count = 0
last_shutdown_reason = "UNKNOWN"
last_cloud_sync_time = "1970-01-01T00:00:00"

event_queue = []
next_event_id = 0

cpu_temp_state = "NORMAL"
overheat_timer = 0

cloud_push_event = threading.Event()

def get_current_now():
    return datetime.now()

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return 0.0

def get_clock_source():
    try:
        if os.path.exists("/run/systemd/timesync/synchronized"):
            with open("/run/systemd/timesync/synchronized", "r") as f:
                if f.read().strip() == "yes": return "NTP"
    except Exception: pass
    return "UNKNOWN"

WING_CONFIG = {
    'A': {'name': 'Wing A', 'relay_pin': 17, 'toggle_pin':  5,  'target_days': 9,  'daily_units': 5.0},
    'B': {'name': 'Wing B', 'relay_pin': 27, 'toggle_pin':  6,  'target_days': 12, 'daily_units': 5.0},
    'C': {'name': 'Wing C', 'relay_pin': 23, 'toggle_pin': 13,  'target_days': 10, 'daily_units': 5.0},
    'D': {'name': 'Wing D', 'relay_pin': 25, 'toggle_pin': 12,  'target_days': 0,  'daily_units': 5.0},
    'E': {'name': 'Wing E', 'relay_pin': 8,  'toggle_pin': 20,  'target_days': 0,  'daily_units': 5.0},
    'F': {'name': 'Wing F', 'relay_pin': 7,  'toggle_pin': 16,  'target_days': 0,  'daily_units': 5.0},
    'G': {'name': 'Wing G', 'relay_pin': 10, 'toggle_pin': 19,  'target_days': 0,  'daily_units': 5.0},
    'H': {'name': 'Wing H', 'relay_pin': 9,  'toggle_pin': 26,  'target_days': 0,  'daily_units': 5.0},
    'I': {'name': 'Wing I', 'relay_pin': 22, 'toggle_pin': 21,  'target_days': 0,  'daily_units': 5.0},
    'J': {'name': 'Wing J', 'relay_pin': 11, 'toggle_pin': 18,  'target_days': 0,  'daily_units': 5.0}
}
WING_ORDER = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']

if len(WING_CONFIG) > MAX_WINGS_ALLOWED:
    print(f"!!! FATAL ERROR: {len(WING_CONFIG)} wings configured. Max allowed is {MAX_WINGS_ALLOWED}. System halting.")
    exit(1)

wings = {}
for wid, cfg in WING_CONFIG.items():
    wings[wid] = {
        'name': cfg['name'], 'display_name': cfg['name'], 'disabled': False,
        'used_days': 0, 'target_days': cfg['target_days'], 'daily_units': cfg['daily_units'],
        'relay': OutputDevice(cfg['relay_pin'], active_high=False, initial_value=False),
        'toggle': Button(cfg['toggle_pin'], pull_up=False, bounce_time=0.5),
        'is_active': False, 'prev_toggle_state': False, 'remote_block_until': 0,
        'relay_clicks': 0
    }

PHYSICAL_ESTOP_PIN = 24
physical_estop_btn = Button(PHYSICAL_ESTOP_PIN, pull_up=True, bounce_time=0.2)

def trigger_physical_estop():
    global active_wing_id, emergency_stop_active, last_shutdown_reason
    if not emergency_stop_active:
        emergency_stop_active = True
        for w in wings.values(): w['relay'].off(); w['is_active'] = False
        active_wing_id = None
        log_event("!!! PHYSICAL E-STOP PRESSED !!!", "ERROR")
        save_state(push_cloud=True)

physical_estop_btn.when_pressed = trigger_physical_estop

def log_event(event_msg, level="INFO"):
    global next_event_id
    now = get_current_now()
    try:
        file_exists = os.path.exists(LOG_FILE)
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists: writer.writerow(['Date', 'Time', 'Level', 'Event'])
            writer.writerow([now.strftime("%d-%m-%Y"), now.strftime("%H:%M"), level, event_msg])
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f: lines = f.readlines()
            if len(lines) > MAX_LOCAL_LOG_LINES:
                with open(LOG_FILE, 'w') as f: f.writelines(lines[-5000:])
    except Exception: pass
    event_queue.append({"id": next_event_id, "ts": now.isoformat(), "level": level, "msg": event_msg})
    next_event_id += 1
    if len(event_queue) > MAX_EVENT_QUEUE_SIZE: event_queue.pop(0)

def is_wing_toggled_on(wid): return wings[wid]['toggle'].is_pressed
def get_wing_status(wid): return "ON" if is_wing_toggled_on(wid) else "OFF"

def is_wing_eligible(wid):
    if wings[wid]['disabled']: return False
    if not is_wing_toggled_on(wid): return False
    if wings[wid]['used_days'] >= wings[wid]['target_days']: return False
    if time.time() < wings[wid]['remote_block_until']: return False
    return True

def is_quota_locked(): return time.time() < quota_lock_until
def is_reset_day_locked(): return time.time() < reset_day_lock_until

def load_state():
    global active_wing_id, last_assigned_wing, today_assigned_wing, last_counted_date, last_reset_month
    global current_api_key, last_24h_log_date, reset_day, quota_lock_until, reset_day_lock_until
    global pending_cycle_start, pending_new_days, boot_count, last_shutdown_reason, next_event_id, last_cloud_sync_time

    active_wing_id = None; today_assigned_wing = None; last_assigned_wing = WING_ORDER[-1]
    last_counted_date = get_current_now().strftime("%Y-%m-%d"); last_reset_month = -1
    reset_day = 22; quota_lock_until = 0; reset_day_lock_until = 0
    pending_cycle_start = False; pending_new_days = {}
    boot_count = 0; last_shutdown_reason = "UNKNOWN"; next_event_id = 0; last_cloud_sync_time = "1970-01-01T00:00:00"

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                current_api_key = data.get('api_key', DEFAULT_API_KEY)
                reset_day = data.get('reset_day', 22)
                quota_lock_until = data.get('quota_lock_until', 0)
                reset_day_lock_until = data.get('reset_day_lock_until', 0)
                pending_cycle_start = data.get('pending_cycle_start', False)
                pending_new_days = data.get('pending_new_days', {})
                boot_count = data.get('bootCount', 0)
                last_shutdown_reason = data.get('lastShutdownReason', "UNKNOWN")
                next_event_id = data.get('nextEventId', 0)
                last_cloud_sync_time = data.get('lastCloudSync', "1970-01-01T00:00:00")
                for wid in wings:
                    if wid in data:
                        wings[wid]['used_days'] = data[wid].get('used_days', 0)
                        wings[wid]['target_days'] = data[wid].get('target_days', WING_CONFIG[wid]['target_days'])
                        wings[wid]['daily_units'] = data[wid].get('daily_units', WING_CONFIG[wid]['daily_units'])
                        wings[wid]['disabled'] = data[wid].get('disabled', False)
                        wings[wid]['display_name'] = data[wid].get('display_name', WING_CONFIG[wid]['name'])
                        wings[wid]['relay_clicks'] = data[wid].get('relay_clicks', 0)
                last_counted_date = data.get('last_counted_date', last_counted_date)
                last_assigned_wing = data.get('last_assigned_wing', last_assigned_wing)
                active_wing_id = data.get('active_wing_id', None)
                today_assigned_wing = data.get('today_assigned_wing', None)
                last_reset_month = data.get('last_reset_month', -1)
                last_24h_log_date = data.get('last_24h_log_date', last_counted_date)
                for wid in wings: wings[wid]['prev_toggle_state'] = is_wing_toggled_on(wid)
        except Exception as e: log_event(f"STATE FILE ERROR: {e}", "ERROR")

def save_state(push_cloud=False):
    data = {
        'api_key': current_api_key, 'last_24h_log_date': last_24h_log_date, 'reset_day': reset_day,
        'quota_lock_until': quota_lock_until, 'reset_day_lock_until': reset_day_lock_until,
        'pending_cycle_start': pending_cycle_start, 'pending_new_days': pending_new_days,
        'bootCount': boot_count, 'lastShutdownReason': last_shutdown_reason, 'firmwareVersion': FIRMWARE_VERSION,
        'nextEventId': next_event_id, 'lastCloudSync': last_cloud_sync_time
    }
    for wid, w in wings.items():
        data[wid] = {
            'used_days': w['used_days'], 'target_days': w['target_days'], 'daily_units': w['daily_units'],
            'disabled': w['disabled'], 'display_name': w['display_name'], 'relay_clicks': w['relay_clicks']
        }
    data['last_counted_date'] = last_counted_date
    data['active_wing_id'] = active_wing_id
    data['today_assigned_wing'] = today_assigned_wing
    data['last_assigned_wing'] = last_assigned_wing
    data['last_reset_month'] = last_reset_month
    temp_file = DATA_FILE + ".tmp"
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, DATA_FILE)
    except Exception as e:
        log_event(f"STATE SAVE ERROR: {e}", "ERROR")
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass
    if push_cloud: cloud_push_event.set()

def get_next_eligible_wing(failed_wing_id=None):
    start_idx = WING_ORDER.index(failed_wing_id) if failed_wing_id and failed_wing_id in WING_ORDER else -1
    for i in range(1, len(WING_ORDER) + 1):
        wid = WING_ORDER[(start_idx + i) % len(WING_ORDER)]
        if is_wing_eligible(wid): return wid
    return None

def switch_wing(target_wid, source="system"):
    global active_wing_id, last_assigned_wing, today_assigned_wing, last_hardware_action_time
    if source not in ["system", "monthly_reset", "health_check", "startup_recovery", "auto_cycle_reset", "cloud_command"] and time.time() - last_hardware_action_time < HARDWARE_COOLDOWN_SECONDS:
        log_event(f"BLOCKED RAPID CLICK on Wing {target_wid}", "WARNING"); return
    for w in wings.values(): w['relay'].off(); w['is_active'] = False
    if target_wid == active_wing_id: return
    time.sleep(1.0)
    if target_wid and is_wing_eligible(target_wid):
        wings[target_wid]['relay'].on(); wings[target_wid]['is_active'] = True
        wings[target_wid]['relay_clicks'] += 1
        active_wing_id = target_wid; last_assigned_wing = target_wid; today_assigned_wing = target_wid
        log_event(f"{wings[target_wid]['display_name']} ACTIVATED [{source.upper()}]")
        if source not in ["system", "monthly_reset", "health_check", "startup_recovery", "auto_cycle_reset", "cloud_command"]:
            last_hardware_action_time = time.time()
    else:
        active_wing_id = None; today_assigned_wing = None
        if target_wid: log_event(f"Wing {target_wid} SWITCH DENIED", "WARNING")
    save_state(push_cloud=True)

def recover_after_reboot():
    global active_wing_id
    for w in wings.values(): w['relay'].off(); w['is_active'] = False
    if active_wing_id and active_wing_id in WING_ORDER and is_wing_eligible(active_wing_id):
        wings[active_wing_id]['relay'].on(); wings[active_wing_id]['is_active'] = True
        log_event(f"Reboot Recovery - {wings[active_wing_id]['display_name']} Restored")
    elif active_wing_id is not None:
        log_event("Reboot - Stale State Cleared", "WARNING")
        active_wing_id = None
    save_state(push_cloud=True)

def get_time_str(): return get_current_now().strftime("%H:%M")

def update_lcd(lines):
    if LCD_CONNECTED:
        lcd.clear()
        lcd.cursor_pos = (0, 0); lcd.write_string(lines[0].ljust(16))
        lcd.cursor_pos = (1, 0); lcd.write_string(lines[1].ljust(16))

def update_lcd_emergency(): update_lcd(["SYSTEM PAUSED", "ALL OFF/FULL"])
def update_lcd_estop():
    if int(time.time()) % 2 == 0: update_lcd(["!!! E-STOP !!!", "SYSTEM LOCKED"])
    else: update_lcd(["AWAITING RESTART", "REMOTE COMMAND"])

def update_lcd_status(screen_idx):
    now = get_current_now()
    if screen_idx < len(WING_ORDER):
        wid = WING_ORDER[screen_idx]; w = wings[wid]
        if w['disabled']: tag = "DIS"
        elif w['used_days'] >= w['target_days']: tag = "FULL"
        elif active_wing_id == wid: tag = "ACT"
        elif is_wing_toggled_on(wid): tag = "ON "
        else: tag = "OFF"
        name_str = w['display_name'][:12]
        line1 = f"{name_str:<12}{tag}"
        line2 = f" {w['used_days']}/{w['target_days']}d  Nxt:{reset_day}th"
        update_lcd([line1, line2])
    else: update_lcd([f"{now.strftime('%d-%m-%Y')}", "Time:     " + get_time_str()])

# ===================================================================
# FLASK API - ALL ENDPOINTS ALIGNED WITH CLOUD BACKEND + DASHBOARD
# ===================================================================
if FLASK_AVAILABLE:
    app = Flask(__name__)
    def is_authorized(): return request.args.get('key') == current_api_key

    @app.route('/status')
    def api_status():
        status_data = {}
        for wid, w in wings.items():
            status_data[wid] = {
                "name": w['name'],
                "display_name": w['display_name'],
                "disabled": w['disabled'],
                "used_days": w['used_days'],
                "target_days": w['target_days'],
                "is_active": w['is_active'],
                "meter_toggle": get_wing_status(wid),
                "relay_clicks": w['relay_clicks']
            }
        status_data["system_active_wing"] = active_wing_id
        status_data["emergency_stop"] = emergency_stop_active
        status_data["reset_day"] = reset_day
        status_data["pending_start"] = pending_cycle_start
        status_data["locked"] = is_quota_locked()
        # NEW: Fields dashboard V2.1.0 reads
        status_data["system_quota_lock_until"] = datetime.fromtimestamp(quota_lock_until).isoformat() if quota_lock_until > 0 else ""
        status_data["system_reset_day_lock_until"] = datetime.fromtimestamp(reset_day_lock_until).isoformat() if reset_day_lock_until > 0 else ""
        status_data["system_watchdog_enabled"] = True
        status_data["system_firmware_version"] = FIRMWARE_VERSION
        status_data["system_uptime_seconds"] = int(time.time() - BOOT_TIME)
        status_data["system_boot_count"] = boot_count
        status_data["system_last_reboot_reason"] = last_shutdown_reason
        return jsonify(status_data)

    @app.route('/logs')
    def api_logs():
        logs = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f: reader = csv.reader(f); next(reader, None); logs = list(reader)[-50:]
        return jsonify(logs)

    @app.route('/control/estop')
    def api_emergency_stop():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        trigger_physical_estop()
        return jsonify({"success": True, "message": "EMERGENCY STOP ACTIVATED."})

    @app.route('/control/restart_system')
    def api_restart_system():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global emergency_stop_active
        if not emergency_stop_active: return jsonify({"success": False, "message": "System is not in E-Stop mode."}), 400
        emergency_stop_active = False; log_event("SYSTEM RESTARTED FROM E-STOP"); recover_after_reboot()
        return jsonify({"success": True, "message": "SYSTEM RESTARTED."})

    @app.route('/control/force_on')
    def api_force_on():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        if emergency_stop_active: return jsonify({"success": False, "message": "System in E-Stop."}), 403
        if last_assigned_wing and is_wing_eligible(last_assigned_wing):
            switch_wing(last_assigned_wing, source="remote_force_on"); return jsonify({"success": True, "message": f"Force ON: Wing {last_assigned_wing}"})
        next_wing = get_next_eligible_wing()
        if next_wing: switch_wing(next_wing, source="remote_force_on"); return jsonify({"success": True, "message": f"Force ON: Wing {next_wing}"})
        return jsonify({"success": False, "message": "Force ON failed."}), 400

    @app.route('/control/reset')
    def api_force_reset():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        if is_quota_locked(): return jsonify({"success": False, "message": "System is locked."}), 403
        global active_wing_id
        log_event("MANUAL REMOTE RESET TRIGGERED")
        for w in wings.values(): w['used_days'] = 0; w['remote_block_until'] = 0
        active_wing_id = None; save_state(push_cloud=True)
        return jsonify({"success": True, "message": "All wings reset to 0 days."})

    @app.route('/control/switch/<wing_id>')
    def api_force_switch(wing_id):
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        if emergency_stop_active: return jsonify({"success": False, "message": "System in E-Stop."}), 403
        if wing_id in WING_ORDER:
            wings[wing_id]['remote_block_until'] = 0; switch_wing(wing_id, source="remote_web")
            return jsonify({"success": True, "message": f"Switched to Wing {wing_id}"})
        return jsonify({"success": False, "message": "Invalid Wing ID"}), 400

    @app.route('/control/off/<wing_id>')
    def api_force_off(wing_id):
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global active_wing_id
        if wing_id in WING_ORDER:
            wings[wing_id]['remote_block_until'] = time.time() + 300
            if active_wing_id == wing_id:
                wings[wing_id]['relay'].off(); wings[wing_id]['is_active'] = False; active_wing_id = None
                log_event(f"Wing {wing_id} REMOTE TURN OFF"); save_state(push_cloud=True)
                return jsonify({"success": True, "message": f"Wing {wing_id} turned off."})
            return jsonify({"success": True, "message": f"Wing {wing_id} blocked."})
        return jsonify({"success": False, "message": "Invalid Wing ID"}), 400

    @app.route('/control/off_all')
    def api_force_off_all():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global active_wing_id
        for w in wings.values(): w['relay'].off(); w['is_active'] = False; w['remote_block_until'] = time.time() + 300
        if active_wing_id: log_event("ALL WINGS REMOTE TURN OFF")
        active_wing_id = None; save_state(push_cloud=True)
        return jsonify({"success": True, "message": "All wings turned off."})

    @app.route('/control/reboot_device')
    def api_reboot_device():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global last_shutdown_reason
        log_event("MANUAL REMOTE REBOOT INITIATED", "WARNING")
        last_shutdown_reason = "USER_COMMAND"; save_state()
        time.sleep(2); os.system("sudo reboot")
        return jsonify({"success": True, "message": "Rebooting Pi..."})

    @app.route('/config/toggle_disable/<wing_id>')
    def api_toggle_disable(wing_id):
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global active_wing_id
        if wing_id in WING_ORDER:
            wings[wing_id]['disabled'] = not wings[wing_id]['disabled']
            state_str = "DISABLED" if wings[wing_id]['disabled'] else "ENABLED"
            if wings[wing_id]['disabled'] and active_wing_id == wing_id:
                wings[wing_id]['relay'].off(); wings[wing_id]['is_active'] = False; active_wing_id = None
            log_event(f"Wing {wing_id} ({wings[wing_id]['display_name']}) {state_str}")
            save_state(push_cloud=True)
            return jsonify({"success": True, "message": f"Wing {wing_id} {state_str}.", "disabled": wings[wing_id]['disabled']})
        return jsonify({"success": False, "message": "Invalid Wing ID"}), 400

    @app.route('/config/set_display_name/<wing_id>')
    def api_set_display_name(wing_id):
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        if wing_id in WING_ORDER:
            new_name = request.args.get('name', '').strip()[:12]
            if new_name:
                old_name = wings[wing_id]['display_name']
                wings[wing_id]['display_name'] = new_name
                log_event(f"Wing {wing_id} RENAMED: {old_name} -> {new_name}")
                save_state(push_cloud=True)
                return jsonify({"success": True, "message": f"Renamed to {new_name}"})
            return jsonify({"success": False, "message": "Name cannot be empty."}), 400
        return jsonify({"success": False, "message": "Invalid Wing ID"}), 400

    @app.route('/config/days')
    def api_set_days():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        if is_quota_locked(): return jsonify({"success": False, "message": "System LOCKED. Use /config/set_monthly_quota"}), 403
        try:
            new_days = {wid: max(0, int(request.args.get(wid, wings[wid]['target_days']))) for wid in WING_ORDER}
            for wid, days in new_days.items(): wings[wid]['target_days'] = days
            log_event(f"CONFIG DAYS: {new_days}"); save_state(push_cloud=True)
            return jsonify({"success": True, "message": f"Days updated: {new_days}", "days": new_days})
        except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

    # ===================================================================
    # KEY ENDPOINT: set_monthly_quota - Pi calculates, returns format
    # that dashboard V2.1.0 expects: {avg_daily, results: {wid: {units, days, formula, skipped}}}
    # ===================================================================
    @app.route('/config/set_monthly_quota')
    def api_set_monthly_quota():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global quota_lock_until, pending_cycle_start, pending_new_days
        try:
            total_units = float(request.args.get('total_units', 0))
            total_days = float(request.args.get('total_days', 30))
            wing_units = {wid: float(request.args.get(wid, 0)) for wid in WING_ORDER}
            if total_units <= 0 or total_days <= 0:
                return jsonify({"success": False, "message": "Total units/days must be > 0"}), 400

            building_daily_avg = total_units / total_days

            # Build results in the format dashboard expects
            results = {}
            for wid, units in wing_units.items():
                if wings[wid]['disabled'] or units <= 0:
                    calc_days_val = 0
                    results[wid] = {"units": units, "days": 0, "formula": f"{units} / {building_daily_avg:.2f}", "skipped": True, "reason": "disabled" if wings[wid]['disabled'] else "zero_units"}
                else:
                    calc_days_val = max(1, math.floor(units / building_daily_avg))
                    results[wid] = {"units": units, "days": calc_days_val, "formula": f"{units} / {building_daily_avg:.2f} = {calc_days_val}", "skipped": False}

            calc_days_map = {wid: r["days"] for wid, r in results.items()}

            # Lock quota for 30 days
            quota_lock_until = time.time() + 2592000

            now = get_current_now()
            if now.day < reset_day:
                pending_new_days = calc_days_map; pending_cycle_start = True
                log_event(f"QUOTA BUFFERED. Starts {reset_day}th. Days: {calc_days_map}.", "WARNING")
            else:
                pending_new_days = {}; pending_cycle_start = False
                for wid, days in calc_days_map.items():
                    wings[wid]['target_days'] = days; wings[wid]['used_days'] = 0; wings[wid]['remote_block_until'] = 0
                log_event(f"QUOTA APPLIED NOW. Days: {calc_days_map}.")

            save_state(push_cloud=True)

            # Return in the EXACT format dashboard V2.1.0 parses
            return jsonify({
                "success": True,
                "avg_daily": round(building_daily_avg, 2),
                "results": results,
                "message": f"Quota locked. Days: {calc_days_map}",
                "buffered": pending_cycle_start
            })
        except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

    # ===================================================================
    # NEW: lock_quota - Called by dashboard "Lock 30 Days" button
    # ===================================================================
    @app.route('/config/lock_quota')
    def api_lock_quota():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global quota_lock_until
        try:
            duration = int(request.args.get('days', 30))
            quota_lock_until = time.time() + (duration * 86400)
            lock_iso = datetime.fromtimestamp(quota_lock_until).isoformat()
            log_event(f"QUOTA LOCKED for {duration} days until {lock_iso}", "WARNING")
            save_state(push_cloud=True)
            return jsonify({"success": True, "locked_until": lock_iso, "duration_days": duration})
        except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

    # ===================================================================
    # NEW: unlock_quota - Called by dashboard "Unlock" button
    # ===================================================================
    @app.route('/config/unlock_quota')
    def api_unlock_quota():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global quota_lock_until
        was_locked = is_quota_locked()
        quota_lock_until = 0
        log_event(f"QUOTA UNLOCKED (was_locked={was_locked})", "WARNING")
        save_state(push_cloud=True)
        return jsonify({"success": True, "was_locked": was_locked})

    # ===================================================================
    # UPDATED: set_reset_day - NOW AUTO-LOCKS for 30 days
    # ===================================================================
    @app.route('/config/set_reset_day')
    def api_set_reset_day():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global reset_day, reset_day_lock_until
        try:
            if is_reset_day_locked():
                lock_iso = datetime.fromtimestamp(reset_day_lock_until).isoformat()
                return jsonify({"success": False, "message": f"Reset day locked until {lock_iso}", "locked_until": lock_iso}), 403
            day = int(request.args.get('day', reset_day))
            if 1 <= day <= 28:
                old_day = reset_day
                reset_day = day
                # AUTO-LOCK for 30 days
                reset_day_lock_until = time.time() + 2592000
                lock_iso = datetime.fromtimestamp(reset_day_lock_until).isoformat()
                log_event(f"RESET DAY changed: {old_day} -> {day}, LOCKED until {lock_iso}", "WARNING")
                save_state(push_cloud=True)
                return jsonify({"success": True, "message": f"Reset day set to {day}th", "reset_day": day, "locked_until": lock_iso})
            return jsonify({"success": False, "message": "Day must be 1-28"}), 400
        except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

    # ===================================================================
    # NEW: unlock_reset_day - Called by dashboard
    # ===================================================================
    @app.route('/config/unlock_reset_day')
    def api_unlock_reset_day():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global reset_day_lock_until
        was_locked = is_reset_day_locked()
        reset_day_lock_until = 0
        log_event(f"RESET DAY UNLOCKED (was_locked={was_locked})", "WARNING")
        save_state(push_cloud=True)
        return jsonify({"success": True, "was_locked": was_locked})

    @app.route('/config/set_key')
    def api_set_key():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global current_api_key
        new_key = request.args.get('new_key')
        if new_key and len(new_key) >= 10:
            current_api_key = new_key; log_event("API KEY CHANGED"); save_state(push_cloud=True)
            return jsonify({"success": True, "message": "API Key updated"})
        return jsonify({"success": False, "message": "Key must be >= 10 chars"}), 400

    @app.route('/lcd/display')
    def api_lcd_display():
        if not is_authorized(): return jsonify({"success": False, "message": "Unauthorized"}), 401
        global custom_lcd_lines, custom_lcd_expire
        l1 = request.args.get('l1', '')[:16]; l2 = request.args.get('l2', '')[:16]
        try: t = int(request.args.get('t', 10))
        except ValueError: t = 10
        if l1 or l2:
            custom_lcd_lines = [l1.ljust(16), l2.ljust(16)]; custom_lcd_expire = time.time() + t
            log_event(f"LCD MSG ({t}s): {l1} | {l2}")
            return jsonify({"success": True, "message": f"Displaying for {t}s"})
        return jsonify({"success": False, "message": "Missing l1/l2"}), 400

    def run_web_server():
        app.run(host='0.0.0.0', port=5000, threaded=True)

    threading.Thread(target=run_web_server, daemon=True).start()
    print(">>> WEB DASHBOARD ACTIVE on port 5000 <<<")

def ping_render_server():
    while True:
        try: urllib.request.urlopen(RENDER_SERVER_URL, timeout=3)
        except Exception: pass
        time.sleep(300)

if RENDER_SERVER_URL != "https://your-future-app-name.onrender.com/ping":
    threading.Thread(target=ping_render_server, daemon=True).start()

WATCHDOG_TIMEOUT = 30; last_heartbeat_time = time.time()
def watchdog_monitor():
    global last_heartbeat_time, last_shutdown_reason
    while True:
        time.sleep(5)
        if not emergency_stop_active and not pending_cycle_start:
            if time.time() - last_heartbeat_time > WATCHDOG_TIMEOUT:
                log_event("WATCHDOG TRIGGERED: Rebooting...", "ERROR")
                last_shutdown_reason = "WATCHDOG"; save_state()
                os.system("sudo reboot")

threading.Thread(target=watchdog_monitor, daemon=True).start()

# ===================================================================
# CLOUD SYNC - FIXED: sends ALL wings including disabled,
# includes display_name, disabled, physicalToggle, lock fields
# ===================================================================
def push_state_to_server():
    global emergency_stop_active, active_wing_id, last_cloud_error_log_time, last_cloud_sync_time, event_queue
    while True:
        cloud_push_event.wait(30)
        cloud_push_event.clear()
        if FLASK_AVAILABLE and event_queue:
            try:
                uptime = int(time.time() - BOOT_TIME)
                cpu_temp = get_cpu_temp()
                disk_free_mb = 0.0
                try:
                    stat = os.statvfs("/")
                    disk_free_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
                except: pass
                events_to_send = event_queue.copy()

                # FIX: Include ALL wings (not filtering disabled), add display_name, disabled, physicalToggle
                wings_payload = {}
                for wid, w in wings.items():
                    wings_payload[wid] = {
                        "usedDays": w['used_days'],
                        "targetDays": w['target_days'],
                        "name": w['name'],
                        "display_name": w['display_name'],
                        "disabled": w['disabled'],
                        "physicalToggle": get_wing_status(wid),
                        "clicks": w['relay_clicks']
                    }

                payload = {
                    "societyId": SOCIETY_ID,
                    "firmwareVersion": FIRMWARE_VERSION,
                    "bootCount": boot_count,
                    "lastShutdownReason": last_shutdown_reason,
                    "last_reboot_reason": last_shutdown_reason,
                    "uptimeSeconds": uptime,
                    "deviceTime": get_current_now().isoformat(),
                    "clockSource": get_clock_source(),
                    "cpuTemp": round(cpu_temp, 1),
                    "diskFreeMB": round(disk_free_mb, 2),
                    "activeWing": active_wing_id,
                    "wings": wings_payload,
                    "resetDay": reset_day,
                    "emergencyStop": emergency_stop_active,
                    "events": events_to_send,
                    "key": current_api_key,
                    "quota_lock_until": datetime.fromtimestamp(quota_lock_until).isoformat() if quota_lock_until > 0 else "",
                    "reset_day_lock_until": datetime.fromtimestamp(reset_day_lock_until).isoformat() if reset_day_lock_until > 0 else "",
                    "watchdog_enabled": True
                }

                req = urllib.request.Request(SERVER_PUSH_URL, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=15) as response:
                    event_queue.clear()
                    last_cloud_sync_time = get_current_now().isoformat()
                    reply = json.loads(response.read().decode('utf-8'))
                    if reply.get("success") and reply.get("command"):
                        process_cloud_command(reply)
            except Exception as e:
                if time.time() - last_cloud_error_log_time > 3600:
                    log_event(f"CLOUD SYNC FAILED: {e}", "WARNING")
                    last_cloud_error_log_time = time.time()

# ===================================================================
# CLOUD COMMAND PROCESSOR - Handles ALL 12 commands from backend
# ===================================================================
def process_cloud_command(reply):
    global emergency_stop_active, active_wing_id, quota_lock_until, reset_day, reset_day_lock_until
    cmd = reply.get("command", "")
    wing = reply.get("wing", "")
    params = reply.get("params", {})

    if cmd == "estop":
        if not emergency_stop_active: trigger_physical_estop()

    elif cmd == "restart_system":
        if emergency_stop_active:
            emergency_stop_active = False; recover_after_reboot()

    elif cmd == "switch":
        if wing in WING_ORDER:
            wings[wing]['remote_block_until'] = 0
            switch_wing(wing, source="cloud_command")

    elif cmd == "off":
        if wing in WING_ORDER:
            wings[wing]['remote_block_until'] = time.time() + 300
            if active_wing_id == wing:
                wings[wing]['relay'].off(); wings[wing]['is_active'] = False
                active_wing_id = None; log_event(f"Wing {wing} CLOUD OFF")
                save_state(push_cloud=True)

    elif cmd == "off_all":
        for w in wings.values(): w['relay'].off(); w['is_active'] = False; w['remote_block_until'] = time.time() + 300
        if active_wing_id: log_event("ALL WINGS CLOUD OFF")
        active_wing_id = None; save_state(push_cloud=True)

    elif cmd == "force_on":
        if wing and wing in WING_ORDER and is_wing_eligible(wing):
            switch_wing(wing, source="cloud_command")
        elif last_assigned_wing and is_wing_eligible(last_assigned_wing):
            switch_wing(last_assigned_wing, source="cloud_command")

    elif cmd == "reset":
        for w in wings.values(): w['used_days'] = 0; w['remote_block_until'] = 0
        active_wing_id = None; save_state(push_cloud=True)
        log_event("CLOUD RESET ALL DAYS")

    elif cmd == "set_days":
        if not is_quota_locked():
            wing_days = params.get("wings", {})
            for wid, days in wing_days.items():
                if wid in wings: wings[wid]['target_days'] = int(days)
            save_state(push_cloud=True)
            log_event(f"CLOUD SET DAYS: {wing_days}")

    elif cmd == "set_monthly_quota":
        if not is_quota_locked():
            total_units = float(params.get("total_units", 0))
            total_days = float(params.get("total_days", 30))
            wing_units = params.get("wings", {})
            if total_units > 0 and total_days > 0:
                avg = total_units / total_days
                calc = {}
                for wid in WING_ORDER:
                    u = float(wing_units.get(wid, 0))
                    calc[wid] = max(1, math.floor(u / avg)) if u > 0 and not wings[wid]['disabled'] else 0
                quota_lock_until = time.time() + 2592000
                for wid, d in calc.items():
                    wings[wid]['target_days'] = d; wings[wid]['used_days'] = 0; wings[wid]['remote_block_until'] = 0
                save_state(push_cloud=True)
                log_event(f"CLOUD QUOTA: {total_units}u/{total_days}d -> {calc}")

    elif cmd == "lock_quota":
        duration = int(params.get("duration_days", 30))
        quota_lock_until = time.time() + (duration * 86400)
        save_state(push_cloud=True)
        log_event(f"CLOUD LOCK QUOTA {duration}d")

    elif cmd == "unlock_quota":
        quota_lock_until = 0
        save_state(push_cloud=True)
        log_event("CLOUD UNLOCK QUOTA")

    elif cmd == "set_reset_day":
        if not is_reset_day_locked():
            day = int(params.get("day", reset_day))
            if 1 <= day <= 28:
                reset_day = day
                reset_day_lock_until = time.time() + 2592000
                save_state(push_cloud=True)
                log_event(f"CLOUD SET RESET DAY {day}, LOCKED")

    elif cmd == "unlock_reset_day":
        reset_day_lock_until = 0
        save_state(push_cloud=True)
        log_event("CLOUD UNLOCK RESET DAY")

    elif cmd == "toggle_disable":
        if wing and wing in WING_ORDER:
            wings[wing]['disabled'] = not wings[wing]['disabled']
            if wings[wing]['disabled'] and active_wing_id == wing:
                wings[wing]['relay'].off(); wings[wing]['is_active'] = False; active_wing_id = None
            save_state(push_cloud=True)
            log_event(f"CLOUD {'DISABLE' if wings[wing]['disabled'] else 'ENABLE'} {wing}")

    elif cmd == "set_display_name":
        if wing and wing in WING_ORDER:
            name = params.get("name", "")
            if name:
                wings[wing]['display_name'] = name[:12]
                save_state(push_cloud=True)
                log_event(f"CLOUD RENAME {wing} -> {name}")

    elif cmd == "reboot_device":
        log_event("CLOUD REBOOT", "WARNING")
        last_shutdown_reason = "CLOUD_COMMAND"; save_state()
        time.sleep(2); os.system("sudo reboot")

    elif cmd == "restart_system":
        if emergency_stop_active:
            emergency_stop_active = False; recover_after_reboot()

threading.Thread(target=push_state_to_server, daemon=True).start()
print(">>> CLOUD SYNC ACTIVE <<<")

load_state()
log_event(f"SYSTEM BOOT. Reason: {last_shutdown_reason}. Boot#: {boot_count}")
boot_count += 1
save_state()

update_lcd(["EMS POWER ROUTER", "SYSTEM START"]); time.sleep(2)
recover_after_reboot()

if active_wing_id is None:
    next_wing = get_next_eligible_wing()
    if next_wing: switch_wing(next_wing, source="startup_recovery")

last_save_time = time.time(); last_lcd_update = 0; current_screen = 0; TOTAL_SCREENS = len(WING_ORDER) + 1
last_health_check_time = time.time()

try:
    while True:
        if emergency_stop_active:
            last_heartbeat_time = time.time()
            if time.time() - last_lcd_update > 1.0: update_lcd_estop(); last_lcd_update = time.time()
            time.sleep(1); continue

        last_heartbeat_time = time.time(); now = get_current_now()
        current_date = now.strftime("%Y-%m-%d")

        if current_date != last_24h_log_date:
            log_event("SYSTEM 24H HEARTBEAT - ALIVE"); last_24h_log_date = current_date; save_state()

        cpu_temp = get_cpu_temp()
        if cpu_temp >= 95.0:
            if cpu_temp_state != "E_STOP":
                log_event(f"SYSTEM STOPPED DUE TO OVERHEAT {cpu_temp:.1f}C", "ERROR")
                for w in wings.values(): w['relay'].off(); w['is_active'] = False
                active_wing_id = None; last_shutdown_reason = "OVERHEAT"; save_state()
                if LCD_CONNECTED: update_lcd(["!!! OVERHEAT !!!", "HALTING SYSTEM"])
                time.sleep(5); os.system("sudo shutdown -h now")
        elif cpu_temp >= 90.0:
            if cpu_temp_state not in ["RELAY_OFF"]: overheat_timer = time.time(); cpu_temp_state = "RELAY_OFF"
            if cpu_temp_state == "RELAY_OFF" and (time.time() - overheat_timer > 300):
                if active_wing_id:
                    log_event(f"CPU TEMP CRITICAL {cpu_temp:.1f}C. Relays Safe-Shutdown.", "ERROR")
                    for w in wings.values(): w['relay'].off(); w['is_active'] = False
                    active_wing_id = None; save_state(push_cloud=True)
        elif cpu_temp >= 85.0:
            if cpu_temp_state not in ["WARN_LCD_CLOUD", "RELAY_OFF", "E_STOP"]: overheat_timer = time.time(); cpu_temp_state = "WARN_LCD_CLOUD"
            LCD_CYCLE_TIME = 20.0
            if cpu_temp_state == "WARN_LCD_CLOUD" and (time.time() - overheat_timer > 300):
                log_event(f"CPU TEMP WARNING {cpu_temp:.1f}C. LCD Slowed.", "WARNING")
        elif cpu_temp >= 70.0:
            if cpu_temp_state == "NORMAL": log_event(f"CPU TEMP WARNING {cpu_temp:.1f}C", "WARNING"); cpu_temp_state = "WARN_LOG"
            LCD_CYCLE_TIME = LCD_CYCLE_TIME_NORMAL
        else:
            if cpu_temp_state != "NORMAL":
                log_event(f"CPU NORMAL {cpu_temp:.1f}C", "INFO")
                cpu_temp_state = "NORMAL"; overheat_timer = 0; LCD_CYCLE_TIME = LCD_CYCLE_TIME_NORMAL

        if pending_cycle_start and now.day == reset_day and now.month != last_reset_month:
            log_event(f"START DATE REACHED ({reset_day}th) - APPLYING BUFFERED QUOTA!")
            for wid, days in pending_new_days.items():
                if wid in wings: wings[wid]['target_days'] = days; wings[wid]['used_days'] = 0; wings[wid]['remote_block_until'] = 0
            pending_cycle_start = False; pending_new_days = {}; last_reset_month = now.month
            active_wing_id = None
            for w in wings.values(): w['relay'].off(); w['is_active'] = False
            switch_wing('A', source="quota_start"); save_state(push_cloud=True)

        elif not pending_cycle_start and now.day == reset_day and now.month != last_reset_month:
            log_event(f"MONTHLY HARD RESET ({reset_day}th)")
            for w in wings.values(): w['used_days'] = 0; w['remote_block_until'] = 0
            last_reset_month = now.month; save_state(push_cloud=True); switch_wing('A', source="monthly_reset")

        if current_date != last_counted_date:
            if active_wing_id and active_wing_id in WING_ORDER and wings[active_wing_id]['used_days'] < wings[active_wing_id]['target_days']:
                wings[active_wing_id]['used_days'] += 1; log_event(f"Wing {active_wing_id} Completed Day")
            last_counted_date = current_date; save_state()

        if active_wing_id and active_wing_id in WING_ORDER:
            is_on = is_wing_toggled_on(active_wing_id); is_full = wings[active_wing_id]['used_days'] >= wings[active_wing_id]['target_days']
            if not is_on: log_event(f"ACTIVE Wing {active_wing_id} TURNED OFF", "WARNING"); switch_wing(None)
            elif is_full: log_event(f"ACTIVE Wing {active_wing_id} QUOTA FULL"); switch_wing(None)

        if not active_wing_id:
            next_wing = get_next_eligible_wing(failed_wing_id=active_wing_id)
            if next_wing: switch_wing(next_wing, source="auto_route")
            elif all(wings[w]['used_days'] >= wings[w]['target_days'] for w in WING_ORDER):
                log_event("ALL WINGS FULL - AUTO CYCLE RESET", "WARNING")
                for w in wings.values(): w['used_days'] = 0; w['remote_block_until'] = 0
                next_eligible = get_next_eligible_wing()
                if next_eligible: switch_wing(next_eligible, source="auto_cycle_reset")
                save_state(push_cloud=True)

        if time.time() - last_health_check_time > 300:
            last_health_check_time = time.time()
            if active_wing_id is None:
                if any(is_wing_eligible(w) for w in WING_ORDER):
                    log_event("Recovery: No active wing found", "WARNING")
                    switch_wing(get_next_eligible_wing(), source="health_check")

        if custom_lcd_lines and time.time() < custom_lcd_expire:
            if time.time() - last_lcd_update > LCD_CYCLE_TIME: update_lcd(custom_lcd_lines); last_lcd_update = time.time()
        elif not active_wing_id and not any(is_wing_eligible(w) for w in WING_ORDER):
            if time.time() - last_lcd_update > LCD_CYCLE_TIME: update_lcd_emergency(); last_lcd_update = time.time()
        else:
            if time.time() - last_lcd_update > LCD_CYCLE_TIME: update_lcd_status(current_screen); current_screen = (current_screen + 1) % TOTAL_SCREENS; last_lcd_update = time.time()

        if time.time() - last_save_time > 30: save_state(); last_save_time = time.time()
        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopping EMS System...")
    last_shutdown_reason = "NORMAL"; save_state()
finally:
    for w in wings.values(): w['relay'].off(); w['relay'].close(); w['toggle'].close()
    physical_estop_btn.close()
    if LCD_CONNECTED: lcd.clear(); lcd.write_string("SYSTEM STOPPED   ")
    print("GPIO pins released safely!")
