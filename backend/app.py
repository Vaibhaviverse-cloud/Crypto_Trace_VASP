from flask import Flask, request, jsonify
from flask_cors import CORS
from graph_analysis import analyze_graph

import csv
import os
import requests
from dotenv import load_dotenv


app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# --------------------------------------------------

load_dotenv(os.path.join(BASE_DIR, ".env"))

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

print("API KEY LOADED:", bool(ETHERSCAN_API_KEY))


# --------------------------------------------------
# FILE PATHS
# --------------------------------------------------

VASP_FILE = os.path.join(
    BASE_DIR,
    "vasp_addresses.csv"
)


# --------------------------------------------------
# LOAD VASP ADDRESSES
# --------------------------------------------------

def load_vasp_addresses():

    vasp_addresses = {}

    with open(
        VASP_FILE,
        "r",
        newline="",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            address = row["address"].strip().lower()
            vasp_name = row["vasp_name"].strip()

            vasp_addresses[address] = vasp_name

    return vasp_addresses


VASP_ADDRESSES = load_vasp_addresses()

print(
    f"Loaded {len(VASP_ADDRESSES)} VASP addresses"
)


# --------------------------------------------------
# ETHEREUM ADDRESS VALIDATION
# --------------------------------------------------

def is_valid_ethereum_address(address):

    if not address.startswith("0x"):
        return False

    if len(address) != 42:
        return False

    hex_part = address[2:]

    try:

        int(hex_part, 16)
        return True

    except ValueError:

        return False


# --------------------------------------------------
# FETCH TRANSACTIONS FROM ETHERSCAN API
# --------------------------------------------------

def fetch_transactions(address):

    if not ETHERSCAN_API_KEY:

        print("----------------------------------------")
        print("ETHERSCAN ERROR")
        print("ETHERSCAN_API_KEY not found in .env")
        print("----------------------------------------")

        return [], "API key not found"

    if not is_valid_ethereum_address(address):

        print("----------------------------------------")
        print("ETHERSCAN ERROR")
        print(
            "Invalid Ethereum address:",
            address
        )
        print("----------------------------------------")

        return [], "Invalid Ethereum address"

    # Etherscan V2 API
    url = "https://api.etherscan.io/v2/api"

    params = {

        "chainid": "1",

        "module": "account",

        "action": "txlist",

        "address": address,

        "startblock": "0",

        "endblock": "99999999",

        "page": "1",

        "offset": "100",

        "sort": "asc",

        "apikey": ETHERSCAN_API_KEY
    }

    print("----------------------------------------")
    print("REQUESTING TRANSACTIONS FROM ETHERSCAN")
    print("Address:", address)
    print("----------------------------------------")

    try:

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        print(
            "HTTP Status:",
            response.status_code
        )

        response.raise_for_status()

        data = response.json()

        print(
            "Etherscan response status:",
            data.get("status")
        )

        print(
            "Etherscan message:",
            data.get("message")
        )

        # --------------------------------------------------
        # SUCCESS
        # --------------------------------------------------

        if data.get("status") == "1":

            transactions = []

            for tx in data.get(
                "result",
                []
            ):

                sender = tx.get(
                    "from",
                    ""
                ).strip().lower()

                receiver = tx.get(
                    "to",
                    ""
                ).strip().lower()

                if (
                    sender
                    and receiver
                    and sender != receiver
                ):

                    transactions.append(
                        (sender, receiver)
                    )

            if transactions:

                print("----------------------------------------")
                print(
                    f"SUCCESS: Received "
                    f"{len(transactions)} "
                    "transactions from Etherscan"
                )
                print("----------------------------------------")

                return (
                    transactions,
                    "Etherscan transaction data loaded successfully"
                )

            print("----------------------------------------")
            print(
                "Etherscan returned zero "
                "usable transactions"
            )
            print("----------------------------------------")

            return (
                [],
                "Etherscan returned zero usable transactions"
            )

        # --------------------------------------------------
        # API ERROR
        # --------------------------------------------------

        error_message = data.get(
            "result",
            data.get(
                "message",
                "Unknown Etherscan error"
            )
        )

        print("----------------------------------------")
        print("ETHERSCAN API ERROR")
        print(error_message)
        print("----------------------------------------")

        return (
            [],
            str(error_message)
        )

    except requests.RequestException as error:

        print("----------------------------------------")
        print("ETHERSCAN REQUEST FAILED")
        print(error)
        print("----------------------------------------")

        return (
            [],
            str(error)
        )

    except ValueError as error:

        print("----------------------------------------")
        print("INVALID JSON FROM ETHERSCAN")
        print(error)
        print("----------------------------------------")

        return (
            [],
            str(error)
        )


# --------------------------------------------------
# ATTRIBUTE API
# --------------------------------------------------

@app.route(
    "/api/attribute",
    methods=["GET"]
)
def attribute():

    # --------------------------------------------------
    # GET ADDRESS
    # --------------------------------------------------

    address = request.args.get(
        "address",
        ""
    ).strip().lower()

    if not address:

        return jsonify({
            "error": "Address is required"
        }), 400

    # --------------------------------------------------
    # VALIDATE ADDRESS
    # --------------------------------------------------

    if not is_valid_ethereum_address(address):

        return jsonify({

            "error": "Invalid Ethereum address",

            "message": (
                "Ethereum wallet address must contain "
                "0x followed by 40 hexadecimal characters."
            )

        }), 400

    # --------------------------------------------------
    # FETCH TRANSACTIONS FROM ETHERSCAN
    # --------------------------------------------------

    transactions, data_source_message = fetch_transactions(
        address
    )

    # If Etherscan failed
    if not transactions:

        return jsonify({

            "error": "Unable to fetch transaction data",

            "address": address,

            "data_source": "etherscan",

            "data_source_message": data_source_message,

            "transactions": [],

            "graph_analysis": {}

        }), 502

    # --------------------------------------------------
    # GRAPH ANALYSIS
    # --------------------------------------------------

    graph_result = analyze_graph(
        transactions,
        address
    )

    # --------------------------------------------------
    # SUSPECT TRANSACTIONS
    # --------------------------------------------------

    suspect_transactions = []

    for sender, receiver in transactions:

        if (
            sender == address
            or receiver == address
        ):

            suspect_transactions.append({

                "from": sender,

                "to": receiver

            })

    # --------------------------------------------------
    # VASP CONNECTIONS
    # --------------------------------------------------

    vasp_connections = []

    for wallet in graph_result[
        "cluster_members"
    ]:

        if wallet in VASP_ADDRESSES:

            vasp_connections.append({

                "address": wallet,

                "vasp_name": VASP_ADDRESSES[
                    wallet
                ]

            })

    # --------------------------------------------------
    # DIRECT VASP MATCH
    # --------------------------------------------------

    direct_vasp = VASP_ADDRESSES.get(
        address
    )

    if direct_vasp:

        matched_vasp = direct_vasp

        confidence = 90

        hops = 0

        matched_via = None

    else:

        matched_vasp = None

        confidence = 0

        hops = -1

        matched_via = None

    # --------------------------------------------------
    # REPEATED TRANSACTION DETECTION
    # --------------------------------------------------

    flags = []

    transaction_counts = {}

    for sender, receiver in transactions:

        if sender == address:

            key = (
                sender,
                receiver
            )

            transaction_counts[key] = (
                transaction_counts.get(
                    key,
                    0
                ) + 1
            )

    for (
        sender,
        receiver
    ), count in transaction_counts.items():

        if count >= 3:

            flags.append({

                "type": "repeated_transaction",

                "from": sender,

                "to": receiver,

                "count": count

            })

    # --------------------------------------------------
    # FINAL RESPONSE
    # --------------------------------------------------

    result = {

        "address": address,

        "data_source": "etherscan",

        "data_source_message":
            data_source_message,

        "tx_count":
            len(suspect_transactions),

        "transactions":
            suspect_transactions,

        "matched_vasp":
            matched_vasp,

        "confidence":
            confidence,

        "hops":
            hops,

        "matched_via":
            matched_via,

        "flags":
            flags,

        "graph_analysis": {

            "nodes":
                graph_result["nodes"],

            "edges":
                graph_result["edges"],

            "suspect_cluster":
                graph_result[
                    "suspect_cluster"
                ],

            "cluster_size":
                graph_result[
                    "cluster_size"
                ],

            "suspect_in_degree":
                graph_result[
                    "suspect_in_degree"
                ],

            "suspect_out_degree":
                graph_result[
                    "suspect_out_degree"
                ],

            "cluster_members":
                graph_result[
                    "cluster_members"
                ],

            "clusters":
                graph_result[
                    "clusters"
                ],

            "graph_nodes":
                graph_result[
                    "graph_nodes"
                ],

            "graph_edges":
                graph_result[
                    "graph_edges"
                ],

            "vasp_connections":
                vasp_connections,

            "vasp_connection_count":
                len(vasp_connections)
        }
    }

    return jsonify(result)


# --------------------------------------------------
# HEALTH CHECK API
# --------------------------------------------------

@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status": "ok",

        "etherscan_configured":
            bool(ETHERSCAN_API_KEY),

        "vasp_addresses":
            len(VASP_ADDRESSES)

    })


# --------------------------------------------------
# RUN SERVER
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        debug=True,
        port=5000
    )