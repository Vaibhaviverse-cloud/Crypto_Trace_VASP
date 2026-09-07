import networkx as nx


# ==========================================================
# BUILD TRANSACTION GRAPH
# ==========================================================

def build_transaction_graph(transactions):
    """
    Build a directed weighted transaction graph.

    Node  = wallet address
    Edge  = transaction direction
    Weight = number of transactions between two wallets
    """

    G = nx.DiGraph()

    for sender, receiver in transactions:

        sender = sender.strip().lower()
        receiver = receiver.strip().lower()

        if not sender or not receiver:
            continue

        if sender == receiver:
            continue

        if G.has_edge(sender, receiver):

            G[sender][receiver]["weight"] += 1

        else:

            G.add_edge(
                sender,
                receiver,
                weight=1
            )

    return G


# ==========================================================
# FIND NEAREST VASP USING BFS
# ==========================================================

def find_nearest_vasp(
    graph,
    start_address,
    vasp_addresses
):
    """
    Find the nearest known VASP from a wallet using BFS.

    BFS is performed on an undirected projection because
    we are measuring wallet-to-wallet structural proximity.

    Returns:
        address
        vasp_name
        hops
        path
    """

    start_address = start_address.strip().lower()

    if not vasp_addresses:

        return {
            "address": None,
            "vasp_name": None,
            "hops": -1,
            "path": []
        }

    # Normalize VASP addresses
    normalized_vasps = {
        address.strip().lower(): name
        for address, name in vasp_addresses.items()
    }

    # Direct VASP match
    if start_address in normalized_vasps:

        return {
            "address": start_address,
            "vasp_name": normalized_vasps[start_address],
            "hops": 0,
            "path": [start_address]
        }

    # Use undirected graph for structural proximity
    undirected_graph = graph.to_undirected()

    if start_address not in undirected_graph:

        return {
            "address": None,
            "vasp_name": None,
            "hops": -1,
            "path": []
        }

    # BFS from suspect wallet
    queue = [start_address]

    visited = {
        start_address
    }

    parent = {
        start_address: None
    }

    while queue:

        current = queue.pop(0)

        # Check whether current wallet is known VASP
        if current in normalized_vasps:

            path = []

            node = current

            while node is not None:

                path.append(node)

                node = parent[node]

            path.reverse()

            return {
                "address": current,
                "vasp_name": normalized_vasps[current],
                "hops": len(path) - 1,
                "path": path
            }

        for neighbor in undirected_graph.neighbors(current):

            if neighbor in visited:
                continue

            visited.add(neighbor)

            parent[neighbor] = current

            queue.append(neighbor)

    # No VASP reachable
    return {
        "address": None,
        "vasp_name": None,
        "hops": -1,
        "path": []
    }


# ==========================================================
# CONFIDENCE SCORE
# ==========================================================

def calculate_confidence(
    nearest_vasp,
    is_direct_vasp=False
):
    """
    Calculate a heuristic confidence score.

    IMPORTANT:
    This is graph-based analytical confidence.
    It does NOT prove ownership or VASP control.
    """

    if is_direct_vasp:

        return 90

    hops = nearest_vasp.get(
        "hops",
        -1
    )

    if hops == 1:

        return 80

    if hops == 2:

        return 70

    if hops == 3:

        return 60

    if hops > 3:

        return 50

    return 0


# ==========================================================
# WALLET EVIDENCE / CONFIDENCE
# ==========================================================

def calculate_wallet_scores(
    graph,
    vasp_addresses
):
    """
    Calculate graph-based nearest-VASP evidence
    for every wallet in the graph.
    """

    wallet_scores = []

    for wallet in graph.nodes():

        nearest_vasp = find_nearest_vasp(
            graph,
            wallet,
            vasp_addresses
        )

        is_direct_vasp = wallet in {
            address.strip().lower()
            for address in vasp_addresses
        }

        confidence = calculate_confidence(
            nearest_vasp,
            is_direct_vasp
        )

        wallet_scores.append({

            "address": wallet,

            "nearest_vasp":
                nearest_vasp["address"],

            "vasp_name":
                nearest_vasp["vasp_name"],

            "hops":
                nearest_vasp["hops"],

            "path":
                nearest_vasp["path"],

            "confidence":
                confidence
        })

    return wallet_scores


# ==========================================================
# LOAD TRANSACTIONS FROM CSV
# ==========================================================

def load_transactions(file_path):
    """
    Load transactions from CSV.

    CSV format:

    from,to
    """

    import csv

    transactions = []

    with open(
        file_path,
        "r",
        newline="",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            sender = row["from"].strip().lower()
            receiver = row["to"].strip().lower()

            if (
                sender
                and receiver
                and sender != receiver
            ):

                transactions.append(
                    (sender, receiver)
                )

    return transactions


# ==========================================================
# MAIN GRAPH ANALYSIS
# ==========================================================

def analyze_graph(
    transactions,
    suspect_address,
    vasp_addresses=None
):

    suspect_address = (
        suspect_address
        .strip()
        .lower()
    )

    if vasp_addresses is None:

        vasp_addresses = {}

    # ------------------------------------------------------
    # 1. BUILD DIRECTED GRAPH
    # ------------------------------------------------------

    G = build_transaction_graph(
        transactions
    )

    # Make sure suspect exists
    if suspect_address not in G:

        G.add_node(
            suspect_address
        )

    # ------------------------------------------------------
    # 2. GRAPH FEATURES
    # ------------------------------------------------------

    suspect_in_degree = G.in_degree(
        suspect_address
    )

    suspect_out_degree = G.out_degree(
        suspect_address
    )

    # ------------------------------------------------------
    # 3. UNDIRECTED GRAPH FOR COMMUNITY DETECTION
    # ------------------------------------------------------

    G_cluster = G.to_undirected()

    # ------------------------------------------------------
    # 4. LOUVAIN COMMUNITY DETECTION
    # ------------------------------------------------------

    if G_cluster.number_of_nodes() > 0:

        communities = (
            nx.community.louvain_communities(
                G_cluster,
                weight="weight",
                seed=42
            )
        )

    else:

        communities = []

    # ------------------------------------------------------
    # 5. ASSIGN CLUSTER IDS
    # ------------------------------------------------------

    node_to_cluster = {}

    for cluster_id, community in enumerate(
        communities,
        start=1
    ):

        for node in community:

            node_to_cluster[node] = (
                cluster_id
            )

    # ------------------------------------------------------
    # 6. FIND SUSPECT CLUSTER
    # ------------------------------------------------------

    suspect_cluster = (
        node_to_cluster.get(
            suspect_address
        )
    )

    suspect_community = set()

    if suspect_cluster is not None:

        suspect_community = set(
            communities[
                suspect_cluster - 1
            ]
        )

    # ------------------------------------------------------
    # 7. CLUSTER STATISTICS
    # ------------------------------------------------------

    cluster_stats = []

    for cluster_id, community in enumerate(
        communities,
        start=1
    ):

        subgraph = G_cluster.subgraph(
            community
        )

        wallet_count = len(
            community
        )

        internal_edges = (
            subgraph.number_of_edges()
        )

        total_transaction_weight = sum(

            data.get(
                "weight",
                1
            )

            for _, _, data
            in subgraph.edges(
                data=True
            )
        )

        degrees = dict(
            subgraph.degree()
        )

        average_degree = (

            sum(
                degrees.values()
            )
            / wallet_count

            if wallet_count
            else 0
        )

        cluster_stats.append({

            "cluster_id":
                cluster_id,

            "wallet_count":
                wallet_count,

            "internal_edges":
                internal_edges,

            "total_transaction_weight":
                total_transaction_weight,

            "average_degree":
                round(
                    average_degree,
                    2
                ),

            "members":
                sorted(
                    community
                )
        })

    # ------------------------------------------------------
    # 8. NEAREST VASP FOR SUSPECT
    # ------------------------------------------------------

    nearest_vasp = find_nearest_vasp(

        G,

        suspect_address,

        vasp_addresses
    )

    # ------------------------------------------------------
    # 9. DIRECT VASP CHECK
    # ------------------------------------------------------

    normalized_vasp_addresses = {

        address.strip().lower():
            name

        for address, name
        in vasp_addresses.items()
    }

    direct_vasp = (
        normalized_vasp_addresses.get(
            suspect_address
        )
    )

    # ------------------------------------------------------
    # 10. CONFIDENCE
    # ------------------------------------------------------

    confidence = calculate_confidence(

        nearest_vasp,

        is_direct_vasp=(
            direct_vasp is not None
        )
    )

    # ------------------------------------------------------
    # 11. VASP CONNECTIONS INSIDE SUSPECT CLUSTER
    # ------------------------------------------------------

    vasp_connections = []

    for wallet in sorted(
        suspect_community
    ):

        if wallet in normalized_vasp_addresses:

            vasp_connections.append({

                "address":
                    wallet,

                "vasp_name":
                    normalized_vasp_addresses[
                        wallet
                    ]
            })

    # ------------------------------------------------------
    # 12. CONFIDENCE / EVIDENCE FOR EVERY WALLET
    # ------------------------------------------------------

    wallet_scores = calculate_wallet_scores(

        G,

        normalized_vasp_addresses
    )

    # ------------------------------------------------------
    # 13. GRAPH NODES FOR FRONTEND
    # ------------------------------------------------------

    graph_nodes = []

    for node in G.nodes():

        wallet_score = next(

            (
                item
                for item in wallet_scores
                if item["address"] == node
            ),

            None
        )

        graph_nodes.append({

            "id":
                node,

            "label":
                node[:10] + "...",

            "cluster":
                node_to_cluster.get(
                    node
                ),

            "confidence":
                (
                    wallet_score["confidence"]
                    if wallet_score
                    else 0
                ),

            "nearest_vasp":
                (
                    wallet_score["nearest_vasp"]
                    if wallet_score
                    else None
                ),

            "vasp_name":
                (
                    wallet_score["vasp_name"]
                    if wallet_score
                    else None
                ),

            "hops":
                (
                    wallet_score["hops"]
                    if wallet_score
                    else -1
                )
        })

    # ------------------------------------------------------
    # 14. GRAPH EDGES FOR FRONTEND
    # ------------------------------------------------------

    graph_edges = []

    for sender, receiver, data in G.edges(
        data=True
    ):

        graph_edges.append({

            "from":
                sender,

            "to":
                receiver,

            "weight":
                data.get(
                    "weight",
                    1
                )
        })

    # ------------------------------------------------------
    # 15. RETURN RESULT
    # ------------------------------------------------------

    return {

        "nodes":
            G.number_of_nodes(),

        "edges":
            G.number_of_edges(),

        "suspect_cluster":
            suspect_cluster,

        "suspect_in_degree":
            suspect_in_degree,

        "suspect_out_degree":
            suspect_out_degree,

        "cluster_size":
            len(
                suspect_community
            ),

        "cluster_members":
            sorted(
                suspect_community
            ),

        "clusters":
            cluster_stats,

        "nearest_vasp":
            nearest_vasp,

        "confidence":
            confidence,

        "wallet_scores":
            wallet_scores,

        "graph_nodes":
            graph_nodes,

        "graph_edges":
            graph_edges,

        "vasp_connections":
            vasp_connections,

        "vasp_connection_count":
            len(
                vasp_connections
            )
    }