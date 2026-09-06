from dotenv import load_dotenv
import os, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

print("Script started")

load_dotenv()
API_KEY = os.getenv("ETHERSCAN_API_KEY")
print("API Key loaded:", API_KEY)

address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist&address={address}&sort=desc&apikey={API_KEY}"

# Set up a session with retry logic
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

print("Calling API...")
try:
    response = session.get(url, timeout=15)
    print("Status code:", response.status_code)
    data = response.json()
    print("Status:", data.get('status'))
    print("Message:", data.get('message'))
    print("First 2 transactions:", data.get('result')[:2] if isinstance(data.get('result'), list) else data.get('result'))
except requests.exceptions.RequestException as e:
    print("Request failed:", e)