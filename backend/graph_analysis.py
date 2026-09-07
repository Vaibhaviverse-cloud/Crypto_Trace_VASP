import networkx as nx


def load_transactions(file_path):
    """
    Load transactions from CSV.

    CSV format:
    from,to
    """
    import csv

    transactions = []

    with open(file_path, "r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            sender = row["from"].strip().lower()
            receiver = row["to"].strip().lower()

            if sender and receiver and sender != receiver:
                transactions.append((sender, receiver))

    return transactions


def build_transaction_graph(transactions):
    """
    Build a directed weighted transaction graph.

    Node = wallet
    Edge = transaction
    Weight = number of transactions between two wallets
    """

    G = nx.DiGraph()

    for sender, receiver in transactions:

        if G.has_edge(sender, receiver):
            G[sender][receiver]["weight"] += 1

        else:
            G.add_edge(
                sender,
                receiver,
                weight=1
            )

    return G


def analyze_graph(transactions, suspect_address):

    suspect_address = suspect_address.strip().lower()

    # ------------------------------------------------
    # 1. Build directed graph
    # ------------------------------------------------

    G = build_transaction_graph(transactions)

    if suspect_address not in G:
        G.add_node(suspect_address)

    # ------------------------------------------------
    # 2. Graph features
    # ------------------------------------------------

    suspect_in_degree = G.in_degree(suspect_address)
    suspect_out_degree = G.out_degree(suspect_address)

    # ------------------------------------------------
    # 3. Convert to undirected graph for clustering
    # ------------------------------------------------

    G_cluster = G.to_undirected()

    # ------------------------------------------------
    # 4. Louvain community detection
    # ------------------------------------------------

    communities = nx.community.louvain_communities(
        G_cluster,
        weight="weight",
        seed=42
    )

    # ------------------------------------------------
    # 5. Assign cluster IDs
    # ------------------------------------------------

    node_to_cluster = {}

    for cluster_id, community in enumerate(communities, start=1):

        for node in community:
            node_to_cluster[node] = cluster_id

    # ------------------------------------------------
    # 6. Find suspect cluster
    # ------------------------------------------------

    suspect_cluster = node_to_cluster.get(suspect_address)

    suspect_community = set()

    if suspect_cluster is not None:

        suspect_community = set(
            communities[suspect_cluster - 1]
        )

    # ------------------------------------------------
    # 7. Cluster statistics
    # ------------------------------------------------

    cluster_stats = []

    for cluster_id, community in enumerate(
        communities,
        start=1
    ):

        subgraph = G_cluster.subgraph(community)

        wallet_count = len(community)

        internal_edges = subgraph.number_of_edges()

        total_transaction_weight = sum(
            data.get("weight", 1)
            for _, _, data in subgraph.edges(data=True)
        )

        degrees = dict(subgraph.degree())

        average_degree = (
            sum(degrees.values()) / wallet_count
            if wallet_count
            else 0
        )

        cluster_stats.append({
            "cluster_id": cluster_id,
            "wallet_count": wallet_count,
            "internal_edges": internal_edges,
            "total_transaction_weight": total_transaction_weight,
            "average_degree": round(
                average_degree,
                2
            ),
            "members": sorted(community)
        })

    # ------------------------------------------------
    # 8. Prepare graph nodes for frontend
    # ------------------------------------------------

    graph_nodes = []

    for node in G.nodes():

        graph_nodes.append({
            "id": node,
            "label": node[:10] + "...",
            "cluster": node_to_cluster.get(node)
        })

    # ------------------------------------------------
    # 9. Prepare graph edges for frontend
    # ------------------------------------------------

    graph_edges = []

    for sender, receiver, data in G.edges(data=True):

        graph_edges.append({
            "from": sender,
            "to": receiver,
            "weight": data.get("weight", 1)
        })

    # ------------------------------------------------
    # 10. Return analysis
    # ------------------------------------------------

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),

        "suspect_cluster": suspect_cluster,

        "suspect_in_degree": suspect_in_degree,
        "suspect_out_degree": suspect_out_degree,

        "cluster_size": len(suspect_community),

        "cluster_members": sorted(
            suspect_community
        ),

        "clusters": cluster_stats,

        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges
    }