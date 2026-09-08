from flask import Flask, request, jsonify
from flask_cors import CORS
from graph_analysis import analyze_graph

import csv
import os
import re
import requests

from dotenv import load_dotenv


# ============================================================
# FLASK APP SETUP
# ============================================================

app = Flask(__name__)
CORS(app)

load_dotenv()

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VASP_FILE = os.path.join(
    BASE_DIR,
    "vasp_addresses.csv"
)


# ============================================================
# LOAD VASP ADDRESSES
# ============================================================

def load_vasp_addresses(file_path):

    vasp_addresses = {}

    try:

        with open(
            file_path,
            "r",
            newline="",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                address = (
                    row.get("address", "")
                    .strip()
                    .lower()
                )

                vasp_name = (
                    row.get("vasp_name", "")
                    .strip()
                )

                if address:
                    vasp_addresses[address] = vasp_name

    except FileNotFoundError:

        print(
            f"ERROR: VASP file not found: "
            f"{file_path}"
        )

    return vasp_addresses


VASP_ADDRESSES = load_vasp_addresses(
    VASP_FILE
)

print(
    f"Loaded {len(VASP_ADDRESSES)} VASP addresses"
)


# ============================================================
# ETHEREUM ADDRESS VALIDATION
# ============================================================

def is_valid_eth_address(address):

    pattern = r"^0x[a-fA-F0-9]{40}$"

    return bool(
        re.fullmatch(
            pattern,
            address
        )
    )


# ============================================================
# FETCH TRANSACTIONS FOR ONE WALLET
# ============================================================

def fetch_transactions(address):

    if not ETHERSCAN_API_KEY:

        raise RuntimeError(
            "ETHERSCAN_API_KEY is not configured"
        )

    url = (
        "https://api.etherscan.io/v2/api"
    )

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

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if data.get("status") != "1":

        message = data.get(
            "message",
            "Etherscan API error"
        )

        result = data.get(
            "result"
        )

        if isinstance(
            result,
            str
        ):

            message = result

        raise RuntimeError(
            message
        )

    transactions = []

    for tx in data.get(
        "result",
        []
    ):

        sender = (
            tx.get("from", "")
            .strip()
            .lower()
        )

        receiver = (
            tx.get("to", "")
            .strip()
            .lower()
        )

        if (
            sender
            and receiver
            and sender != receiver
        ):

            transactions.append(
                (
                    sender,
                    receiver
                )
            )

    return transactions


# ============================================================
# BOUNDED 2-HOP TRANSACTION FETCHING
# ============================================================

def fetch_transactions_multi_hop(
    start_address,
    max_depth=2,
    max_wallets=10
):

    start_address = (
        start_address
        .strip()
        .lower()
    )

    visited = set()

    # queue contains:
    # (wallet_address, depth)
    queue = [
        (
            start_address,
            0
        )
    ]

    all_transactions = []

    root_tx_count = 0

    while (
        queue
        and len(visited) < max_wallets
    ):

        current_address, depth = (
            queue.pop(0)
        )

        if current_address in visited:
            continue

        visited.add(
            current_address
        )

        print(
            f"[TRACE] Fetching "
            f"{current_address} "
            f"(depth={depth})"
        )

        try:

            transactions = fetch_transactions(
                current_address
            )

        except Exception as e:

            print(
                f"[TRACE] Failed to fetch "
                f"{current_address}: {e}"
            )

            continue

        # Save transaction count
        # for original searched wallet
        if current_address == start_address:

            root_tx_count = len(
                transactions
            )

        # Add transactions to
        # combined graph dataset
        all_transactions.extend(
            transactions
        )

        # Stop expansion after
        # reaching maximum depth
        if depth >= max_depth:
            continue

        # ----------------------------------------------------
        # DISCOVER NEXT-LEVEL WALLETS
        # ----------------------------------------------------

        for sender, receiver in transactions:

            next_wallet = None

            # Outgoing transaction
            if sender == current_address:

                next_wallet = receiver

            # Incoming transaction
            elif receiver == current_address:

                next_wallet = sender

            if not next_wallet:
                continue

            if next_wallet in visited:
                continue

            # Don't fetch known VASP wallets.
            #
            # We already know that they are VASPs,
            # so there is no reason to download
            # their entire transaction history.
            if next_wallet in VASP_ADDRESSES:

                print(
                    f"[TRACE] Found VASP "
                    f"{next_wallet}"
                )

                continue

            if not is_valid_eth_address(
                next_wallet
            ):

                continue

            # Avoid unlimited API expansion
            if (
                len(visited)
                + len(queue)
                >= max_wallets
            ):

                break

            queue.append(
                (
                    next_wallet,
                    depth + 1
                )
            )

    return (
        all_transactions,
        visited,
        root_tx_count
    )


# ============================================================
# ATTRIBUTE / TRACE API
# ============================================================

@app.route(
    "/api/attribute",
    methods=["GET"]
)
def attribute():

    address = (
        request.args.get(
            "address",
            ""
        )
        .strip()
        .lower()
    )

    # --------------------------------------------------------
    # VALIDATE ADDRESS
    # --------------------------------------------------------

    if not is_valid_eth_address(
        address
    ):

        return jsonify({

            "error":
                "Invalid Ethereum address",

            "message": (
                "Ethereum wallet address must "
                "contain 0x followed by 40 "
                "hexadecimal characters."
            )

        }), 400

    # --------------------------------------------------------
    # DIRECT VASP
    #
    # If searched address itself is a VASP,
    # don't perform multi-hop fetching.
    # --------------------------------------------------------

    if address in VASP_ADDRESSES:

        try:

            transactions = fetch_transactions(
                address
            )

        except Exception as e:

            return jsonify({

                "error":
                    "Failed to fetch blockchain data",

                "message":
                    str(e),

                "data_source":
                    "etherscan"

            }), 502

        fetched_wallets = {
            address
        }

        root_tx_count = len(
            transactions
        )

    # --------------------------------------------------------
    # NON-VASP → BOUNDED 2-HOP FETCH
    # --------------------------------------------------------

    else:

        try:

            (
                transactions,
                fetched_wallets,
                root_tx_count

            ) = fetch_transactions_multi_hop(

                address,

                max_depth=2,

                max_wallets=10
            )

        except Exception as e:

            return jsonify({

                "error":
                    "Failed to fetch blockchain data",

                "message":
                    str(e),

                "data_source":
                    "etherscan"

            }), 502

    # --------------------------------------------------------
    # NO TRANSACTIONS
    # --------------------------------------------------------

    if not transactions:

        return jsonify({

            "error":
                "No transactions found",

            "address":
                address,

            "data_source":
                "etherscan"

        }), 404

    # --------------------------------------------------------
    # GRAPH ANALYSIS
    # --------------------------------------------------------

    try:

        graph_result = analyze_graph(

            transactions,

            address,

            VASP_ADDRESSES
        )

    except Exception as e:

        return jsonify({

            "error":
                "Graph analysis failed",

            "message":
                str(e)

        }), 500

    # --------------------------------------------------------
    # VASP RESULT
    # --------------------------------------------------------

    nearest_vasp = graph_result.get(
        "nearest_vasp"
    )

    matched_vasp = None

    matched_via = None

    hops = -1

    confidence = 0

    if nearest_vasp:

        matched_vasp = (
            nearest_vasp.get(
                "vasp_name"
            )
        )

        matched_via = (
            nearest_vasp.get(
                "address"
            )
        )

        hops = (
            nearest_vasp.get(
                "hops",
                -1
            )
        )

        confidence = (
            graph_result.get(
                "confidence",
                0
            )
        )

    # --------------------------------------------------------
    # DIRECT VASP OVERRIDE
    # --------------------------------------------------------

    if address in VASP_ADDRESSES:

        matched_vasp = (
            VASP_ADDRESSES[address]
        )

        matched_via = address

        hops = 0

        confidence = 90

    # --------------------------------------------------------
    # REPEATED TRANSACTION FLAGS
    # --------------------------------------------------------

    outgoing_counts = {}

    for sender, receiver in transactions:

        # Only analyse transactions
        # originating from searched wallet
        if sender != address:
            continue

        key = (
            sender,
            receiver
        )

        outgoing_counts[key] = (
            outgoing_counts.get(
                key,
                0
            )
            + 1
        )

    flags = []

    for (
        (sender, receiver),
        count
    ) in outgoing_counts.items():

        if count >= 3:

            flags.append({

                "type":
                    "repeated_transaction",

                "from":
                    sender,

                "to":
                    receiver,

                "count":
                    count
            })

    # --------------------------------------------------------
    # FINAL RESPONSE
    # --------------------------------------------------------

    return jsonify({

        "address":
            address,

        "data_source":
            "etherscan",

        "data_source_message": (
            "Transactions fetched from "
            "Etherscan using bounded "
            "2-hop graph expansion."
        ),

        # Transactions belonging to
        # searched wallet
        "tx_count":
            root_tx_count,

        # Total transactions used
        # for graph construction
        "graph_tx_count":
            len(transactions),

        # Number of wallets whose
        # transactions were fetched
        "fetched_wallet_count":
            len(fetched_wallets),

        # Maximum configured trace depth
        "trace_depth":
            2,

        # Sample transactions for frontend
        "transactions":
            transactions[:10],

        # VASP attribution
        "matched_vasp":
            matched_vasp,

        "confidence":
            confidence,

        "hops":
            hops,

        "matched_via":
            matched_via,

        # Flags
        "flags":
            flags,

        # Complete graph analysis
        "graph_analysis":
            graph_result
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status":
            "ok",

        "service":
            "Crypto Trace VASP API"
    })


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True,
        port=5000
    )