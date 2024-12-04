import requests

try:
    response = requests.get('http://212.8.231.10:11444/api/generate', timeout=10)
    print('Status Code:', response.status_code)
    print('Response Body:', response.text)
except requests.exceptions.RequestException as e:
    print('Error:', e)
