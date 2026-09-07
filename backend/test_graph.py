from graph_analysis import load_transactions, analyze_graph


transactions = load_transactions(
    "transactions.csv"
)

result = analyze_graph(
    transactions,
    "0xsuspect"
)

print("\n===== GRAPH ANALYSIS =====")

print("Nodes:", result["nodes"])
print("Edges:", result["edges"])

print(
    "Suspect Cluster:",
    result["suspect_cluster"]
)

print(
    "Cluster Size:",
    result["cluster_size"]
)

print(
    "Suspect In-Degree:",
    result["suspect_in_degree"]
)

print(
    "Suspect Out-Degree:",
    result["suspect_out_degree"]
)

print("\nCluster Members:")

for wallet in result["cluster_members"]:
    print(wallet)

print("\n===== ALL CLUSTERS =====")

for cluster in result["clusters"]:

    print(
        f"\nCluster {cluster['cluster_id']}"
    )

    print(
        "Wallets:",
        cluster["wallet_count"]
    )

    print(
        "Internal edges:",
        cluster["internal_edges"]
    )

    print(
        "Transaction weight:",
        cluster["total_transaction_weight"]
    )

    print(
        "Members:",
        cluster["members"]
    )