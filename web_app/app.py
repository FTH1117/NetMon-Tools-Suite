from flask import Flask, render_template, request, jsonify, send_from_directory, abort
import os
import subprocess
import shutil
import requests
import csv
from datetime import datetime, timedelta
from collections import Counter
import threading
import uuid
import sys
import logging
import json
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

task_statuses = {}  # A dictionary to keep track of task statuses.
task_status_lock = threading.Lock()

# Set up logging
log_directory = '/var/log/app'
if not os.path.exists(log_directory):
    os.makedirs(log_directory)
log_file = os.path.join(log_directory, 'error.log')
handler = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
)
handler.setFormatter(formatter)
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)



# Zabbix server details
ZABBIX_URL = "<ZABBIX_URL>"
ZABBIX_API_URL = f"{ZABBIX_URL}/api_jsonrpc.php"
ZABBIX_USERNAME = "<ZABBIX_USERNAME>"
ZABBIX_PASSWORD = "<ZABBIX_PASSWORD>"

# Network Zabbix server details
NETWORK_ZABBIX_URL = "<NETWORK_ZABBIX_URL>"
NETWORK_ZABBIX_API_URL = f"{NETWORK_ZABBIX_URL}/api_jsonrpc.php"
NETWORK_ZABBIX_USERNAME = "<NETWORK_ZABBIX_USERNAME>"
NETWORK_ZABBIX_PASSWORD = "<NETWORK_ZABBIX_PASSWORD>"

# Directory to serve for browsing
BASE_DIR = '/home/almalinux'

# Helper functions for each action
def create_project(project_id, project_name, host_group_name, server_tags, racks, subscriptions, grafana_selected):
    # Verify the host group in the Zabbix server
    session = requests.Session()
    auth_token = zabbix_login_api(session, ZABBIX_API_URL, ZABBIX_USERNAME, ZABBIX_PASSWORD)
    if not auth_token:
        app.logger.error("Failed to authenticate with Zabbix API.")
        return False, "Error: Failed to authenticate with Zabbix API."
    group_id = get_hostgroup_id(auth_token, session, ZABBIX_API_URL, host_group_name)
    if not group_id:
        app.logger.error(f"Host group '{host_group_name}' not found in Zabbix.")
        return False, f"Error: Host group '{host_group_name}' not found in Zabbix."
    app.logger.info(f"Found host group '{host_group_name}' with ID {group_id}")

    # If server tags and racks are provided, verify them in the network Zabbix server
    if server_tags and racks:
        # Authenticate with network Zabbix
        network_session = requests.Session()
        network_auth_token = zabbix_login_api(network_session, NETWORK_ZABBIX_API_URL, NETWORK_ZABBIX_USERNAME, NETWORK_ZABBIX_PASSWORD)
        if not network_auth_token:
            return False, "Error: Failed to authenticate with Network Zabbix API."
        # For each server tag and rack, verify host existence
        for server_tag, rack in zip(server_tags, racks):
            host_exists = verify_network_host(network_auth_token, network_session, rack, server_tag)
            if not host_exists:
                return False, f"Error: Host with Rack '{rack}' and Server Tag '{server_tag}' not found in Network Zabbix."
            else:
                print(f"Verified host with Rack '{rack}' and Server Tag '{server_tag}' in Network Zabbix.")

    # If all verifications passed, proceed to create the project directory and customer_details.txt
    project_dir = os.path.join(BASE_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)
    details_file = os.path.join(project_dir, "customer_details.txt")
    with open(details_file, 'w') as f:
        f.write(f"Project ID: {project_id}\n")
        f.write(f"Project Name: {project_name}\n")
        f.write(f"Host Group Name: {host_group_name}\n")
        for i, subscription in enumerate(subscriptions, start=1):
            f.write(f"Subscription ID {i}: {subscription}\n")
        for i, (server_tag, rack) in enumerate(zip(server_tags, racks), start=1):
            f.write(f"Server Tag {i}: {server_tag}\n")
            f.write(f"Rack {i}: {rack}\n")
        f.write(f"Grafana Selected: {'Yes' if grafana_selected else 'No'}\n")

    if grafana_selected:
        success, message = setup_grafana(project_id, host_group_name, server_tags, racks)
        if not success:
            return False, message

    return True, f"Project '{project_id}' created successfully at {project_dir}."


def zabbix_login_api(session, zabbix_api_url, username, password):
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {"user": username, "password": password},
        "id": 1,
        "auth": None
    }
    response = session.post(zabbix_api_url, json=payload)
    result = response.json()
    if 'result' in result:
        return result['result']
    else:
        app.logger.error("Failed to authenticate with Zabbix API.")
        return None


def get_hostgroup_id(auth_token, session, zabbix_api_url, group_name):
    payload = {
        "jsonrpc": "2.0",
        "method": "hostgroup.get",
        "params": {"output": ["groupid"], "filter": {"name": [group_name]}},
        "auth": auth_token,
        "id": 2
    }
    response = session.post(zabbix_api_url, json=payload)
    result = response.json()
    if result.get('result'):
        group_id = result['result'][0]['groupid']
        app.logger.info(f"Found host group '{group_name}' with ID {group_id}")
        return group_id
    else:
        app.logger.warning(f"Host group '{group_name}' not found.")
        return None

def get_hosts(auth_token, session, rack):
    payload = {
        "jsonrpc": "2.0",
        "method": "host.get",
        "params": {
            "output": ["hostid", "host", "name"],
            "search": {
                "host": rack,
                "name": rack
            },
            "searchCaseInsensitive": True
        },
        "auth": auth_token,
        "id": 2
    }
    response = session.post(NETWORK_ZABBIX_API_URL, json=payload)
    result = response.json()
    hosts = result.get('result', [])
    return hosts

def get_graphs(auth_token, session, host_id, server_tag):
    payload = {
        "jsonrpc": "2.0",
        "method": "graph.get",
        "params": {
            "output": ["graphid", "name"],
            "hostids": host_id,
            "search": {
                "name": server_tag
            },
            "searchCaseInsensitive": True
        },
        "auth": auth_token,
        "id": 3
    }
    response = session.post(NETWORK_ZABBIX_API_URL, json=payload)
    return response.json().get('result', [])

def verify_network_host(auth_token, session, rack, server_tag):
    # Initialize hosts as empty list
    hosts = []

    # Check if the rack starts with 'MAH-'
    if rack.startswith('MAH-'):
        # Try searching for hosts with 'MAH-<Anything>'
        hosts = get_hosts(auth_token, session, rack)
        if not hosts:
            # If no hosts found, try 'AIMS-<Anything>'
            aims_rack = 'AIMS-' + rack[len('MAH-'):]
            app.logger.info(f"No hosts found for '{rack}', trying '{aims_rack}'")
            hosts = get_hosts(auth_token, session, aims_rack)
    else:
        # For other racks, search as usual
        hosts = get_hosts(auth_token, session, rack)

    if not hosts:
        app.logger.warning(f"No hosts found containing rack '{rack}'.")
        return False

    # For each host, check if graphs matching server_tag exist
    for host in hosts:
        host_id = host['hostid']
        graphs = get_graphs(auth_token, session, host_id, server_tag)
        if graphs:
            return True
    return False


def run_script_async(command, task_id=None):
    def target():
        app.logger.debug(f"Running command: {' '.join(command)}")
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            app.logger.debug(f"Command output: {result.stdout}")
            if task_id:
                # Update task status to 'completed' upon success
                with task_status_lock:
                    task_statuses[task_id] = {
                        'status': 'completed',
                        'message': 'Task completed successfully.'
                    }
        except subprocess.CalledProcessError as e:
            error_message = f"Command '{' '.join(command)}' failed with return code {e.returncode}\n"
            if e.stderr:
                error_message += f"Stderr: {e.stderr}\n"
            if e.stdout:
                error_message += f"Stdout: {e.stdout}\n"
            app.logger.error(error_message)
            if task_id:
                # Update task status to 'failed' upon error
                with task_status_lock:
                    task_statuses[task_id] = {
                        'status': 'failed',
                        'message': error_message
                    }
        except Exception as e:
            app.logger.exception(f"Unexpected error: {e}")
            if task_id:
                # Update task status to 'failed', including the exception message
                with task_status_lock:
                    task_statuses[task_id] = {
                        'status': 'failed',
                        'message': f'Unexpected error: {str(e)}'
                    }

    if task_id:
        # Set initial status to 'in progress'
        with task_status_lock:
            task_statuses[task_id] = {'status': 'in progress', 'message': 'Task is running.'}

    thread = threading.Thread(target=target)
    thread.start()
    return thread



def export_graph(month, year, project_id):
    task_id = str(uuid.uuid4())
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(os.path.dirname(script_dir), 'zabbix_graph_export.py')
    command = ["python3", script_path, "--month", month, "--year", year, "--customer", project_id]
    run_script_async(command, task_id)
    return True, f"Task {task_id} started for exporting graphs.", task_id

def export_network_graph(month, year, project_id):
    task_id = str(uuid.uuid4())
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(os.path.dirname(script_dir), 'network_graph_export.py')
    command = ["python3", script_path, "--month", month, "--year", year, "--customer", project_id]
    run_script_async(command, task_id)
    return True, f"Task {task_id} started for exporting network graphs.", task_id

def export_grafana_graph(month, year, project_id):
    task_id = str(uuid.uuid4())
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(os.path.dirname(script_dir), 'grafana_graph_export.py')
    command = ["python3", script_path, "--month", month, "--year", year, "--customer", project_id]
    run_script_async(command, task_id)
    return True, f"Task {task_id} started for exporting Grafana graphs.", task_id


def generate_report(month, year, project_id):
    task_id = str(uuid.uuid4())
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(os.path.dirname(script_dir), 'generate_report.py')
    command = ["python3", script_path, "--month", month, "--year", year, "--customer", project_id]
    run_script_async(command, task_id)
    return True, f"Task {task_id} started for generating report.", task_id

def generate_grafana_report(month, year, project_id, llama_selected=False):
    task_id = str(uuid.uuid4())
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(os.path.dirname(script_dir), 'generate_report_grafana.py')
    command = ["python3", script_path, "--month", month, "--year", year, "--customer", project_id]
    if llama_selected:
        command.append("--llama")
    run_script_async(command, task_id)
    return True, f"Task {task_id} started for generating Grafana report.", task_id


def export_and_generate_report(month, year, project_id):
    task_id = str(uuid.uuid4())

    def target():
        with task_status_lock:
            task_statuses[task_id] = {'status': 'in progress', 'message': 'Task is running.'}
        try:
            # Start the export scripts asynchronously
            script_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(script_dir)
            # Start the export scripts asynchronously
            task_id1 = str(uuid.uuid4())
            thread1 = run_script_async(
                ["python3", os.path.join(parent_dir, "zabbix_graph_export.py"), "--month", month, "--year", year, "--customer", project_id],
                task_id=task_id1
            )
            task_id2 = str(uuid.uuid4())
            thread2 = run_script_async(
                ["python3", os.path.join(parent_dir, "network_graph_export.py"), "--month", month, "--year", year, "--customer", project_id],
                task_id=task_id2
            )
            # Wait for both export scripts to complete
            thread1.join()
            thread2.join()
            # Check the statuses
            with task_status_lock:
                status1 = task_statuses.get(task_id1)
                status2 = task_statuses.get(task_id2)
            if status1['status'] != 'completed':
                with task_status_lock:
                    task_statuses[task_id] = {'status': 'failed', 'message': f"zabbix_graph_export.py failed: {status1['message']}"}
                return
            if status2['status'] != 'completed':
                with task_status_lock:
                    task_statuses[task_id] = {'status': 'failed', 'message': f"network_graph_export.py failed: {status2['message']}"}
                return
            # Now start the report generation script
            task_id3 = str(uuid.uuid4())
            thread3 = run_script_async(
                ["python3", os.path.join(parent_dir, "generate_report.py"), "--month", month, "--year", year, "--customer", project_id],
                task_id=task_id3
            )
            # Wait for report generation to complete
            thread3.join()
            # Update task status to 'completed'
            with task_status_lock:
                status3 = task_statuses.get(task_id3)
            if status3['status'] != 'completed':
                with task_status_lock:
                    task_statuses[task_id] = {'status': 'failed', 'message': f"generate_report.py failed: {status3['message']}"}
                return
            # If all succeeded
            with task_status_lock:
                task_statuses[task_id] = {'status': 'completed', 'message': 'Export and report generation completed.'}
        except Exception as e:
            # Update task status to 'failed'
            with task_status_lock:
                task_statuses[task_id] = {'status': 'failed', 'message': f'Task failed: {str(e)}'}

    # Start the process in a separate thread
    process_thread = threading.Thread(target=target)
    process_thread.start()
    return True, f"Task {task_id} started for exporting and generating report.", task_id

def export_and_generate_grafana_report(month, year, project_id, llama_selected=False):
    task_id = str(uuid.uuid4())

    def target():
        with task_status_lock:
            task_statuses[task_id] = {'status': 'in progress', 'message': 'Task is running.'}
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(script_dir)

            # Run the Grafana graph export script
            task_id1 = str(uuid.uuid4())
            thread1 = run_script_async(
                ["python3", os.path.join(parent_dir, "grafana_graph_export.py"), "--month", month, "--year", year, "--customer", project_id],
                task_id=task_id1
            )
            thread1.join()

            with task_status_lock:
                status1 = task_statuses.get(task_id1)
            if status1['status'] != 'completed':
                with task_status_lock:
                    task_statuses[task_id] = {'status': 'failed', 'message': f"grafana_graph_export.py failed: {status1['message']}"}
                return

            # Run the Grafana report generation script with llama_selected parameter
            task_id2 = str(uuid.uuid4())
            cmd = ["python3", os.path.join(parent_dir, "generate_report_grafana.py"), "--month", month, "--year", year, "--customer", project_id]
            if llama_selected:
                cmd.append("--llama")
            thread2 = run_script_async(cmd, task_id=task_id2)
            thread2.join()

            with task_status_lock:
                status2 = task_statuses.get(task_id2)
            if status2['status'] != 'completed':
                with task_status_lock:
                    task_statuses[task_id] = {'status': 'failed', 'message': f"generate_report_grafana.py failed: {status2['message']}"}
                return

            with task_status_lock:
                task_statuses[task_id] = {'status': 'completed', 'message': 'Export and report generation for Grafana completed.'}
        except Exception as e:
            with task_status_lock:
                task_statuses[task_id] = {'status': 'failed', 'message': f'Task failed: {str(e)}'}

    process_thread = threading.Thread(target=target)
    process_thread.start()
    return True, f"Task {task_id} started for exporting and generating Grafana report.", task_id


def find_missing_timestamps(csv_file_path):
    try:
        import os
        import re
        timestamps = []
        with open(csv_file_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                timestamp_str = row['Timestamp']
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                timestamps.append(timestamp)
        
        if not timestamps:
            return False, "No data in CSV file."
        
        # Determine expected interval
        timestamps.sort()
        time_diffs = [(timestamps[i+1] - timestamps[i]).total_seconds() for i in range(len(timestamps)-1)]
        if not time_diffs:
            return False, "Not enough data to determine expected interval."
        
        # Use the most common time difference as expected interval
        counter = Counter(time_diffs)
        expected_interval_seconds = counter.most_common(1)[0][0]
        expected_interval = timedelta(seconds=expected_interval_seconds)
        
        # Extract year and month from filename using regex
        base_filename = os.path.basename(csv_file_path)
        match = re.search(r'_(\d{4})_(\d{2})\.csv$', base_filename)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            start_time = datetime(year, month, 1)
            # Get the last day of the month
            if month == 12:
                end_time = datetime(year + 1, 1, 1) - timedelta(seconds=1)
            else:
                end_time = datetime(year, month + 1, 1) - timedelta(seconds=1)
        else:
            # If parsing fails, use first and last timestamp in data
            start_time = timestamps[0]
            end_time = timestamps[-1]
        
        # Generate expected timestamps from start_time to end_time
        expected_timestamps = []
        current_time = start_time
        while current_time <= end_time:
            expected_timestamps.append(current_time)
            current_time += expected_interval
                
        # Find missing timestamps considering the delay tolerance
        DELAY_TOLERANCE_SECONDS = 3  # Tolerance in seconds
        missing_timestamps = []
        actual_index = 0
        actual_len = len(timestamps)
        
        for expected_time in expected_timestamps:
            # Move actual_index forward while actual timestamp is less than expected_time - tolerance
            while (actual_index < actual_len and timestamps[actual_index] < expected_time - timedelta(seconds=DELAY_TOLERANCE_SECONDS)):
                actual_index += 1
            # Check if actual timestamp is within tolerance
            if actual_index < actual_len and abs((timestamps[actual_index] - expected_time).total_seconds()) <= DELAY_TOLERANCE_SECONDS:
                # There is an actual timestamp within tolerance; do not consider as missing
                continue
            else:
                # No actual timestamp within tolerance; consider as missing
                missing_timestamps.append(expected_time)
        
        # Group missing timestamps into downtime periods
        downtime_periods = []
        if missing_timestamps:
            start_downtime = missing_timestamps[0]
            prev_time = missing_timestamps[0]
            for current_time in missing_timestamps[1:]:
                if (current_time - prev_time) <= expected_interval + timedelta(seconds=DELAY_TOLERANCE_SECONDS * 2):
                    # Continue the current downtime period
                    prev_time = current_time
                else:
                    # Downtime period ends here
                    end_downtime = prev_time + expected_interval
                    downtime_periods.append((start_downtime, end_downtime))
                    # Start a new downtime period
                    start_downtime = current_time
                    prev_time = current_time
            # Handle the last downtime period
            end_downtime = prev_time + expected_interval
            downtime_periods.append((start_downtime, end_downtime))
        
        # Format downtime periods as strings
        if downtime_periods:
            downtime_strings = []
            for start, end in downtime_periods:
                downtime_strings.append(f"{start.strftime('%Y-%m-%d %H:%M:%S')} to {end.strftime('%Y-%m-%d %H:%M:%S')}")
            return True, downtime_strings
        else:
            return True, ["No downtime detected."]
    except Exception as e:
        return False, f"Error processing CSV file: {str(e)}"

def setup_grafana(project_id, host_group_name, server_tags, racks):
    app.logger.info(f"Setting up Grafana for Project ID: {project_id}")
    # Call grafana_create.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    grafana_script_path = os.path.join(os.path.dirname(script_dir), 'grafana_create.py')
    command = ["python3", grafana_script_path, "--host_group_name", host_group_name]

    if server_tags and racks:
        for tag in server_tags:
            command.extend(["--server_tag", tag])
        for rack in racks:
            command.extend(["--rack", rack])

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        # Parse the output
        output = result.stdout.strip()
        dashboard_info = json.loads(output)
        dashboard_uid = dashboard_info.get('dashboard_uid')
        dashboard_url = dashboard_info.get('dashboard_url')
        # Append dashboard UID and URL to customer_details.txt
        project_dir = os.path.join(BASE_DIR, project_id)
        details_file = os.path.join(project_dir, "customer_details.txt")
        
        # Read existing details
        with open(details_file, 'r') as f:
            lines = f.readlines()
        
        # Update or append "Grafana Selected: Yes"
        grafana_selected_found = False
        for i, line in enumerate(lines):
            if line.startswith("Grafana Selected:"):
                lines[i] = "Grafana Selected: Yes\n"
                grafana_selected_found = True
                break
        if not grafana_selected_found:
            # Insert "Grafana Selected: Yes" after Host Group Name
            for i, line in enumerate(lines):
                if line.startswith("Host Group Name:"):
                    lines.insert(i + 1, "Grafana Selected: Yes\n")
                    break
            else:
                # If Host Group Name not found, append at the end
                lines.append("Grafana Selected: Yes\n")

        # Append Dashboard UID and URL
        lines.append(f"Dashboard UID: {dashboard_uid}\n")
        lines.append(f"Dashboard URL: {dashboard_url}\n")

        # Write back to customer_details.txt
        with open(details_file, 'w') as f:
            f.writelines(lines)

        app.logger.info(f"Dashboard created with UID: {dashboard_uid}, URL: {dashboard_url}")
        return True, f"Dashboard created with UID: {dashboard_uid}, URL: {dashboard_url}"
    except subprocess.CalledProcessError as e:
        error_message = f"Failed to create Grafana dashboard: {e.stderr}"
        app.logger.error(error_message)
        return False, error_message
    except json.JSONDecodeError as e:
        error_message = (
            f"Failed to parse Grafana dashboard creation output: {e}\n"
            f"Output: {output}\n"
            f"Stderr: {result.stderr}"
        )
        app.logger.error(error_message)
        return False, error_message





# Route to display the main interface
@app.route('/')
@app.route('/browse/<path:path>')
# def index(path=''):
#     full_path = os.path.join(BASE_DIR, path)
#     if os.path.isdir(full_path):
#         files = [f for f in os.listdir(full_path) if not f.startswith('.')]
#         return render_template('index.html', files=files, current_path=path)
#     elif os.path.isfile(full_path):
#         return send_from_directory(BASE_DIR, path)
#     else:
#         abort(404)

def index(path=''):
    search_query = request.args.get('search', '').lower()
    full_path = os.path.join(BASE_DIR, path)
    
    # Calculate the parent path
    parent_path = '' if '/' not in path else path.rsplit('/', 1)[0]

    if os.path.isdir(full_path):
        items = []
        for f in os.listdir(full_path):
            if not f.startswith('.'):
                item_path = os.path.join(full_path, f)
                is_dir = os.path.isdir(item_path)
                include_item = False
                if search_query:
                    # Check if the search query is in the item name
                    if search_query in f.lower():
                        include_item = True
                    elif is_dir and path == '':
                        # We are at the root directory, and the item is a directory
                        # Check if 'customer_details.txt' exists in the directory
                        details_file = os.path.join(item_path, 'customer_details.txt')
                        if os.path.isfile(details_file):
                            try:
                                with open(details_file, 'r') as df:
                                    content = df.read().lower()
                                    if search_query in content:
                                        include_item = True
                            except Exception as e:
                                app.logger.error(f"Error reading {details_file}: {e}")
                else:
                    include_item = True  # Include all items if no search query
                if include_item:
                    # Initialize the item dictionary here
                    item_dict = {
                        'name': f,
                        'is_dir': is_dir
                    }

                    if is_dir and path == '':
                        details_file = os.path.join(item_path, 'customer_details.txt')
                        grafana_status = 'not_set_up'
                        if os.path.isfile(details_file):
                            try:
                                with open(details_file, 'r') as df:
                                    content = df.read()
                                    grafana_selected = False
                                    dashboard_uid = False
                                    for line in content.splitlines():
                                        if line.startswith('Grafana Selected:'):
                                            if line.strip() == 'Grafana Selected: Yes':
                                                grafana_selected = True
                                        if line.startswith('Dashboard UID:'):
                                            dashboard_uid = True
                                    if grafana_selected and dashboard_uid:
                                        grafana_status = 'set_up'
                                    else:
                                        grafana_status = 'not_set_up'
                            except Exception as e:
                                app.logger.error(f"Error reading {details_file}: {e}")
                                grafana_status = 'error'
                        else:
                            grafana_status = 'no_details'
                        item_dict['grafana_status'] = grafana_status

                    # Append the item dictionary to the list
                    items.append(item_dict)


        # Sort items: directories first, then files, both in alphabetical order
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

        return render_template('index.html', items=items, current_path=path, parent_path=parent_path, search_query=search_query)
    elif os.path.isfile(full_path):
        return send_from_directory(BASE_DIR, path)
    else:
        abort(404)

@app.route('/action', methods=['POST'])
def action():
    action_type = request.form['action']
    app.logger.info(f"Received action request: {action_type}")
    month = request.form.get('month')
    year = request.form.get('year')
    project_id = request.form.get('project_id')
    message = ""
    success = True  # Default to True
    task_id = None  # Initialize task_id

    if action_type == 'create':
        project_name = request.form.get('project_name')
        host_group_name = request.form.get('host_group_name')
        server_tag_count = int(request.form.get('server_tag_count', 0))
        server_tags = []
        racks = []
        for i in range(1, server_tag_count + 1):
            server_tag = request.form.get(f'server_tag_{i}')
            rack = request.form.get(f'rack_{i}')
            server_tags.append(server_tag)
            racks.append(rack)
        # Retrieve the number of authorized subscriptions and their values
        subscription_count = int(request.form.get('subscription_count', 0))
        subscriptions = []
        for i in range(1, subscription_count + 1):
            subscription = request.form.get(f'subscription_{i}')
            subscriptions.append(subscription)
        # Retrieve the 'grafana' checkbox value
        grafana_selected = 'grafana' in request.form
        success, message = create_project(project_id, project_name, host_group_name, server_tags, racks, subscriptions, grafana_selected)
    elif action_type == 'export_graph':
        success, message, task_id = export_graph(month, year, project_id)
    elif action_type == 'generate_report':
        success, message, task_id = generate_report(month, year, project_id)
    elif action_type == 'export_network_graph':
        success, message, task_id = export_network_graph(month, year, project_id)
    elif action_type == 'export_grafana_graph':
        success, message, task_id = export_grafana_graph(month, year, project_id)
    elif action_type == 'generate_grafana_report':
        llama_selected = 'llama' in request.form
        success, message, task_id = generate_grafana_report(month, year, project_id, llama_selected)
    elif action_type == 'export_and_generate':
        success, message, task_id = export_and_generate_report(month, year, project_id)
    elif action_type == 'export_and_generate_grafana':
        llama_selected = 'llama' in request.form
        success, message, task_id = export_and_generate_grafana_report(month, year, project_id, llama_selected)


    response_data = {'success': success, 'message': message}
    if task_id:
        response_data['task_id'] = task_id
    if success:
        app.logger.info(f"Action '{action_type}' completed successfully for Project ID: {project_id}")
    else:
        app.logger.error(f"Action '{action_type}' failed for Project ID: {project_id} with message: {message}")
    return jsonify(response_data)


@app.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    with task_status_lock:
        status_info = task_statuses.get(task_id)
    if status_info:
        return jsonify(status_info)
    else:
        return jsonify({'status': 'unknown', 'message': 'Task ID not found.'})


# Route to delete a file or directory
@app.route('/delete', methods=['POST'])
def delete():
    item_path = request.json.get('path')
    full_path = os.path.join(BASE_DIR, item_path)
    
    # Prevent deletion of directories at the root level
    relative_path = os.path.relpath(full_path, BASE_DIR)
    path_parts = relative_path.strip(os.sep).split(os.sep)
    if len(path_parts) == 1 and os.path.isdir(full_path):
        return jsonify({'status': 'error', 'message': 'Cannot delete directories at the root level'})
    
    if os.path.exists(full_path):
        try:
            if os.path.isfile(full_path):
                os.remove(full_path)
            elif os.path.isdir(full_path):
                shutil.rmtree(full_path)
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    else:
        return jsonify({'status': 'error', 'message': 'Path does not exist'})
    
@app.route('/edit_file', methods=['POST'])
def edit_file():
    data = request.get_json()
    file_path = data.get('file_path')
    content = data.get('content')

    if not file_path or content is None:
        return jsonify({'success': False, 'message': 'File path and content are required.'}), 400

    # Normalize the path to prevent directory traversal
    safe_path = os.path.normpath(file_path)

    # Ensure the path is relative and does not navigate up the directory tree
    if os.path.isabs(safe_path) or '..' in safe_path.split(os.path.sep):
        return jsonify({'success': False, 'message': 'Invalid file path.'}), 400

    full_file_path = os.path.join(BASE_DIR, safe_path)

    # Verify that the file exists and is within the BASE_DIR
    if not full_file_path.startswith(os.path.abspath(BASE_DIR)):
        return jsonify({'success': False, 'message': 'Invalid file path.'}), 400

    if os.path.exists(full_file_path) and os.path.isfile(full_file_path):
        try:
            with open(full_file_path, 'w') as f:
                f.write(content)
            return jsonify({'success': True, 'message': 'File saved successfully.'})
        except Exception as e:
            app.logger.error(f"Error saving file {full_file_path}: {e}")
            return jsonify({'success': False, 'message': f'Error saving file: {str(e)}'}), 500
    else:
        return jsonify({'success': False, 'message': 'File not found.'}), 404

@app.route('/project_details/<project_id>', methods=['GET'])
def project_details(project_id):
    project_dir = os.path.join(BASE_DIR, project_id)
    details_file = os.path.join(project_dir, "customer_details.txt")
    
    if os.path.exists(details_file):
        with open(details_file, 'r') as f:
            details_content = f.read()
        return jsonify({'status': 'success', 'content': details_content})
    else:
        return jsonify({'status': 'error', 'message': 'customer_details.txt not found'})

@app.route('/downtime', methods=['POST'])
def downtime():
    file_path = request.json.get('file_path')
    full_file_path = os.path.join(BASE_DIR, file_path)
    if os.path.exists(full_file_path) and os.path.isfile(full_file_path):
        success, result = find_missing_timestamps(full_file_path)
        if success:
            return jsonify({'success': True, 'downtime': result})
        else:
            return jsonify({'success': False, 'message': result})
    else:
        return jsonify({'success': False, 'message': 'File not found.'})
    
@app.route('/setup_grafana', methods=['POST'])
def setup_grafana_route():
    data = request.get_json()
    project_id = data.get('project_id')
    if not project_id:
        return jsonify({'success': False, 'message': 'Project ID is required.'})

    project_dir = os.path.join(BASE_DIR, project_id)
    details_file = os.path.join(project_dir, 'customer_details.txt')
    if not os.path.exists(details_file):
        return jsonify({'success': False, 'message': 'customer_details.txt not found in project directory.'})

    # Parse customer_details.txt
    details = {}
    with open(details_file, 'r') as f:
        for line in f:
            if ':' in line:
                key, value = line.strip().split(':', 1)
                details[key.strip()] = value.strip()

    grafana_selected = details.get('Grafana Selected', '').lower()
    dashboard_uid = details.get('Dashboard UID', '')

    if grafana_selected == 'no' or not dashboard_uid or 'Grafana Selected' not in details:
        # Proceed to set up Grafana
        project_name = details.get('Project Name')
        host_group_name = details.get('Host Group Name')
        server_tags = []
        racks = []
        i = 1
        while True:
            server_tag = details.get(f'Server Tag {i}')
            rack = details.get(f'Rack {i}')
            if not server_tag or not rack:
                break
            server_tags.append(server_tag)
            racks.append(rack)
            i += 1

        # Call the setup_grafana function
        success, message = setup_grafana(project_id, host_group_name, server_tags, racks)
        if success:
            return jsonify({'success': True, 'message': f'Grafana setup completed for project {project_id}.'})
        else:
            return jsonify({'success': False, 'message': message})
    else:
        return jsonify({'success': False, 'message': 'Grafana is already set up for this project.'})


# Add error handlers
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.exception("An error occurred during a request.")
    return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.run(host='0.0.0.0', port=port, debug=False)

