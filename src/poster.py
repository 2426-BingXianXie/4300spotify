"""Build the one-page PDF poster for the DS 4300 Spotify graph project."""

from __future__ import annotations

import logging
import os
import tempfile
import textwrap
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "spotify-mpl-cache"))

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

from src.config import ROOT, get_database, get_driver

log = logging.getLogger(__name__)

OUTPUT_PDF = ROOT / "poster.pdf"

RECS = [
    "My Girlfriend's Girlfriend",
    "コンセプトの戦い",
    "You Will Payback! (Re-Recorded)",
    "To the South",
    "About You",
]

RECOMMENDATIONS = [
    ("1", "Type O Negative", "October Rust\n(Special Edition)", "My Girlfriend's\nGirlfriend"),
    ("2", "Yuki Hayashi", "Haikyu!! Karasuno vs\nShiratorizawa OST", "コンセプトの戦い"),
    ("3", "Confess", "Back to My Future", "You Will Payback!\n(Re-Recorded)"),
    ("4", "Motorama", "Calendar", "To the South"),
    ("5", "The 1975", "Being Funny In A\nForeign Language", "About You"),
]

APPROACH = (
    "The pipeline samples ~3,000 Spotify tracks stratified by track_genre, "
    "force-including every song by The Strokes and Regina Spektor. After "
    "z-scoring nine audio "
    "features (danceability, energy, loudness, speechiness, acousticness, "
    "instrumentalness, liveness, valence, tempo), each song is connected to its "
    "K = 10 nearest neighbours by Euclidean distance, yielding a sparse "
    "SIMILAR_TO graph. Songs, artists, and genres are modelled as distinct nodes. "
    "Recommendation generation runs personalized PageRank (Neo4j GDS) over SIMILAR_TO, "
    "seeded with the user's liked songs and weighted by score = 1 / (1 + distance). "
    "The top-ranked tracks are returned after excluding artists the user already "
    "likes. The approach generalises to any user; Prof. Rachlin is just one seed set."
)

METRICS = (
    "Song nodes: 3,045\n"
    "Artist nodes: 3,252\n"
    "Genre nodes: 114\n"
    "Edges (SIMILAR_TO): 42,384 directed\n"
    "Edges (unique undirected): 21,192\n"
    "Density: (2 x 21,192) / (3,045 x 3,044) ~= 0.00457"
)

SIMILARITY_RULE = (
    "Two songs are connected by a SIMILAR_TO edge iff one is among the other's "
    "10 nearest neighbours in z-scored audio-feature space, using Euclidean "
    "distance. Edges are symmetric and weighted by score = 1 / (1 + distance)."
)

VIZ_QUERY_TEMPLATE = """
MATCH (a:Artist {{name: 'The Strokes'}})-[:PERFORMED]->(strokes:Song)
WITH collect(DISTINCT strokes) AS strokes_songs
MATCH (rec:Song) WHERE rec.name IN $recs
WITH strokes_songs, collect(DISTINCT rec) AS rec_songs
UNWIND strokes_songs AS s
UNWIND rec_songs AS r
MATCH path = (s)-[:SIMILAR_TO*1..{hops}]-(r)
WITH strokes_songs, rec_songs,
     collect(DISTINCT path) AS paths
UNWIND paths AS p
UNWIND nodes(p)         AS n
UNWIND relationships(p) AS e
RETURN
  collect(DISTINCT {{ id: elementId(n), name: n.name,
                     is_strokes: n IN strokes_songs,
                     is_rec:     n IN rec_songs }}) AS nodes,
  collect(DISTINCT {{ src: elementId(startNode(e)),
                     dst: elementId(endNode(e)),
                     score: e.score }}) AS edges;
"""


FONT_PATHS = [
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc"),
]


def _poster_font() -> FontProperties:
    """Pick a system font that supports CJK labels on the graph.

    Returns: ``FontProperties`` for matplotlib text (falls back to DejaVu Sans).
    """
    for path in FONT_PATHS:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            return FontProperties(fname=str(path))
    return FontProperties(family="DejaVu Sans")


def fetch_subgraph(max_hops: int = 3) -> tuple[list[dict], list[dict], int]:
    """Query Neo4j for paths from Strokes seeds to all five recommendation songs.

    Returns: ``(nodes, edges, hops_used)`` where each node has ``id``, ``name``,
    ``is_strokes``, ``is_rec``; edges have ``src``, ``dst``, ``score``.
    Raises: ``RuntimeError`` if no hop limit up to ``max_hops`` connects every rec.
    """
    driver = get_driver()
    try:
        with driver.session(database=get_database()) as session:
            for hops in range(2, max_hops + 1):
                record = session.run(VIZ_QUERY_TEMPLATE.format(hops=hops), recs=RECS).single()
                nodes = record["nodes"] if record else []
                edges = record["edges"] if record else []
                recs_found = {n["name"] for n in nodes if n.get("is_rec")}
                log.info(
                    "viz subgraph hops=%s: %s nodes, %s edges, %s/%s recs found",
                    hops,
                    len(nodes),
                    len(edges),
                    len(recs_found),
                    len(RECS),
                )
                if len(recs_found) == len(RECS):
                    return nodes, edges, hops
    finally:
        driver.close()
    raise RuntimeError("Could not find paths from The Strokes to every recommendation.")


def build_graph(nodes: list[dict], edges: list[dict]) -> nx.Graph:
    """Convert Neo4j subgraph records into an undirected NetworkX graph.

    Returns: Graph with node attrs ``label``, ``is_strokes``, ``is_rec`` and edge ``score``.
    """
    graph = nx.Graph()
    for node in nodes:
        graph.add_node(
            node["id"],
            label=node["name"],
            is_strokes=bool(node["is_strokes"]),
            is_rec=bool(node["is_rec"]),
        )
    for edge in edges:
        if edge["src"] in graph and edge["dst"] in graph:
            graph.add_edge(edge["src"], edge["dst"], score=edge.get("score", 0.0))
    return graph


def _short_label(label: str, width: int = 17) -> str:
    """Wrap recommendation song titles for on-graph labels; hide others.

    Returns: Wrapped label string for rec nodes, or ``""`` for non-rec nodes.
    """
    if label in RECS:
        return "\n".join(textwrap.wrap(label, width=width, break_long_words=False))
    return ""


def draw_poster(graph: nx.Graph, hops: int, output_path: Path = OUTPUT_PDF) -> None:
    """Render the one-page landscape poster PDF with graph, text, and table.

    Side effects: Writes ``output_path`` (default ``poster.pdf``) via matplotlib.
    """
    font = _poster_font()
    font_family = font.get_name()
    plt.rcParams.update(
        {
            "font.family": [font_family, "DejaVu Sans", "sans-serif"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.facecolor": "#fbfaf7",
            "figure.facecolor": "#fbfaf7",
        }
    )

    fig = plt.figure(figsize=(16, 9), constrained_layout=False)
    gs = GridSpec(
        8,
        12,
        figure=fig,
        left=0.035,
        right=0.98,
        top=0.94,
        bottom=0.055,
        wspace=0.55,
        hspace=0.85,
    )

    title_ax = fig.add_subplot(gs[0, :])
    graph_ax = fig.add_subplot(gs[1:8, :7])
    approach_ax = fig.add_subplot(gs[1:3, 7:12])
    metrics_ax = fig.add_subplot(gs[3:4, 7:12])
    table_ax = fig.add_subplot(gs[4:7, 7:12])
    rule_ax = fig.add_subplot(gs[7:8, 7:12])

    for ax in (title_ax, approach_ax, metrics_ax, table_ax, rule_ax):
        ax.axis("off")

    title_ax.text(
        0,
        0.55,
        "Spotify Graph Music Recommender — DS 4300",
        fontsize=25,
        fontweight="bold",
        fontfamily=font_family,
        color="#141414",
        va="center",
    )
    title_ax.text(
        0.995,
        0.55,
        "Personalized PageRank on a kNN audio-feature graph",
        fontsize=11,
        fontfamily=font_family,
        color="#55524d",
        ha="right",
        va="center",
    )

    pos = nx.spring_layout(graph, seed=4300, k=0.45)
    node_colors = []
    node_sizes = []
    for _, attrs in graph.nodes(data=True):
        if attrs["is_strokes"]:
            node_colors.append("#c74440")
            node_sizes.append(130)
        elif attrs["is_rec"]:
            node_colors.append("#2f9e62")
            node_sizes.append(430)
        else:
            node_colors.append("#b8b7b2")
            node_sizes.append(42)

    edge_widths = [0.45 + 1.1 * float(attrs.get("score") or 0.0) for _, _, attrs in graph.edges(data=True)]
    nx.draw_networkx_edges(
        graph,
        pos,
        ax=graph_ax,
        width=edge_widths,
        alpha=0.34,
        edge_color="#77736b",
    )
    nx.draw_networkx_nodes(
        graph,
        pos,
        ax=graph_ax,
        node_color=node_colors,
        node_size=node_sizes,
        linewidths=0.7,
        edgecolors="#ffffff",
    )
    labels = {node: _short_label(attrs["label"]) for node, attrs in graph.nodes(data=True)}
    labels = {node: label for node, label in labels.items() if label}
    nx.draw_networkx_labels(
        graph,
        pos,
        labels=labels,
        ax=graph_ax,
        font_size=8,
        font_weight="normal",
        font_family=font_family,
        font_color="#202020",
        bbox={"boxstyle": "round,pad=0.18", "fc": "#fbfaf7", "ec": "none", "alpha": 0.86},
    )
    graph_ax.set_title(
        f"Subgraph: The Strokes songs to top recommendations (<= {hops} SIMILAR_TO hops)",
        fontsize=13,
        fontweight="bold",
        fontfamily=font_family,
        loc="left",
        pad=12,
    )
    graph_ax.set_xticks([])
    graph_ax.set_yticks([])
    for spine in graph_ax.spines.values():
        spine.set_visible(False)
    graph_ax.legend(
        handles=[
            Line2D([0], [0], marker="o", color="w", label="The Strokes seed songs", markerfacecolor="#c74440", markersize=8),
            Line2D([0], [0], marker="o", color="w", label="Recommended songs", markerfacecolor="#2f9e62", markersize=10),
            Line2D([0], [0], marker="o", color="w", label="Bridge / neighbour songs", markerfacecolor="#b8b7b2", markersize=7),
        ],
        loc="lower left",
        frameon=False,
        fontsize=9,
    )

    approach_ax.text(0, 1, "Approach", fontsize=13, fontweight="bold", va="top", color="#141414")
    approach_ax.text(
        0,
        0.78,
        textwrap.fill(APPROACH, width=82),
        fontsize=8.3,
        va="top",
        linespacing=1.18,
        color="#2d2a27",
    )

    metrics_ax.text(0, 1, "Graph Size", fontsize=13, fontweight="bold", va="top", color="#141414")
    metrics_ax.text(
        0,
        0.66,
        METRICS,
        fontsize=9.2,
        va="top",
        linespacing=1.18,
        color="#2d2a27",
    )

    table_ax.text(0, 1, "Five Recommendations", fontsize=13, fontweight="bold", va="top", color="#141414")
    table = table_ax.table(
        cellText=RECOMMENDATIONS,
        colLabels=["#", "Artist", "Album", "Track"],
        colWidths=[0.06, 0.22, 0.38, 0.34],
        cellLoc="left",
        loc="upper left",
        bbox=[0, 0.02, 1, 0.82],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.0)
    table.scale(1, 1.28)
    for (row, col), cell in table.get_celld().items():
        cell.get_text().set_fontproperties(font)
        cell.set_edgecolor("#ddd8cf")
        cell.set_linewidth(0.45)
        if row == 0:
            cell.set_facecolor("#242424")
            cell.set_text_props(color="white", weight="bold")
        else:
            cell.set_facecolor("#ffffff" if row % 2 else "#f3f1ec")
        if col == 0:
            cell.set_text_props(ha="center")

    rule_ax.text(0, 1, "Similarity Rule", fontsize=13, fontweight="bold", va="top", color="#141414")
    rule_ax.text(
        0,
        0.62,
        textwrap.fill(SIMILARITY_RULE, width=90),
        fontsize=8.6,
        va="top",
        linespacing=1.15,
        color="#2d2a27",
    )

    fig.savefig(output_path, format="pdf", bbox_inches="tight")
    plt.close(fig)
    log.info("wrote %s", output_path)


def main() -> None:
    """CLI entry point: fetch subgraph, build NetworkX graph, write ``poster.pdf``."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    nodes, edges, hops = fetch_subgraph()
    graph = build_graph(nodes, edges)
    draw_poster(graph, hops)


if __name__ == "__main__":
    main()
