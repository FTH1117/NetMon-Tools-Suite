import requests
import os
import sys
import argparse
from datetime import datetime, timezone
import calendar
import urllib3
import shutil

# Disable SSL warnings if you are using self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------- Configuration -------------------

# Grafana API details
BASE_URL = '<GRAFANA_URL>'
API_KEY = '<GRAFANA_API>'  # Replace with your Grafana API key

# Base directory where customer directories are located
BASE_DIRECTORY = "/home/almalinux"

# Minimum content length to consider that the graph has data
MIN_CONTENT_LENGTH = 10000  # Adjust this value as needed (in bytes)

# ------------------------------------------------------

def get_category_from_title(panel_title):
    title_lower = panel_title.lower()
    if 'cpu' in title_lower:
        return 'CPU_Utilization'
    elif 'memory' in title_lower:
        return 'Memory_Utilization'
    elif 'disk' in title_lower or 'storage' in title_lower:
        return 'Disk_Usage'
    elif 'network traffic' in title_lower:
        return 'Network_Traffic'
    elif 'network usage' in title_lower:
        return 'Network_Usage'
    elif 'ping' in title_lower:
        return 'Ping_Result'
    elif 'uptime' in title_lower:
        return 'Uptime'
    else:
        return 'Others'


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Export Grafana graphs for a specified month and customer.")
    parser.add_argument("--month", type=int, required=True, help="Month for which to export data (1-12)")
    parser.add_argument("--year", type=int, required=True, help="Year for which to export data (e.g., 2024)")
    parser.add_argument("--customer", type=str, required=True, help="Customer ID or directory name")
    args = parser.parse_args()

    specified_month = args.month
    specified_year = args.year
    project_id = args.customer

    base_directory = BASE_DIRECTORY
    customer_dir = os.path.join(base_directory, project_id)
    if not os.path.isdir(customer_dir) or not os.path.isfile(os.path.join(customer_dir, "customer_details.txt")):
        print(f"Customer directory '{customer_dir}' not found or missing 'customer_details.txt'.", file=sys.stderr)
        sys.exit(1)

    # Load customer details
    with open(os.path.join(customer_dir, "customer_details.txt"), "r") as f:
        details = dict(line.strip().split(": ", 1) for line in f if ": " in line)

    dashboard_uid = details.get("Dashboard UID")
    hostgroup_name = details.get("Host Group Name")
    project_name = details.get("Project Name", "")
    if not dashboard_uid:
        print("Dashboard UID not found in customer_details.txt", file=sys.stderr)
        sys.exit(1)
    if not hostgroup_name:
        print("Host Group Name not found in customer_details.txt", file=sys.stderr)
        sys.exit(1)

    # Calculate start and end of the specified month as Unix timestamps in milliseconds
    first_day = datetime(specified_year, specified_month, 1, tzinfo=timezone.utc)
    last_day = datetime(
        specified_year,
        specified_month,
        calendar.monthrange(specified_year, specified_month)[1],
        23, 59, 59,
        tzinfo=timezone.utc
    )
    FROM_TS = int(first_day.timestamp() * 1000)
    TO_TS = int(last_day.timestamp() * 1000)

    # Create output directory for the specified month and year
    output_dir = os.path.join(customer_dir, f"{specified_year}-{specified_month:02d}")
    # Check if the directory exists and delete if it does
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
        print(f"Existing directory {output_dir} removed.")
    os.makedirs(output_dir, exist_ok=True)

    # Set up headers for authentication
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json',
    }

    # Fetch the dashboard JSON
    dashboard_url = f'{BASE_URL}/api/dashboards/uid/{dashboard_uid}'
    response = requests.get(dashboard_url, headers=headers, verify=False)

    if response.status_code != 200:
        print(f'Failed to get dashboard: {response.status_code}, {response.text}')
        sys.exit(1)

    dashboard_json = response.json()

    # Function to recursively extract all panels
    # def get_panels(panel_list, category=None):
    #     panels = []
    #     for panel in panel_list:
    #         if panel.get('type') == 'row':
    #             new_category = panel.get('title', category)
    #             if 'panels' in panel:
    #                 panels.extend(get_panels(panel['panels'], new_category))
    #         else:
    #             panels.append((panel, category))
    #     return panels

    # panels_with_categories = get_panels(dashboard_json['dashboard']['panels'])

    # Iterate over each panel and download the graph image
    for panel in dashboard_json['dashboard']['panels']:
        panel_id = panel['id']
        panel_title = panel.get('title', f'panel_{panel_id}')
        # Remove host group name from panel title if it exists
        if ' for ' in panel_title:
            panel_title = panel_title.split(' for ')[0].strip()
            
        panel_title_safe = ''.join(c for c in panel_title if c.isalnum() or c in (' ', '_', '-')).rstrip()

        # Get category based on panel title
        category = get_category_from_title(panel_title)
        category_safe = category  # Already safe from the function

        print(f'Downloading panel {panel_id}: {panel_title}, Category: {category_safe}')

        # Build the directory path
        category_dir = os.path.join(output_dir, category_safe)
        os.makedirs(category_dir, exist_ok=True)
        filename = os.path.join(category_dir, f'{panel_title_safe}.png')

        render_url = f'{BASE_URL}/render/d-solo/{dashboard_uid}'

        # Get number of queries in the panel
        if 'targets' in panel and isinstance(panel['targets'], list):
            number_of_queries = len(panel['targets'])
        else:
            number_of_queries = 0  # Default to 0 if no queries are found

        # Calculate panel height based on the number of queries
        BASE_HEIGHT = 500         # Base height for up to BASE_QUERIES queries
        BASE_QUERIES = 18         # Number of queries that fit in the base height
        DEFAULT_HEIGHT_PER_EXTRA_QUERY = 25  # Default additional height per query beyond BASE_QUERIES
        REDUCED_HEIGHT_PER_EXTRA_QUERY = 23  # Reduced height per query when queries >= 80

        if number_of_queries <= BASE_QUERIES:
            panel_height = BASE_HEIGHT
        else:
            extra_queries = number_of_queries - BASE_QUERIES
            
            # Determine which height per extra query to use
            if number_of_queries >= 90:
                height_per_extra_query = REDUCED_HEIGHT_PER_EXTRA_QUERY
            else:
                height_per_extra_query = DEFAULT_HEIGHT_PER_EXTRA_QUERY
            
            # Calculate the total panel height
            panel_height = BASE_HEIGHT + (extra_queries * height_per_extra_query)

        params = {
            'panelId': panel_id,
            'from': FROM_TS,
            'to': TO_TS,
            'width': 1500,
            'height': panel_height,
            'tz': 'UTC',
        }

        render_response = requests.get(render_url, headers=headers, params=params, verify=False)

        if render_response.status_code == 200:
            # Check if the graph has data
            if len(render_response.content) < MIN_CONTENT_LENGTH:
                print(f"Graph '{panel_title}' has no data. Skipping.")
                continue

            # If the panel is the "Network Traffic", save it in 'network' directory
            # if panel_title == "Network Traffic":
            #     network_dir = os.path.join(output_dir, 'network')
            #     os.makedirs(network_dir, exist_ok=True)
            #     filename = os.path.join(network_dir, f'{panel_title_safe}.png')
            # else:
            #     filename = os.path.join(output_dir, f'{panel_title_safe}.png')
            with open(filename, 'wb') as f:
                f.write(render_response.content)
            print(f'Saved {filename}')
        else:
            print(f'Failed to render panel {panel_id}: {render_response.status_code}, {render_response.text}')

    print(f"Graphs saved to '{output_dir}' for customer '{project_id}'.")

if __name__ == "__main__":
    main()
