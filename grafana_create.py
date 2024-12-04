import requests
import json
import re
import sys
import argparse
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Disable warnings for insecure HTTPS requests
requests.packages.urllib3.disable_warnings()

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Create Grafana dashboard for a host group.')
parser.add_argument('--host_group_name', required=True, help='Name of the host group')
parser.add_argument('--server_tag', action='append', help='Server tag')
parser.add_argument('--rack', action='append', help='Rack')
args = parser.parse_args()

host_group_name = args.host_group_name
server_tags = args.server_tag or []
racks = args.rack or []

# Check if server_tags and racks are provided
if server_tags and racks:
    if len(server_tags) != len(racks):
        logger.error("Number of server tags and racks must be equal.", file=sys.stderr)
        sys.exit(1)
else:
    logger.info("No server tags and racks provided. Skipping network hosts processing.")

# Predefined graph keywords
graph_search_criteria = [
    {
        "panel_title": "Ping Result",
        "search_terms": ["ICMP ping"],  # First priority
        "alternative_search_terms": ["Zabbix agent ping", "Ping_Check"],  # Second and third priority
        "additional_filters": [],
        "exclude_filters": [],
        "search_wildcards_enabled": False,
        "search_by_any": False,  # Ensure that all terms in search_terms must be present
        "search_case_insensitive": True
    },
    {
        "panel_title": "CPU utilization",
        "search_terms": ["CPU utilization"],
        "additional_filters": [],
        "search_wildcards_enabled": False,
        "search_by_any": False,
        "search_case_insensitive": True
    },
    {
        "panel_title": "Memory utilization",
        "search_terms": ["Memory utilization"],
        "additional_filters": [],
        "search_wildcards_enabled": False,
        "search_by_any": False,
        "search_case_insensitive": True
    },
    {
        "panel_title": "Uptime",
        "search_terms": ["uptime"],
        "additional_filters": [],
        "search_wildcards_enabled": False,
        "search_by_any": False,
        "search_case_insensitive": True
    },
        {
        "panel_title": "Disk Space Usage",
        "search_terms": ["space"],
        "additional_filters": ["percentage", "%", "utilization"],
        "exclude_filters": ["Free swap space", "Used swap space", "datastore"],
        "search_wildcards_enabled": False,
        "search_by_any": False,
        "search_case_insensitive": True
    },
        {
        "panel_title": "Network Usage",
        "search_terms": ["Interface", "Bits"],
        "additional_filters": [],
        "search_wildcards_enabled": False,
        "search_by_any": False,
        "search_case_insensitive": True
    }
]


# Zabbix API details
zabbix_url = "<ZABBIX_URL>"
zabbix_user = "<ZABBIX_USER>"
zabbix_password = "<ZABBIX_PASSWORD>"

# Grafana API details
grafana_url = "<GRAFANA_URL>"
grafana_api_key = "<GRAFANA_PASSWORD>"  # Replace with your actual Grafana API key

# Data source names
zabbix_datasource_name = "<ZABBIX_DATASOURCE_NAME>"
network_zabbix_datasource_name = "<NETWORK_ZABBIX_DATASOURCE_NAME>"

# Network Zabbix API details
network_zabbix_url = "<NETWORK_ZABBIX_URL>"
network_zabbix_user = "<NETWORK_ZABBIX_USER>"
network_zabbix_password = "<NETWORK_ZABBIX_PASSWORD>"

### Function Definitions ###

def zabbix_login_api(zabbix_api_url, username, password):
    payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {"user": username, "password": password},
        "id": 1,
        "auth": None
    }
    response = requests.post(zabbix_api_url, json=payload, verify=False)
    result = response.json()
    if 'result' in result:
        return result['result']
    else:
        logger.error("Failed to authenticate with Zabbix API.", file=sys.stderr)
        return None

def get_items_matching_keywords(auth_token, zabbix_api_url, host_id, search_terms, search_wildcards_enabled=False, search_by_any=False, search_case_insensitive=True):
    payload = {
        "jsonrpc": "2.0",
        "method": "item.get",
        "params": {
            "output": ["itemid", "name", "key_"],
            "hostids": host_id,
            "search": {
                "name": search_terms
            },
            "searchCaseInsensitive": search_case_insensitive,
            "searchWildcardsEnabled": search_wildcards_enabled,
            "searchByAny": search_by_any
        },
        "auth": auth_token,
        "id": 4
    }
    response = requests.post(zabbix_api_url, json=payload, verify=False)
    result = response.json()
    return result.get('result', [])


def get_hosts(auth_token, zabbix_api_url, rack):
    payload = {
        "jsonrpc": "2.0",
        "method": "host.get",
        "params": {
            "output": ["hostid", "host", "name"],
            "search": {
                "host": rack,
                "name": rack
            },
            "selectGroups": ["name"],
            "searchCaseInsensitive": True
        },
        "auth": auth_token,
        "id": 2
    }
    response = requests.post(zabbix_api_url, json=payload, verify=False)
    result = response.json()
    hosts = result.get('result', [])
    return hosts

def get_items(auth_token, zabbix_api_url, host_id, server_tag):
    payload = {
        "jsonrpc": "2.0",
        "method": "item.get",
        "params": {
            "output": ["itemid", "name", "key_"],
            "hostids": host_id,
            "search": {
                "name": server_tag
            },
            "searchCaseInsensitive": True
        },
        "auth": auth_token,
        "id": 3
    }
    response = requests.post(zabbix_api_url, json=payload, verify=False)
    return response.json().get('result', [])

def get_alias(host_name):
    import re
    # Define regex patterns for IPv4 and IPv6
    ipv4_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    ipv6_pattern = r'\b(?:[0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{1,4}\b'
    ip_pattern = f'({ipv4_pattern}|{ipv6_pattern})'

    # Search for IP address
    ip_match = re.search(ip_pattern, host_name)
    ip_address = ip_match.group(0) if ip_match else ''

    # Extract the last part after the last '-'
    parts = host_name.split(' - ')
    host_detail = parts[-1].strip() if len(parts) >= 1 else host_name.strip()

    # Build alias
    alias = f"{ip_address} - {host_detail}" if ip_address else host_detail
    return alias




def sanitize_ref_id(s, suffix=''):
    # Replace non-alphanumeric characters with underscores
    s = re.sub(r'\W+', '_', s)
    # Calculate available length for the base part
    max_length = 64 - len(suffix)
    if max_length <= 0:
        # If suffix length exceeds 64, raise an error
        raise ValueError("Suffix length exceeds maximum refId length.")
    # Truncate the base string to fit within the limit
    s = s[:max_length] if s else f"default_ref_{uuid.uuid4().hex[:8]}"
    return s + suffix

### Main Script ###

# Authenticate with Zabbix APIs
zabbix_auth_token = zabbix_login_api(zabbix_url, zabbix_user, zabbix_password)
if not zabbix_auth_token:
    logger.error("Failed to authenticate with Zabbix API.", file=sys.stderr)
    sys.exit(1)

network_auth_token = zabbix_login_api(network_zabbix_url, network_zabbix_user, network_zabbix_password)
if not network_auth_token:
    logger.error("Failed to authenticate with Network Zabbix API.", file=sys.stderr)
    sys.exit(1)

# Get host group ID
payload = {
    "jsonrpc": "2.0",
    "method": "hostgroup.get",
    "params": {
        "filter": {
            "name": [host_group_name]
        }
    },
    "auth": zabbix_auth_token,
    "id": 2
}
response = requests.post(zabbix_url, json=payload, verify=False)
response.raise_for_status()
host_groups = response.json().get('result', [])
if not host_groups:
    logger.error("Host group not found.", file=sys.stderr)
    sys.exit(1)
host_group_id = host_groups[0]['groupid']

# Get hosts in the host group
payload = {
    "jsonrpc": "2.0",
    "method": "host.get",
    "params": {
        "groupids": host_group_id,
        "output": ["hostid", "host"]
    },
    "auth": zabbix_auth_token,
    "id": 3
}
response = requests.post(zabbix_url, json=payload, verify=False)
response.raise_for_status()
hosts = response.json().get('result', [])
if not hosts:
    logger.error("No hosts found in the host group.", file=sys.stderr)
    sys.exit(1)

# Prepare a mapping of host IDs to items matching search criteria
host_items_map = {}
for host in hosts:
    host_id = host['hostid']
    host_name = host['host']
    items = {}
    for criteria in graph_search_criteria:
        panel_title = criteria['panel_title']
        search_terms = criteria['search_terms']
        alternative_search_terms = criteria.get('alternative_search_terms', [])
        additional_filters = criteria.get('additional_filters', [])
        exclude_filters = criteria.get('exclude_filters', [])
        search_wildcards_enabled = criteria.get('search_wildcards_enabled', False)
        search_by_any = criteria.get('search_by_any', False)
        search_case_insensitive = criteria.get('search_case_insensitive', True)

        # Initialize matching_items
        matching_items = []

        # First, try to get items matching the primary search_terms
        matching_items = get_items_matching_keywords(
            zabbix_auth_token, zabbix_url, host_id,
            search_terms,
            search_wildcards_enabled=search_wildcards_enabled,
            search_by_any=search_by_any,
            search_case_insensitive=search_case_insensitive
        )

        # If no items are found, try alternative search terms sequentially
        if not matching_items and alternative_search_terms:
            for alt_term in alternative_search_terms:
                matching_items = get_items_matching_keywords(
                    zabbix_auth_token, zabbix_url, host_id,
                    [alt_term],  # Pass as a list
                    search_wildcards_enabled=search_wildcards_enabled,
                    search_by_any=search_by_any,
                    search_case_insensitive=search_case_insensitive
                )
                if matching_items:
                    # Found matching items, break out of the loop
                    break

        # Proceed with existing code to filter matching items
        if matching_items:
            filtered_items = []
            for item in matching_items:
                item_name_lower = item['name'].lower()
                # Check exclude filters first
                if any(exclude.lower() in item_name_lower for exclude in exclude_filters):
                    continue  # Skip this item
                # Now check additional filters if any
                if additional_filters:
                    if any(f.lower() in item_name_lower for f in additional_filters):
                        filtered_items.append(item)
                else:
                    # If no additional filters, include the item
                    filtered_items.append(item)
            matching_items = filtered_items

        if matching_items:
            # Collect all matching item names
            item_names = [item['name'] for item in matching_items]
            items[panel_title] = item_names
        else:
            logger.warning(f"No items found for host '{host_name}' with criteria '{panel_title}'")
    host_items_map[host_name] = items

# Prepare Grafana Dashboard JSON
dashboard = {
    "dashboard": {
        "id": None,
        "uid": None,
        "title": f"{host_group_name}",
        "timezone": "browser",
        "schemaVersion": 30,
        "version": 0,
        "refresh": "5s",
        "panels": []
    },
    "overwrite": True
}

# Determine panel type based on Grafana version
panel_type = "timeseries"  # Adjust based on your Grafana version

# Function to sanitize refId
def sanitize_ref_id(s, suffix=''):
    # Replace non-alphanumeric characters with underscores
    s = re.sub(r'\W+', '_', s)
    # Calculate available length for the base part
    max_length = 64 - len(suffix)
    if max_length <= 0:
        # If suffix length exceeds 64, raise an error
        raise ValueError("Suffix length exceeds maximum refId length.")
    # Truncate the base string to fit within the limit
    s = s[:max_length] if s else f"default_ref_{uuid.uuid4().hex[:8]}"
    return s + suffix




panel_height = 12  # Height of each panel
panel_width = 24   # Width of each panel


# Loop over each search criteria to create panels
for idx_graph, criteria in enumerate(graph_search_criteria):
    panel_title = criteria['panel_title']
    # Calculate grid position
    grid_position = {
        "h": panel_height,
        "w": panel_width,
        "x": 0,
        "y": idx_graph * panel_height  # Stack panels vertically
    }

    # Create a panel for this criteria
    panel = {
        "type": panel_type,
        "title": f"{panel_title} for {host_group_name}",
        "datasource": zabbix_datasource_name,
        "targets": [],
        "gridPos": grid_position,
        "id": idx_graph + 1,
        "fieldConfig": {
            "defaults": {},
            "overrides": []
        },
        "options": {
            "legend": {
                "displayMode": "table",
                "placement": "right",
                "calcs": ["mean", "min", "max"]
            }
        }
    }

    # Collect refIds to ensure uniqueness for this panel
    ref_ids = set()

    # Add a query for each host
    for idx_host, zabbix_host in enumerate(hosts):
        host_name = zabbix_host['host']
        item_names = host_items_map.get(host_name, {}).get(panel_title)
        if not item_names:
            logger.warning(f"No items found for host '{host_name}' and criteria '{panel_title}', skipping.")
            continue

        for item_name in item_names:
            # Use the host name, item name, and panel title to create a unique refId
            ref_id_base = f"{host_name}_{item_name}_{panel_title}"
            ref_id = sanitize_ref_id(ref_id_base)

            # Ensure refId is unique
            original_ref_id = ref_id
            counter = 1
            while ref_id in ref_ids or not ref_id:
                suffix = f"_{counter}"
                ref_id = sanitize_ref_id(original_ref_id, suffix=suffix)
                counter += 1
            ref_ids.add(ref_id)

            if panel_title in ["Disk Space Usage", "Network Usage"]:
                # Include item name
                alias_name = f"{get_alias(host_name)} - {item_name}"
            else:
                # Exclude item name
                alias_name = f"{get_alias(host_name)}"

            target = {
                "refId": ref_id,
                "group": {"filter": host_group_name},
                "host": {"filter": host_name},
                "application": {"filter": ""},
                "item": {"filter": item_name},
                "functions": [
                    {
                        "name": "setAlias",
                        "def": {
                            "name": "setAlias",
                            "category": "Alias",
                            "params": [
                                {
                                    "name": "alias",
                                    "type": "string"
                                }
                            ],
                            "defaultParams": [],
                            "tooltip": "Set legend alias (alias)"
                        },
                        "params": [alias_name],
                        "text": f"setAlias({alias_name})"
                    }
                ],
                "mode": 0,
                "options": {
                    "showDisabledItems": False
                },
                "resultFormat": "time_series",
                "datasource": zabbix_datasource_name,
                "hide": False
            }
            panel['targets'].append(target)

    # Add the panel to the dashboard
    dashboard['dashboard']['panels'].append(panel)

# Process network hosts similarly
if server_tags and racks:
    network_hosts = []
    for server_tag, rack in zip(server_tags, racks):
        rack_hosts = []

        # Check if the rack starts with 'MAH-'
        if rack.startswith('MAH-'):
            rack_hosts = get_hosts(network_auth_token, network_zabbix_url, rack)
            if not rack_hosts:
                aims_rack = 'AIMS-' + rack[len('MAH-'):]
                rack_hosts = get_hosts(network_auth_token, network_zabbix_url, aims_rack)
        else:
            rack_hosts = get_hosts(network_auth_token, network_zabbix_url, rack)

        if not rack_hosts:
            logger.error(f"No hosts found containing rack '{rack}'.", file=sys.stderr)
            continue

        # For each host, check if items matching server_tag exist
        for host in rack_hosts:
            host_id = host['hostid']
            items = get_items(network_auth_token, network_zabbix_url, host_id, server_tag)
            if items:
                network_hosts.append({
                    'host': host['host'],
                    'hostid': host['hostid'],
                    'groups': host['groups'],
                    'server_tag': server_tag
                })

    # Only proceed if network_hosts is not empty
    if network_hosts:
        # Prepare a mapping of network host IDs to items matching "Bits"
        host_items_map_network = {}
        for network_host in network_hosts:
            host_id = network_host['hostid']
            host_name = network_host['host']
            items = {}

            # Define criteria for network data
            panel_title = "Network Traffic"
            search_terms = ["Bits", network_host['server_tag']]  # Use the server_tag from the network_host
            additional_filters = []
            exclude_filters = []
            search_wildcards_enabled = False
            search_by_any = False
            search_case_insensitive = True

            matching_items = get_items_matching_keywords(
                network_auth_token, network_zabbix_url, host_id,
                search_terms,
                search_wildcards_enabled=search_wildcards_enabled,
                search_by_any=search_by_any,
                search_case_insensitive=search_case_insensitive
            )

            if matching_items:
                # Collect all matching item names
                item_names = [item['name'] for item in matching_items]
                items[panel_title] = item_names
            else:
                logger.warning(f"No items found for network host '{host_name}' with criteria '{panel_title}'")
            host_items_map_network[host_name] = items

        # Create the Network Traffic panel
        idx_graph = len(dashboard['dashboard']['panels'])
        panel_title = "Network Traffic"
        grid_position = {
            "h": panel_height,
            "w": panel_width,
            "x": 0,
            "y": idx_graph * panel_height  # Stack panels vertically
        }

        # Create a panel for this criteria
        panel = {
            "type": panel_type,
            "title": f"{panel_title}",
            "datasource": network_zabbix_datasource_name,
            "targets": [],
            "gridPos": grid_position,
            "id": idx_graph + 1,
            "fieldConfig": {
                "defaults": {},
                "overrides": []
            },
            "options": {
                "legend": {
                    "displayMode": "table",
                    "placement": "right",
                    "calcs": ["mean", "min", "max"]
                }
            }
        }

        # Collect refIds to ensure uniqueness for this panel
        ref_ids = set()

        # Add a query for each network host
        for network_host in network_hosts:
            host_name = network_host['host']
            item_names = host_items_map_network.get(host_name, {}).get(panel_title)
            if not item_names:
                logger.warning(f"No items found for network host '{host_name}' and criteria '{panel_title}', skipping.")
                continue

            for item_name in item_names:
                # Use the host name and item name to create a unique refId
                ref_id_base = f"{host_name}_{item_name}"
                ref_id = sanitize_ref_id(ref_id_base)

                # Ensure refId is unique
                original_ref_id = ref_id
                counter = 1
                while ref_id in ref_ids or not ref_id:
                    suffix = f"_{counter}"
                    ref_id = sanitize_ref_id(original_ref_id, suffix=suffix)
                    counter += 1
                ref_ids.add(ref_id)

                # Build the group filter from the host's groups
                group_names = [group['name'] for group in network_host['groups']]
                group_filter = "Network Equipment"

                target = {
                    "refId": ref_id,
                    "group": {"filter": group_filter},
                    "host": {"filter": host_name},
                    "application": {"filter": ""},
                    "item": {"filter": item_name},
                    "functions": [
                        {
                            "name": "setAlias",
                            "def": {
                                "name": "setAlias",
                                "category": "Alias",
                                "params": [
                                    {
                                        "name": "alias",
                                        "type": "string"
                                    }
                                ],
                                "defaultParams": [],
                                "tooltip": "Set legend alias (alias)"
                            },
                            "params": [f"{host_name} - {item_name}"],
                            "text": f"setAlias({host_name} - {item_name})"
                        }
                    ],
                    "mode": 0,
                    "options": {
                        "showDisabledItems": False
                    },
                    "resultFormat": "time_series",
                    "datasource": network_zabbix_datasource_name,
                    "hide": False
                }
                panel['targets'].append(target)

        # Add the panel to the dashboard
        dashboard['dashboard']['panels'].append(panel)
    else:
        logger.info("No network hosts found. Skipping Network Traffic panel creation.")
else:
    logger.info("Server tags and racks not provided. Skipping network hosts processing and Network Traffic panel creation.")

# Prepare headers for Grafana API request
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {grafana_api_key}"
}

# Create Dashboard in Grafana
response = requests.post(grafana_url, headers=headers, data=json.dumps(dashboard), verify=False)
response.raise_for_status()
response_json = response.json()

dashboard_uid = response_json.get('uid')
dashboard_url = response_json.get('url')
status = response_json.get('status')

if status != 'success' or not dashboard_uid:
    logger.error(f"Failed to create dashboard: {response.content}", file=sys.stderr)
    sys.exit(1)

# Output the dashboard UID and URL in JSON format
print(json.dumps({
    "dashboard_uid": dashboard_uid,
    "dashboard_url": dashboard_url
}))
