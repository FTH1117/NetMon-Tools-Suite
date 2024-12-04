import requests
import os
import sys
import argparse
from datetime import datetime, timezone
import calendar

# Network Zabbix server details
ZABBIX_URL = "<NETWORK_ZABBIX_URL>"
ZABBIX_API_URL = f"{ZABBIX_URL}/api_jsonrpc.php"
USERNAME = "<NETWORK_ZABBIX_USER>"
PASSWORD = "<NETWORK_ZABBIX_PASSWORD>"

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

def zabbix_web_login(session):
    login_url = f"{ZABBIX_URL}/index.php"
    data = {"name": USERNAME, "password": PASSWORD, "autologin": 1, "enter": "Sign in"}
    response = session.post(login_url, data=data)
    if "zbx_session" in session.cookies or "zbx_sessionid" in session.cookies:
        print("Successfully logged in to the Zabbix web interface.")
    else:
        print("Failed to log in to the Zabbix web interface.", file=sys.stderr)
        sys.exit(1)

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
    print(f"Payload: {payload}")  # Debugging line
    response = session.post(ZABBIX_API_URL, json=payload)
    result = response.json()
    print(f"Response: {result}")  # Debugging line
    hosts = result.get('result', [])
    print(f"Retrieved hosts containing rack '{rack}':")
    for host in hosts:
        print(f"ID: {host['hostid']}, Host: {host['host']}, Name: {host['name']}")
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
    response = session.post(ZABBIX_API_URL, json=payload)
    return response.json().get('result', [])

def download_graph(session, graph_id, stime, etime, output_path):
    graph_url = f"{ZABBIX_URL}/chart2.php"

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

def export_network_graphs(customer_dir, specified_month, specified_year):
    # Load customer details
    details_path = os.path.join(customer_dir, "customer_details.txt")
    if not os.path.isfile(details_path):
        print(f"Customer details file not found at {details_path}")
        sys.exit(1)
    with open(details_path, "r") as f:
        details = {}
        for line in f:
            if ": " in line:
                key, value = line.strip().split(": ", 1)
                details[key.strip()] = value.strip()

    # Set up output directory under 'network' subdirectory
    output_dir = os.path.join(customer_dir, f"{specified_year}-{specified_month:02d}", "network")
    os.makedirs(output_dir, exist_ok=True)

    project_id = details.get("Project ID")
    project_name = details.get("Project Name")

    # Collect all server tags and racks
    server_tags = []
    racks = []
    i = 1
    while True:
        server_tag = details.get(f"Server Tag {i}")
        rack = details.get(f"Rack {i}")
        if server_tag and rack:
            server_tags.append(server_tag)
            racks.append(rack)
            i += 1
        else:
            break

    if not server_tags:
        print("No Server Tags and Racks found in customer_details.txt.")
        # Proceed without exporting network graphs
        return

    print(f"Processing customer: {project_id} - {project_name}")

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

    # For each server tag and rack, get hosts and graphs
    for idx, (server_tag, rack) in enumerate(zip(server_tags, racks), start=1):
        print(f"Processing Rack {idx}: '{rack}' and Server Tag {idx}: '{server_tag}'")
        # Initialize hosts as empty list
        hosts = []

        # Check if the rack starts with 'MAH-'
        if rack.startswith('MAH-'):
            # Try searching for hosts with 'MAH-<Anything>'
            hosts = get_hosts(auth_token, session, rack)
            if not hosts:
                # If no hosts found, try 'AIMS-<Anything>'
                aims_rack = 'AIMS-' + rack[len('MAH-'):]
                print(f"No hosts found for '{rack}', trying '{aims_rack}'")
                hosts = get_hosts(auth_token, session, aims_rack)
        else:
            # For other racks, search as usual
            hosts = get_hosts(auth_token, session, rack)

        if not hosts:
            print(f"No hosts found containing rack '{rack}'.")
            continue  # Proceed to next server tag and rack

        # For each host, get graphs whose names contain the server tag
        for host in hosts:
            host_id = host['hostid']
            host_name = host['name']
            host_dir = os.path.join(output_dir, f"{host_name}")
            os.makedirs(host_dir, exist_ok=True)

            graphs = get_graphs(auth_token, session, host_id, server_tag)
            if not graphs:
                print(f"No graphs found for host '{host_name}' containing server tag '{server_tag}'.")
                continue

            for graph in graphs:
                graph_id = graph['graphid']
                graph_name = graph['name'].replace('/', '^').replace('\\', '_')

                output_file = os.path.join(host_dir, f"{graph_name}_{stime}.png")
                download_graph(session, graph_id, stime, etime, output_file)

    print(f"Network graphs saved to '{output_dir}' for customer '{project_id}'.")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Export Network Zabbix graphs for a specified month and customer.")
    parser.add_argument("--month", type=int, required=True, help="Month for which to export data (1-12)")
    parser.add_argument("--year", type=int, required=True, help="Year for which to export data (e.g., 2024)")
    parser.add_argument("--customer", type=str, required=True, help="Customer ID or directory name")
    args = parser.parse_args()

    specified_month = args.month
    specified_year = args.year
    customer_id = args.customer

    base_directory = "/home/almalinux"
    customer_dir = os.path.join(base_directory, customer_id)
    if os.path.isdir(customer_dir):
        export_network_graphs(customer_dir, specified_month, specified_year)
    else:
        print(f"Customer directory '{customer_dir}' not found.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
