"""DS-SUP-02 · SupplyGraph: Bangladesh FMCG supply-chain graph benchmark (GitHub)."""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

API = "https://api.github.com/repos"


class SupplyGraph(Connector):
    ds_id = "DS-SUP-02"
    title = "SupplyGraph (CIOL-SUST)"

    def probe(self, ctx: ProbeContext) -> None:
        for repo in ("CIOL-SUST/SupplyGraph", "ciol-researchlab/SupplyGraph"):
            slug = repo.split("/")[0].lower().replace("-", "_")
            meta = ctx.http(
                ProbeCall(
                    f"repo_{slug}",
                    f"{API}/{repo}",
                    "meta",
                    headers={"Accept": "application/vnd.github+json"},
                )
            )
            if meta.ok and isinstance(meta.parsed, dict):
                ctx.metric(
                    f"repo_{slug}",
                    {
                        k: meta.parsed.get(k)
                        for k in (
                            "full_name",
                            "pushed_at",
                            "license",
                            "size",
                            "stargazers_count",
                            "default_branch",
                        )
                    },
                )
                tree = ctx.http(
                    ProbeCall(
                        f"tree_{slug}",
                        f"{API}/{repo}/git/trees/{meta.parsed['default_branch']}",
                        sample=True,
                        params={"recursive": "1"},
                        records="tree[]",
                        headers={"Accept": "application/vnd.github+json"},
                    )
                )
                if isinstance(tree.parsed, dict):
                    files = [t["path"] for t in tree.parsed.get("tree", []) if t["type"] == "blob"]
                    ctx.metric(f"files_{slug}", {"count": len(files), "sample": files[:30]})


CONNECTOR = SupplyGraph()
