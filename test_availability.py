import requests
import os
import sys
from datetime import datetime, timezone
from collections import Counter

# Zabbix server details
ZABBIX_URL = "<ZABBIX_URL>"
ZABBIX_API_URL = f"{ZABBIX_URL}/api_jsonrpc.php"
USERNAME = "<ZABBIX_USERNAME>"
PASSWORD = "<ZABBIX_PASSWORD>"

# Authenticate with Zabbix API
def zabbix_login_api(session):
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {"user": USERNAME, "password": PASSWORD},
        "id": 1,
        "auth": None
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    result = response.json()
    if 'result' in result:
        return result['result']
    else:
        print("Failed to authenticate with Zabbix API.")
        sys.exit(1)

# Get host ID from the name
def get_host_id(auth_token, session, host_name):
    payload = {
        "jsonrpc": "2.0",
        "method": "host.get",
        "params": {
            "output": ["hostid"],
            "filter": {"name": [host_name]}
        },
        "auth": auth_token,
        "id": 2
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    result = response.json()
    if result['result']:
        host_id = result['result'][0]['hostid']
        print(f"Found host '{host_name}' with ID {host_id}")
        return host_id
    else:
        print(f"Host '{host_name}' not found.")
        sys.exit(1)

# Get item ID for ICMP ping or Zabbix agent ping checks
def get_ping_item_id(auth_token, session, host_id):
    # Try to get ICMP ping first
    item_keys = ["icmpping", "agent.ping"]  # Look for both icmpping and agent.ping
    for key in item_keys:
        payload = {
            "jsonrpc": "2.0",
            "method": "item.get",
            "params": {
                "output": ["itemid"],
                "hostids": host_id,
                "search": {
                    "key_": key
                }
            },
            "auth": auth_token,
            "id": 3
        }
        response = session.post(ZABBIX_API_URL, json=payload)
        result = response.json()
        if result['result']:
            item_id = result['result'][0]['itemid']
            print(f"Found {key} item ID: {item_id}")
            return item_id, key
    print(f"No ICMP ping or agent ping item found for host with ID {host_id}.")
    sys.exit(1)

# Fetch historical data for the given item (ICMP ping or Zabbix agent ping checks)
def fetch_item_history(session, auth_token, item_id, stime, etime):
    payload = {
        "jsonrpc": "2.0",
        "method": "history.get",
        "params": {
            "output": "extend",
            "history": 3,  # 3 for unsigned integer, typically used for ping/availability
            "itemids": item_id,
            "time_from": stime,
            "time_till": etime,
            "sortfield": "clock",
            "sortorder": "ASC"
        },
        "auth": auth_token,
        "id": 4
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    history_data = response.json().get('result', [])
    if not history_data:
        print("No historical data found, trying to fetch trend data...")
        history_data = fetch_item_trends(session, auth_token, item_id, stime, etime)
    return history_data

# Fetch trend data for older data (if history is unavailable)
def fetch_item_trends(session, auth_token, item_id, stime, etime):
    payload = {
        "jsonrpc": "2.0",
        "method": "trend.get",
        "params": {
            "output": ["clock", "num", "value_min", "value_avg", "value_max"],
            "itemids": item_id,
            "time_from": stime,
            "time_till": etime,
            "sortfield": "clock",
            "sortorder": "ASC"
        },
        "auth": auth_token,
        "id": 5
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    return response.json().get('result', [])

# Determine the most frequent time difference (expected interval)
def determine_expected_interval(history_data):
    time_differences = []
    for i in range(1, len(history_data)):
        time1 = int(history_data[i - 1]['clock'])
        time2 = int(history_data[i]['clock'])
        time_diff = time2 - time1  # Time difference in seconds
        time_differences.append(time_diff)

    # Find the most common time difference (mode)
    time_counter = Counter(time_differences)
    expected_interval, _ = time_counter.most_common(1)[0]
    return expected_interval

# Filter data points that do not match the expected interval
def filter_unexpected_data_points(history_data, expected_interval):
    filtered_data = [history_data[0]]  # Include the first data point
    for i in range(1, len(history_data)):
        time1 = int(history_data[i - 1]['clock'])
        time2 = int(history_data[i]['clock'])
        time_diff = time2 - time1  # Time difference in seconds

        # Include only data points that match the expected interval
        if time_diff == expected_interval:
            filtered_data.append(history_data[i])
    return filtered_data

# Calculate SLA uptime by processing actual data points
def calculate_sla_uptime_improved(history_data, stime, etime):
    total_possible_time = etime - stime  # Total time in seconds
    total_uptime_time = 0

    # Sort history_data by timestamp
    history_data.sort(key=lambda x: int(x['clock']))

    # If no data, return 0% uptime
    if not history_data:
        return 0.0

    # Initialize last_time and last_value
    last_time = stime
    last_value = 1  # Assume uptime before first data point

    for entry in history_data:
        current_time = int(entry['clock'])
        if current_time < stime:
            continue
        if current_time > etime:
            break
        value = int(float(entry.get('value', entry.get('value_avg', 0))))

        # Calculate the time interval since last data point
        time_interval = current_time - last_time

        # If last_value is 1, add time_interval to total uptime
        if last_value == 1:
            total_uptime_time += time_interval

        # Update last_time and last_value
        last_time = current_time
        last_value = value

    # After last data point, if last_value is 1, add remaining time up to etime
    if last_value == 1 and last_time < etime:
        total_uptime_time += etime - last_time

    # Calculate SLA uptime
    sla_uptime = (total_uptime_time / total_possible_time) * 100

    return sla_uptime


# Estimate the expected number of data points based on the average interval
def estimate_expected_data_points(stime, etime, expected_interval):
    total_time = etime - stime  # Total time in seconds
    expected_data_points = total_time // expected_interval
    return expected_data_points

# Calculate SLA uptime with missing data handling
def calculate_sla_uptime(filtered_data, stime, etime, expected_interval):
    expected_data_points = estimate_expected_data_points(stime, etime, expected_interval)
    actual_data_points = len(filtered_data)
    
    # Count missing data and points where value was 0
    missing_data_points = expected_data_points - actual_data_points
    downtime_data_points = 0

    for entry in filtered_data:
        if 'value' in entry and int(entry['value']) == 0:
            downtime_data_points += 1
        elif 'value_avg' in entry and int(float(entry['value_avg'])) == 0:
            downtime_data_points += 1
    
    # Calculate SLA uptime percentage
    uptime_data_points = actual_data_points - downtime_data_points
    sla_uptime = (uptime_data_points / expected_data_points) * 100
    return sla_uptime, missing_data_points, downtime_data_points

# Export historical/trend data to a CSV file
def export_history_to_csv(history_data, host_name, output_dir, item_key):
    output_file = os.path.join(output_dir, f"{host_name}_{item_key}_history_august_2024.csv")
    os.makedirs(output_dir, exist_ok=True)

    with open(output_file, 'w') as f:
        f.write("Timestamp,Value\n")
        for entry in history_data:
            # Convert Unix timestamp to a readable format
            timestamp = datetime.utcfromtimestamp(int(entry['clock'])).strftime('%Y-%m-%d %H:%M:%S')
            if 'value_avg' in entry:  # For trend data
                value = entry['value_avg']
            else:
                value = entry['value']
            f.write(f"{timestamp},{value}\n")

    print(f"Exported historical/trend data to {output_file}")

# Main function to run the script
def main():
    # Get user input for the host name
    host_name = input("Enter the host name: ")

    # Define the time range for August 2024
    start_time = datetime(2024, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2024, 10, 27, 23, 59, 59, tzinfo=timezone.utc)

    stime = int(start_time.timestamp())
    etime = int(end_time.timestamp())

    # Create session and authenticate
    session = requests.Session()
    auth_token = zabbix_login_api(session)

    # Get host ID based on the input host name
    host_id = get_host_id(auth_token, session, host_name)

    # Get the item ID for either ICMP ping or Zabbix agent ping checks
    item_id, item_key = get_ping_item_id(auth_token, session, host_id)

    # Fetch historical or trend data for the ping checks
    history_data = fetch_item_history(session, auth_token, item_id, stime, etime)

    if not history_data:
        print("No data found for the specified time range.")
        sys.exit(1)

    # Define output directory for the CSV file
    output_dir = "/home/almalinux/testing-api"

    # Export the historical/trend data to a CSV file
    export_history_to_csv(history_data, host_name, output_dir, item_key)

    # Determine the expected interval
    expected_interval = determine_expected_interval(history_data)
    print(f"Expected interval between data points (in seconds): {expected_interval}")

    # Calculate the SLA uptime percentage
    sla_uptime = calculate_sla_uptime_improved(history_data, stime, etime)
    print(f"SLA Uptime for the entire period: {sla_uptime:.2f}%")


if __name__ == "__main__":
    main()
