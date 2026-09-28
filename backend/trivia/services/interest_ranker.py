"""Rank a user's interests from their watch history.

Pure Python — no Django imports.
"""

from collections import Counter


def rank_interests(watch_entries, top_n=5, min_share=0.0):
    """Rank user interests by channel frequency.

    Args:
        watch_entries: List of dicts with a 'channel_name' key. Entries with
            a missing or blank channel name are ignored.
        top_n: Maximum number of interests to return.
        min_share: Drop interests whose share of total watch history is below
            this threshold. 0.0 disables filtering.

    Returns:
        A list of dicts with 'label' (str) and 'weight' (float), sorted by
        weight descending.

    Weight semantics — read this before using the numbers:
        weight = (videos from this channel) / (total videos with a channel)
    Weights therefore express each interest's share of the user's whole
    channel-tagged history. They sum to at most 1.0, and sum to exactly 1.0
    only when `top_n` is at least the number of distinct channels. If you
    need them to sum to 1.0 over the returned set, divide each by the sum
    of the returned weights.
    """
    channel_counts = Counter(
        entry.get("channel_name", "")
        for entry in watch_entries
        if entry.get("channel_name")
    )

    if not channel_counts:
        return []

    total = sum(channel_counts.values())
    ranked = channel_counts.most_common(top_n)

    results = [
        {"label": channel, "weight": round(count / total, 3)}
        for channel, count in ranked
    ]

    if min_share > 0:
        results = [item for item in results if item["weight"] >= min_share]

    return results


def renormalize(ranked):
    """Rescale weights so a returned set sums to 1.0.

    Use this when you need the displayed percentages to add up to 100%.
    Without it, weights express share of the *whole* history, so truncating
    to top_n leaves a remainder (see the weight semantics note above).

    Args:
        ranked: Output of rank_interests().

    Returns:
        A new list with rescaled weights, order preserved.
    """
    total = sum(item["weight"] for item in ranked)
    if not total:
        return ranked
    return [
        {**item, "weight": round(item["weight"] / total, 3)}
        for item in ranked
    ]


def rank_interests_by_cluster(watch_entries, n_clusters=5, random_state=42):
    """Optional extension: cluster video titles by vocabulary.

    Requires scikit-learn, which is NOT a Watchtrivia dependency:

        pip install scikit-learn

    Returns the same [{'label', 'weight'}] shape as rank_interests(), so it
    is a drop-in replacement.

    Note: with fewer entries than clusters, or near-duplicate titles, KMeans
    emits ConvergenceWarning and may produce empty clusters. Guard with
    `if len(titles) < n_clusters * 2: fall back to channel frequency`.
    """
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    titles = [e.get("video_title", "") for e in watch_entries if e.get("video_title")]
    if len(titles) < n_clusters * 2:
        return rank_interests(watch_entries, top_n=n_clusters)

    vectorizer = TfidfVectorizer(
        max_features=1000,
        stop_words="english",
        min_df=2,          # ignore words appearing in only one title
    )
    matrix = vectorizer.fit_transform(titles)

    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    kmeans.fit(matrix)

    terms = vectorizer.get_feature_names_out()
    results = []
    for cluster_id in range(n_clusters):
        indices = [i for i, label in enumerate(kmeans.labels_) if label == cluster_id]
        if not indices:
            continue
        centroid = kmeans.cluster_centers_[cluster_id]
        top_terms = [
            terms[i]
            for i in centroid.argsort()[::-1][:3]
            if centroid[i] > 0
        ]
        if not top_terms:
            continue
        results.append({
            "label": " / ".join(top_terms).title(),
            "weight": round(len(indices) / len(titles), 3),
        })

    return sorted(results, key=lambda item: item["weight"], reverse=True)[:n_clusters]
