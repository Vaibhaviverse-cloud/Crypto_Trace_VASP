import csv
import networkx as nx


# ============================================================
# LOAD TRANSACTIONS FROM CSV
# ============================================================

def load_transactions(file_path):

    transactions = []

    with open(
        file_path,
        "r",
        newline="",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(
            file
        )

        for row in reader:

            sender = (
                row["from"]
                .strip()
                .lower()
            )

            receiver = (
                row["to"]
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
# BUILD DIRECTED WEIGHTED GRAPH
# ============================================================

def build_transaction_graph(
    transactions
):

    G = nx.DiGraph()

    for sender, receiver in transactions:

        if G.has_edge(
            sender,
            receiver
        ):

            G[sender][receiver]["weight"] += 1

        else:

            G.add_edge(

                sender,

                receiver,

                weight=1
            )

    return G


# ============================================================
# FIND NEAREST VASP
#
# Uses DIRECTED BFS.
#
# This means:
#
# Wallet A
#    ↓
# Wallet B
#    ↓
# VASP
#
# is a valid 2-hop path.
# ============================================================

def find_nearest_vasp(
    graph,
    start_address,
    vasp_addresses
):

    start_address = (
        start_address
        .strip()
        .lower()
    )

    # Normalize VASP addresses
    normalized_vasps = {
        address.strip().lower(): name
        for address, name in vasp_addresses.items()
    }

    # --------------------------------------------------------
    # DIRECT VASP MATCH
    # --------------------------------------------------------

    if start_address in normalized_vasps:

        return {
            "address": start_address,
            "vasp_name": normalized_vasps[start_address],
            "hops": 0,
            "path": [start_address]
        }

    # --------------------------------------------------------
    # WALLET NOT IN GRAPH
    # --------------------------------------------------------

    if start_address not in graph:

        return {
            "address": None,
            "vasp_name": None,
            "hops": -1,
            "path": []
        }

    # --------------------------------------------------------
    # UNDIRECTED GRAPH FOR VASP PROXIMITY
    #
    # This treats a transaction relationship as
    # a wallet-to-wallet connection regardless of
    # transaction direction.
    # --------------------------------------------------------

    G_bfs = graph.to_undirected()

    # --------------------------------------------------------
    # BFS
    # --------------------------------------------------------

    queue = [
        (
            start_address,
            0,
            [start_address]
        )
    ]

    visited = {
        start_address
    }

    while queue:

        current, hops, path = queue.pop(0)

        for neighbor in G_bfs.neighbors(current):

            if neighbor in visited:
                continue

            new_path = path + [neighbor]

            # ------------------------------------------------
            # VASP FOUND
            # ------------------------------------------------

            if neighbor in normalized_vasps:

                return {
                    "address": neighbor,
                    "vasp_name": normalized_vasps[neighbor],
                    "hops": hops + 1,
                    "path": new_path
                }

            visited.add(neighbor)

            queue.append(
                (
                    neighbor,
                    hops + 1,
                    new_path
                )
            )

    # --------------------------------------------------------
    # NO VASP FOUND
    # --------------------------------------------------------

    return {
        "address": None,
        "vasp_name": None,
        "hops": -1,
        "path": []
    }


# ============================================================
# CONFIDENCE SCORE
# ============================================================

def calculate_confidence(
    nearest_vasp,
    is_direct_vasp=False
):

    # --------------------------------------------------------
    # DIRECT VASP
    # --------------------------------------------------------

    if is_direct_vasp:

        return 90

    # --------------------------------------------------------
    # NO VASP
    # --------------------------------------------------------

    if nearest_vasp is None:

        return 0

    hops = nearest_vasp.get(
        "hops",
        -1
    )

    # --------------------------------------------------------
    # HOP-BASED SCORE
    # --------------------------------------------------------

    if hops == 1:

        return 80

    elif hops == 2:

        return 70

    elif hops == 3:

        return 60

    elif hops > 3:

        return 50

    return 0


# ============================================================
# CALCULATE WALLET SCORES
# ============================================================

def calculate_wallet_scores(
    graph,
    vasp_addresses
):

    wallet_scores = {}

    # Normalize once instead of
    # rebuilding the set for every wallet
    normalized_vasp_addresses = {

        address.strip().lower()

        for address
        in vasp_addresses.keys()
    }

    for wallet in graph.nodes():

        nearest_vasp = find_nearest_vasp(

            graph,

            wallet,

            vasp_addresses
        )

        is_direct_vasp = (

            wallet.strip().lower()

            in normalized_vasp_addresses
        )

        confidence = calculate_confidence(

            nearest_vasp,

            is_direct_vasp
        )

        wallet_scores[wallet] = {

            "confidence":
                confidence,

            "nearest_vasp":

                (
                    nearest_vasp.get(
                        "address"
                    )

                    if nearest_vasp
                    else None
                ),

            "vasp_name":

                (
                    nearest_vasp.get(
                        "vasp_name"
                    )

                    if nearest_vasp
                    else None
                ),

            "hops":

                (
                    nearest_vasp.get(
                        "hops",
                        -1
                    )

                    if nearest_vasp
                    else -1
                ),

            "path":

                (
                    nearest_vasp.get(
                        "path",
                        []
                    )

                    if nearest_vasp
                    else []
                )
        }

    return wallet_scores


# ============================================================
# COMPLETE GRAPH ANALYSIS
# ============================================================

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

    # --------------------------------------------------------
    # BUILD DIRECTED GRAPH
    # --------------------------------------------------------

    G = build_transaction_graph(
        transactions
    )

    # Ensure suspect exists
    if suspect_address not in G:

        G.add_node(
            suspect_address
        )

    # --------------------------------------------------------
    # SUSPECT DEGREE
    # --------------------------------------------------------

    suspect_in_degree = (
        G.in_degree(
            suspect_address
        )
    )

    suspect_out_degree = (
        G.out_degree(
            suspect_address
        )
    )

    # --------------------------------------------------------
    # UNDIRECTED PROJECTION
    #
    # Used only for Louvain clustering.
    #
    # Original directed graph G
    # remains unchanged.
    # --------------------------------------------------------

    G_cluster = (
        G.to_undirected()
    )

    # --------------------------------------------------------
    # LOUVAIN COMMUNITY DETECTION
    # --------------------------------------------------------

    communities = (

        nx.community.louvain_communities(

            G_cluster,

            weight="weight",

            seed=42
        )
    )

    # --------------------------------------------------------
    # NODE → CLUSTER
    # --------------------------------------------------------

    node_to_cluster = {}

    for (
        cluster_id,
        community
    ) in enumerate(

        communities,

        start=1
    ):

        for node in community:

            node_to_cluster[node] = (
                cluster_id
            )

    # --------------------------------------------------------
    # SUSPECT COMMUNITY
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CLUSTER STATISTICS
    # --------------------------------------------------------

    cluster_stats = []

    for (
        cluster_id,
        community
    ) in enumerate(

        communities,

        start=1
    ):

        subgraph = (
            G_cluster.subgraph(
                community
            )
        )

        wallet_count = (
            len(community)
        )

        internal_edges = (
            subgraph.number_of_edges()
        )

        total_transaction_weight = sum(

            data.get(
                "weight",
                1
            )

            for (
                _,
                _,
                data
            )

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

    # --------------------------------------------------------
    # NEAREST VASP
    # --------------------------------------------------------

    nearest_vasp = find_nearest_vasp(

        G,

        suspect_address,

        vasp_addresses
    )

    # --------------------------------------------------------
    # DIRECT VASP CHECK
    # --------------------------------------------------------

    normalized_vasp_addresses = {

        address.strip().lower()

        for address
        in vasp_addresses.keys()
    }

    is_direct_vasp = (

        suspect_address

        in normalized_vasp_addresses
    )

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    confidence = calculate_confidence(

        nearest_vasp,

        is_direct_vasp
    )

    # --------------------------------------------------------
    # VASP CONNECTIONS INSIDE
    # SUSPECT CLUSTER
    # --------------------------------------------------------

    vasp_connections = []

    for wallet in suspect_community:

        normalized_wallet = (
            wallet
            .strip()
            .lower()
        )

        if (
            normalized_wallet
            in normalized_vasp_addresses
        ):

            vasp_connections.append({

                "address":
                    normalized_wallet,

                "vasp_name":
                    vasp_addresses.get(
                        normalized_wallet
                    )
                    or vasp_addresses.get(
                        wallet
                    )
            })

    # --------------------------------------------------------
    # WALLET SCORES
    # --------------------------------------------------------

    wallet_scores = (
        calculate_wallet_scores(

            G,

            vasp_addresses
        )
    )

    # --------------------------------------------------------
    # GRAPH NODES
    # --------------------------------------------------------

    graph_nodes = []

    for node in G.nodes():

        score = wallet_scores.get(
            node,
            {}
        )

        graph_nodes.append({

            "id":
                node,

            "label":

                (
                    node[:10]
                    + "..."

                    if len(node) > 10
                    else node
                ),

            "cluster":
                node_to_cluster.get(
                    node
                ),

            "confidence":
                score.get(
                    "confidence",
                    0
                ),

            "nearest_vasp":
                score.get(
                    "nearest_vasp"
                ),

            "vasp_name":
                score.get(
                    "vasp_name"
                ),

            "hops":
                score.get(
                    "hops",
                    -1
                )
        })

    # --------------------------------------------------------
    # GRAPH EDGES
    # --------------------------------------------------------

    graph_edges = []

    for (
        sender,
        receiver,
        data
    ) in G.edges(
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

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {

        # Basic graph
        "nodes":
            G.number_of_nodes(),

        "edges":
            G.number_of_edges(),

        # Suspect
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

        # Clusters
        "clusters":
            cluster_stats,

        # VASP
        "nearest_vasp":
            nearest_vasp,

        "confidence":
            confidence,

        "vasp_connections":
            vasp_connections,

        "vasp_connection_count":
            len(
                vasp_connections
            ),

        # Wallet scores
        "wallet_scores":
            wallet_scores,

        # Frontend graph
        "graph_nodes":
            graph_nodes,

        "graph_edges":
            graph_edges
    }