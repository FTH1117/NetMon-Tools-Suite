import base64
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

# Define system prompts for different graph types
SYSTEM_PROMPT_CPU = """
Give professional IT observation and comment for this monthly CPU utilization graph of multiple hosts. Identify any anomalies, trends, or concerns regarding CPU usage over the reported period.
"""

SYSTEM_PROMPT_MEMORY = """
Give professional IT observation and comment for this monthly Memory utilization graph of multiple hosts. Identify any anomalies, trends, or concerns regarding memory usage over the reported period.
"""

SYSTEM_PROMPT_DISK = """
Give professional IT observation and comment for this monthly Disk usage graph of multiple hosts. Identify any anomalies, trends, or concerns regarding disk space usage over the reported period.
"""

SYSTEM_PROMPT_NETWORK = """
Give professional IT observation and comment for this monthly Network traffic graph of multiple hosts. Identify any anomalies, trends, or concerns regarding network usage over the reported period.
"""

SYSTEM_PROMPT_PING = """
Give professional IT observation and comment for this monthly ping result of multiple hosts graph. When the value is 1, that means the server is up; if the value is 0, that means the server down. The mean value is the server uptime, if any server uptime is not equal to 1, that means the server down at that time, tell me which server and the value.
"""

SYSTEM_PROMPT_UPTIME = """
Give professional IT observation and comment for this monthly Uptime graph of multiple hosts. Identify any periods of downtime or concerns regarding server availability over the reported period.
"""

SYSTEM_PROMPT_OTHER = """
Give professional IT observation and comment for this monthly provided graph of multiple hosts. Identify any anomalies, trends, or concerns over the reported period.
"""

LLAMA_API_URL = "<LLAMA_url>"  # The Llama API endpoint

def get_system_prompt(graph_type):
    if graph_type == 'CPU_Utilization':
        return SYSTEM_PROMPT_CPU
    elif graph_type == 'Memory_Utilization':
        return SYSTEM_PROMPT_MEMORY
    elif graph_type == 'Disk_Usage':
        return SYSTEM_PROMPT_DISK
    elif graph_type == 'Network_Traffic':
        return SYSTEM_PROMPT_NETWORK
    elif graph_type == 'Ping_Result':
        return SYSTEM_PROMPT_PING
    elif graph_type == 'Uptime':
        return SYSTEM_PROMPT_UPTIME
    else:
        return SYSTEM_PROMPT_OTHER

def encode_image_to_base64(image_path):
    """Convert an image file to a base64 encoded string."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image to base64: {e}")
        return None

def perform_llama_analysis(image_path, system_prompt):
    """Perform analysis on the given image using Llama 3.2-Vision."""
    base64_image = encode_image_to_base64(image_path)
    if not base64_image:
        print("Failed to encode image. Skipping Llama analysis.")
        return None

    headers = {
        'Content-Type': 'application/json'
    }

    payload = {
        "model": "llama3.2-vision:11b",
        "role": "user",
        "system": "",
        "template": "",
        "prompt": system_prompt,
        "images": [base64_image],
        "stream": False
    }

    try:
        print("Performing Llama analysis...")
        response = requests.post(
            LLAMA_API_URL,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()  # Raise an exception for HTTP errors
        response_json = response.json()
        # Extract the analysis from the 'response' key
        return response_json.get("response", "")
    except Timeout:
        print("Error: Request to Llama API timed out.")
        return None
    except ConnectionError as e:
        print(f"Error: Failed to connect to Llama API. Details: {e}")
        return None
    except RequestException as e:
        print(f"Error during Llama API request: {e}")
        print(f"Response content: {response.content.decode() if response else 'No response'}")
        return None
    except ValueError as e:
        print(f"Error parsing JSON response from Llama API: {e}")
        print(f"Response content: {response.content.decode() if response else 'No response'}")
        return None
