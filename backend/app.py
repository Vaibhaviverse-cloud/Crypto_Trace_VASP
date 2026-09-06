from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import os, requests, csv
from collections import Counter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()
API_KEY = os.getenv("ETHERSCAN_API_KEY")

app = Flask(__name__)
CORS(app)

session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))


# ---------- VASP DATABASE ----------
def load_vasp_addresses():
    vasp_map = {}
    with open('vasp_addresses.csv', mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vasp_map[row['address'].strip().lower()] = row['vasp_name'].strip()
    return vasp_map


VASP_ADDRESSES = load_vasp_addresses()
print(f"Loaded {len(VASP_ADDRESSES)} VASP addresses")


# ---------- DATA FETCHING ----------
def fetch_transactions(address):
    """Native ETH transactions for an address."""
    url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist&address={address}&sort=desc&apikey={API_KEY}"
    try:
        response = session.get(url, timeout=30)
        data = response.json()
        result = data.get('result', [])
        return result if isinstance(result, list) else []
    except requests.exceptions.RequestException:
        return []


def fetch_token_transfers(address):
    """ERC20 / USDT-style token transfers for an address."""
    url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=tokentx&address={address}&sort=desc&apikey={API_KEY}"
    try:
        response = session.get(url, timeout=30)
        data = response.json()
        result = data.get('result', [])
        return result if isinstance(result, list) else []
    except requests.exceptions.RequestException:
        return []


def fetch_all_activity(address):
    """Combines native + token transfers into one list for matching purposes."""
    native = fetch_transactions(address)
    tokens = fetch_token_transfers(address)
    return native + tokens, native  # combined (for matching), native only (for tx_count/display)


# ---------- MATCHING ----------
def check_direct_match(transactions):
    for tx in transactions:
        from_addr = tx.get('from', '').strip().lower()
        to_addr = tx.get('to', '').strip().lower()
        if from_addr in VASP_ADDRESSES:
            return VASP_ADDRESSES[from_addr]
        if to_addr in VASP_ADDRESSES:
            return VASP_ADDRESSES[to_addr]
    return None


# ---------- SUSPICIOUS PATTERN DETECTION ----------
def detect_flags(transactions):
    flags = []
    values = [tx.get('value') for tx in transactions if tx.get('value') not in (None, '0', '')]
    if values:
        counts = Counter(values)
        most_common_value, freq = counts.most_common(1)[0]
        if freq >= 3:
            flags.append('repeated_equal_value_possible_mixer')
    return flags


# ---------- MAIN ENDPOINT ----------
@app.route('/api/attribute', methods=['GET'])
def attribute():
    address = request.args.get('address', '').strip()
    if not address:
        return jsonify({"error": "address parameter is required"}), 400
    if not address.lower().startswith('0x') or len(address) != 42:
        return jsonify({"error": "invalid Ethereum address format"}), 400

    address_lower = address.lower()

    combined_activity, native_txs = fetch_all_activity(address)

    matched_vasp = check_direct_match(combined_activity)
    confidence = 90 if matched_vasp else 0
    hops = 0 if matched_vasp else -1
    matched_via = None

    # Hop 1: check up to 5 counterparties if no direct match
    if not matched_vasp:
        counterparties = set()
        for tx in combined_activity[:20]:
            from_addr = tx.get('from', '').strip().lower()
            to_addr = tx.get('to', '').strip().lower()
            other = from_addr if to_addr == address_lower else to_addr
            if other and other != address_lower:
                counterparties.add(other)
            if len(counterparties) >= 5:
                break

        for candidate in counterparties:
            candidate_native = fetch_transactions(candidate)
            m_vasp = check_direct_match(candidate_native)
            if m_vasp:
                matched_vasp = m_vasp
                confidence = 70
                hops = 1
                matched_via = candidate
                break

    flags = detect_flags(combined_activity)

    result = {
        "address": address,
        "tx_count": len(native_txs),
        "transactions": native_txs[:10],
        "matched_vasp": matched_vasp,
        "confidence": confidence,
        "hops": hops,
        "matched_via": matched_via,
        "flags": flags
    }
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, port=5000)