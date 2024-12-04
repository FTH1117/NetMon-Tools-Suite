import requests
import os
import sys
import argparse
from datetime import datetime, timezone
import calendar
from collections import Counter
import statistics

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
        print("Failed to authenticate with Zabbix API.", file=sys.stderr)
        sys.exit(1)

def get_directory_name(host_name, project_id, project_name):
    parts = host_name.split(' - ')
    project_id = project_id.strip()
    project_name = project_name.strip()
    # Remove parts that are equal to project_id or project_name (after stripping whitespace)
    filtered_parts = [part.strip() for part in parts if part.strip() != project_id and part.strip() != project_name]
    # Optionally, limit to parts up to the third '- '
    # If you want to remove parts after the third '- ', uncomment the next line
    # filtered_parts = filtered_parts[:2]  # Keep only the first two parts after filtering
    directory_name = ' - '.join(filtered_parts)
    return directory_name



# Function to get items related to Disk space usage
def get_disk_space_items(auth_token, session, host_id):
    payload = {
        "jsonrpc": "2.0",
        "method": "item.get",
        "params": {
            "output": ["itemid", "name"],
            "hostids": host_id,
            "search": {
                "name": "Disk space usage"
            },
            "searchByAny": True
        },
        "auth": auth_token,
        "id": 8
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    result = response.json()
    if 'result' in result:
        return result['result']
    else:
        print(f"Failed to retrieve Disk space usage items for host ID {host_id}")
        return []

# Download pie chart image using the web session cookie
def download_pie_chart(session, graph_id, stime, etime, output_path):
    chart_url = f"{ZABBIX_URL}/chart6.php"

    # Format 'from' and 'to' as 'YYYY-MM-DD HH:MM:SS'
    from_str = datetime.utcfromtimestamp(stime).strftime('%Y-%m-%d %H:%M:%S')
    to_str = datetime.utcfromtimestamp(etime).strftime('%Y-%m-%d %H:%M:%S')

    params = {
        "graphid": graph_id,
        "from": from_str,
        "to": to_str,
        "type": 2,  # 2 for Pie chart
        "profileIdx": "web.charts.filter",
        "width": 900,
        "height": 600
    }

    print(f"Downloading pie chart with parameters: {params}")

    response = session.get(chart_url, params=params, stream=True)

    if response.headers.get('Content-Type', '').startswith('image/'):
        with open(output_path, 'wb') as img_file:
            img_file.write(response.content)
        print(f"Pie chart {graph_id} saved to {output_path}")
    else:
        print(f"Failed to download pie chart {graph_id}. Received non-image content.")
        print(f"Response status code: {response.status_code}")
        print("Response content (for debugging):", response.text)
        print(f"Request URL: {response.url}")



# Perform web login to obtain session cookie
def zabbix_web_login(session):
    login_url = f"{ZABBIX_URL}/index.php"
    data = {"name": USERNAME, "password": PASSWORD, "autologin": 1, "enter": "Sign in"}
    response = session.post(login_url, data=data)
    if "zbx_session" in session.cookies or "zbx_sessionid" in session.cookies:
        print("Successfully logged in to the Zabbix web interface.")
    else:
        print("Failed to log in to the Zabbix web interface.", file=sys.stderr)
        sys.exit(1)

# Get host group ID from name
def get_hostgroup_id(auth_token, session, group_name):
    payload = {
        "jsonrpc": "2.0",
        "method": "hostgroup.get",
        "params": {"output": ["groupid"], "filter": {"name": [group_name]}},
        "auth": auth_token,
        "id": 2
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    result = response.json()
    if result['result']:
        group_id = result['result'][0]['groupid']
        print(f"Found host group '{group_name}' with ID {group_id}")
        return group_id
    else:
        print(f"Host group '{group_name}' not found.")
        sys.exit(1)

# Get hosts under the host group and ensure they are enabled
def get_hosts(auth_token, session, group_id):
    payload = {
        "jsonrpc": "2.0",
        "method": "host.get",
        "params": {
            "output": ["hostid", "name"],
            "groupids": group_id,
            "filter": {
                "status": 0  # 0 for enabled hosts only
            }
        },
        "auth": auth_token,
        "id": 3
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    result = response.json()
    hosts = result.get('result', [])
    print(f"Retrieved enabled hosts for group ID {group_id}:")
    for host in hosts:
        print(f"ID: {host['hostid']}, Name: {host['name']}")
    return hosts

# Get graphs for a host
def get_graphs(auth_token, session, host_id, search_terms=None):
    if search_terms is None:
        search_terms = ["CPU utilization", "Memory utilization", "Fortinet Uptime", "Disk space usage", "Network"]

    payload = {
        "jsonrpc": "2.0",
        "method": "graph.get",
        "params": {
            "output": ["graphid", "name"],
            "hostids": host_id,
            "search": {
                "name": search_terms
            },
            "searchByAny": True
        },
        "auth": auth_token,
        "id": 4
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    return response.json()['result']



# Download graph image using the web session cookie
def download_graph(session, graph_id, stime, etime, output_path):
    graph_url = f"{ZABBIX_URL}/chart2.php"

    # Format 'from' and 'to' as 'YYYY-MM-DD HH:MM:SS'
    from_str = datetime.utcfromtimestamp(stime).strftime('%Y-%m-%d %H:%M:%S')
    to_str = datetime.utcfromtimestamp(etime).strftime('%Y-%m-%d %H:%M:%S')

    params = {
        "graphid": graph_id,
        "width": 900,
        "height": 200,
        "from": from_str,
        "to": to_str,
        "profileIdx": "web.charts.filter"
    }

    print(f"Downloading graph with parameters: {params}")

    response = session.get(graph_url, params=params, stream=True)

    if response.headers.get('Content-Type', '').startswith('image/'):
        with open(output_path, 'wb') as img_file:
            img_file.write(response.content)
        print(f"Graph {graph_id} saved to {output_path}")
    else:
        print(f"Failed to download graph {graph_id}. Received non-image content.")
        print(f"Response status code: {response.status_code}")
        print("Response content (for debugging):", response.text)
        print(f"Request URL: {response.url}")

# Export graphs for each customer
def export_graphs_for_customer(customer_dir, specified_month, specified_year):
    # Load customer details
    with open(os.path.join(customer_dir, "customer_details.txt"), "r") as f:
        details = dict(line.strip().split(": ", 1) for line in f if ": " in line)

    project_id = details.get("Project ID")
    project_name = details.get("Project Name")
    hostgroup_name = details.get("Host Group Name", project_name)

    print(f"Processing customer: {project_id} - {project_name}")

    # Set up output directory for the specified month and year
    output_dir = os.path.join(customer_dir, f"{specified_year}-{specified_month:02d}")
    os.makedirs(output_dir, exist_ok=True)

    # Calculate start and end of the specified month as Unix timestamps
    first_day = datetime(specified_year, specified_month, 1, tzinfo=timezone.utc)
    last_day = datetime(
        specified_year,
        specified_month,
        calendar.monthrange(specified_year, specified_month)[1],
        23, 59, 59,
        tzinfo=timezone.utc
    )

    # Convert to Unix timestamps
    stime = int(first_day.timestamp())
    etime = int(last_day.timestamp())

    print(f"Start time (stime): {stime} ({first_day})")
    print(f"End time (etime): {etime} ({last_day})")

    # Create session and authenticate
    session = requests.Session()
    auth_token = zabbix_login_api(session)
    zabbix_web_login(session)

    # Get host group ID
    group_id = get_hostgroup_id(auth_token, session, hostgroup_name)
    print(f"Using host group ID: {group_id}")

    # Common search terms
    search_terms_common = ["Uptime", "CPU utilization", "Memory utilization", "Disk space usage", "Network"]


    # Get hosts and download graphs
    hosts = get_hosts(auth_token, session, group_id)
    for host in hosts:
        host_id = host['hostid']
        host_name = host['name']
        directory_name = get_directory_name(host_name, project_id, project_name)
        host_dir = os.path.join(output_dir, directory_name)
        os.makedirs(host_dir, exist_ok=True)

        # Fetch 'icmp' graphs separately
        graphs_icmp = get_graphs(auth_token, session, host_id, search_terms=["icmp"])

        # If no 'icmp' graphs are found, try 'ping'
        if not graphs_icmp:
            print(f"No graphs containing 'icmp' found for host {host_name}. Trying 'ping'.")
            graphs_ping = get_graphs(auth_token, session, host_id, search_terms=["ping"])
            graphs_icmp_or_ping = graphs_ping
        else:
            graphs_icmp_or_ping = graphs_icmp

        # Fetch common graphs
        graphs_common = get_graphs(auth_token, session, host_id, search_terms=search_terms_common)

        # Combine all graphs, avoiding duplicates
        graph_ids = set()
        all_graphs = []
        for graph in graphs_icmp_or_ping + graphs_common:
            if graph['graphid'] not in graph_ids:
                graph_ids.add(graph['graphid'])
                all_graphs.append(graph)

        # Process all graphs
        for graph in all_graphs:
            graph_id = graph['graphid']
            graph_name = graph['name'].replace('/', '^').replace('\\', '_')

            # Check if the graph name is "Disk space usage"
            if "Disk space usage" in graph['name']:
                output_file = os.path.join(host_dir, f"{graph_name}_{stime}.png")
                download_pie_chart(session, graph_id, stime, etime, output_file)
            else:
                # For other graphs, use the regular download_graph function
                output_file = os.path.join(host_dir, f"{graph_name}_{stime}.png")
                download_graph(session, graph_id, stime, etime, output_file)

        # Get the "Disk space usage" graphs separately (if needed)
        # If you want to ensure all "Disk space usage" graphs are included, regardless of previous steps
        disk_graphs = get_graphs(auth_token, session, host_id, search_terms=["Disk space usage"])
        for graph in disk_graphs:
            if "Disk space usage" in graph['name']:
                graph_id = graph['graphid']
                graph_name = graph['name'].replace('/', '^').replace('\\', '_')
                output_file = os.path.join(host_dir, f"{graph_name}_{stime}.png")
                download_pie_chart(session, graph_id, stime, etime, output_file)

        # --- SLA Calculation Starts Here ---
        # Get ping item ID
        item_id, item_key = get_ping_item_id(auth_token, session, host_id)
        if item_id is None:
            print(f"Skipping SLA calculation for host '{host_name}' due to missing ping item.")
            continue  # Skip to the next host

        # Fetch historical and trend data
        combined_data = fetch_item_history(session, auth_token, item_id, stime, etime)
        if not combined_data:
            print(f"No data found for host '{host_name}'. Skipping SLA calculation.")
            continue

        # Determine expected interval
        expected_interval = determine_expected_interval(combined_data)
        if expected_interval is None:
            print(f"Cannot determine expected interval for host '{host_name}'. Skipping SLA calculation.")
            continue

        # Calculate SLA uptime using the improved function
        sla_uptime, missing_data_points, downtime_data_points = calculate_sla_uptime_trend_data(
            combined_data, stime, etime, expected_interval
        )




        print(f"SLA Uptime for host '{host_name}': {sla_uptime:.2f}%")

        # Export historical data to CSV
        csv_output_file = os.path.join(host_dir, f"{host_name}_{item_key}_history_{specified_year}_{specified_month:02d}.csv")
        export_history_to_csv(combined_data, csv_output_file)

        # Write SLA uptime to a text file
        sla_output_file = os.path.join(host_dir, f"{host_name}_SLA_{specified_year}_{specified_month:02d}.txt")
        with open(sla_output_file, 'w') as f:
            f.write(f"SLA Uptime: {sla_uptime:.2f}%\n")
            f.write(f"Missing Data Points: {missing_data_points}\n")
            f.write(f"Downtime Data Points: {downtime_data_points}\n")
        # --- SLA Calculation Ends Here ---

    print(f"Graphs saved to '{output_dir}' for customer '{project_id}'.")

def get_ping_item_id(auth_token, session, host_id):
    item_keys = ["icmpping", "agent.ping"]
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
            "id": 5
        }
        response = session.post(ZABBIX_API_URL, json=payload)
        result = response.json()
        if result['result']:
            item_id = result['result'][0]['itemid']
            print(f"Found {key} item ID: {item_id} for host ID: {host_id}")
            return item_id, key
    print(f"No ICMP ping or agent ping item found for host with ID {host_id}.")
    return None, None  # Return None if no item is found

def fetch_item_history(session, auth_token, item_id, stime, etime):
    # Fetch history data
    history_data = []
    for history_type in [3, 0]:  # 3: Unsigned integer, 0: Numeric float
        payload = {
            "jsonrpc": "2.0",
            "method": "history.get",
            "params": {
                "output": "extend",
                "history": history_type,
                "itemids": item_id,
                "time_from": stime,
                "time_till": etime,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": 100000  # Adjust as needed
            },
            "auth": auth_token,
            "id": 6
        }
        response = session.post(ZABBIX_API_URL, json=payload)
        result = response.json().get('result', [])
        history_data.extend(result)
        print(f"Fetched {len(result)} history data points for history type {history_type}")
    
    # Fetch trend data
    payload = {
        "jsonrpc": "2.0",
        "method": "trend.get",
        "params": {
            "output": ["itemid", "clock", "num", "value_min", "value_avg", "value_max"],
            "itemids": item_id,
            "time_from": stime,
            "time_till": etime,
            "sortfield": "clock",
            "sortorder": "ASC",
            "limit": 100000  # Adjust as needed
        },
        "auth": auth_token,
        "id": 7
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    trend_data = response.json().get('result', [])
    print(f"Fetched {len(trend_data)} trend data points")

    # Merge history and trend data
    combined_data = []
    # Convert history data entries to have 'value_avg' for consistency
    for entry in history_data:
        entry['value_avg'] = entry['value']
        combined_data.append(entry)
    # Add trend data entries
    combined_data.extend(trend_data)

    # Sort combined data by timestamp
    combined_data.sort(key=lambda x: int(x['clock']))
    print(f"Total combined data points: {len(combined_data)}")

    return combined_data


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
        "id": 7
    }
    response = session.post(ZABBIX_API_URL, json=payload)
    return response.json().get('result', [])

def determine_expected_interval(combined_data):
    time_differences = [
        int(combined_data[i]['clock']) - int(combined_data[i - 1]['clock'])
        for i in range(1, len(combined_data))
    ]
    if not time_differences:
        print("Insufficient data to determine expected interval.")
        return None

    # Try to find a consistent interval over 5 consecutive time differences
    for start_index in range(len(time_differences) - 4):
        intervals = time_differences[start_index:start_index+5]
        if len(set(intervals)) == 1:
            expected_interval = intervals[0]
            print(f"Determined expected interval from consistent intervals: {expected_interval} seconds")
            return expected_interval
    print("Unable to determine a consistent expected interval from the data.")
    return None




def calculate_sla_uptime_trend_data(combined_data, stime, etime, expected_interval):
    total_possible_time = etime - stime
    total_uptime = 0
    total_downtime = 0

    data_len = len(combined_data)
    if data_len == 0 or expected_interval is None:
        print("No data available or expected interval could not be determined for uptime calculation.")
        sla_uptime = 0.0
        return sla_uptime, 0, 0

    # Initialize previous timestamp and value
    previous_time = stime
    previous_value = 1  # Assume host was up at the start

    for entry in combined_data:
        data_time = int(entry['clock'])
        value_avg = float(entry.get('value_avg', entry.get('value', 0)))

        # Skip data outside the time range
        if data_time < previous_time or data_time > etime:
            continue

        # Calculate interval from previous time
        interval = data_time - previous_time

        # Check for missing data
        if interval > expected_interval * 1.5:
            # Consider the extra time as downtime due to missing data
            missing_time = interval - expected_interval
            total_downtime += missing_time

            # For the expected_interval, use previous value to determine uptime/downtime
            if previous_value > 0:
                total_uptime += expected_interval
            else:
                total_downtime += expected_interval
        else:
            # Interval is within expected range
            if previous_value > 0:
                total_uptime += interval
            else:
                total_downtime += interval

        # Update previous values
        previous_time = data_time
        previous_value = 1 if value_avg > 0 else 0

    # Handle any remaining time until etime
    if previous_time < etime:
        interval = etime - previous_time
        if previous_value > 0:
            total_uptime += interval
        else:
            total_downtime += interval

    # Adjust for any overcounting
    total_time_counted = total_uptime + total_downtime
    if total_time_counted > total_possible_time:
        overcount = total_time_counted - total_possible_time
        if total_uptime >= overcount:
            total_uptime -= overcount
        else:
            total_uptime = 0

    sla_uptime = (total_uptime / total_possible_time) * 100
    print(f"Total possible time: {total_possible_time} seconds")
    print(f"Total uptime: {total_uptime} seconds")
    print(f"Total downtime: {total_downtime} seconds")
    print(f"Calculated SLA Uptime: {sla_uptime:.2f}%")
    return sla_uptime, None, None




def export_history_to_csv(combined_data, output_file):
    with open(output_file, 'w') as f:
        f.write("Timestamp,Value\n")
        for entry in combined_data:
            timestamp = datetime.utcfromtimestamp(int(entry['clock'])).strftime('%Y-%m-%d %H:%M:%S')
            value_avg = entry.get('value_avg', entry.get('value', '0'))
            f.write(f"{timestamp},{value_avg}\n")
    print(f"Exported combined data to {output_file}")



# Main function to iterate over the specified customer
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Export Zabbix graphs for a specified month and customer.")
    parser.add_argument("--month", type=int, required=True, help="Month for which to export data (1-12)")
    parser.add_argument("--year", type=int, required=True, help="Year for which to export data (e.g., 2024)")
    parser.add_argument("--customer", type=str, required=True, help="Customer ID or directory name")
    args = parser.parse_args()

    specified_month = args.month
    specified_year = args.year
    customer_id = args.customer

    base_directory = "/home/almalinux"
    customer_dir = os.path.join(base_directory, customer_id)
    if os.path.isdir(customer_dir) and os.path.isfile(os.path.join(customer_dir, "customer_details.txt")):
        export_graphs_for_customer(customer_dir, specified_month, specified_year)
    else:
        print(f"Customer directory '{customer_dir}' not found or missing 'customer_details.txt'.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

