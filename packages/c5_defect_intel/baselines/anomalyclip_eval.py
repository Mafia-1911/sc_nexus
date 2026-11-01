"""AnomalyCLIP zero-shot baseline on C5's own split (offline, CPU; C5-AC01).

Cross-dataset protocol: MVTec categories use the checkpoint trained on VisA; StitchNet uses the
one trained on MVTec. Image score = the model's global anomaly probability; pixel map as in the
repo's test.py (multi-layer similarity, Gaussian σ = 4). Same metrics as `cportal_c5.evaluate`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--clip-cache", required=True)
    ap.add_argument("--categories", nargs="+", required=True)
    ap.add_argument("--image-size", type=int, default=518)
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()
    sys.path.insert(0, args.repo)
    import AnomalyCLIP_lib
    import torch
    from PIL import Image
    from prompt_ensemble import AnomalyCLIP_PromptLearner
    from scipy.ndimage import gaussian_filter
    from sklearn.metrics import roc_auc_score
    from utils import get_transform

    torch.set_num_threads(args.threads)
    torch.manual_seed(111)
    size = args.image_size
    params = {
        "Prompt_length": 12,
        "learnabel_text_embedding_depth": 9,
        "learnabel_text_embedding_length": 4,
    }
    model, _ = AnomalyCLIP_lib.load(
        "ViT-L/14@336px", device="cpu", design_details=params, download_root=args.clip_cache
    )
    model.eval()
    model.visual.DAPM_replace(DPAM_layer=20)
    preprocess, _ = get_transform(SimpleNamespace(image_size=size))

    text: dict[str, torch.Tensor] = {}
    for name, sub in (("mvtec", "9_12_4_multiscale"), ("visa", "9_12_4_multiscale_visa")):
        learner = AnomalyCLIP_PromptLearner(model.to("cpu"), params)
        ckpt = torch.load(
            Path(args.repo) / "checkpoints" / sub / "epoch_15.pth", map_location="cpu"
        )
        learner.load_state_dict(ckpt["prompt_learner"])
        with torch.no_grad():
            prompts, tokenized, compound = learner(cls_id=None)
            tf = model.encode_text_learn(prompts, tokenized, compound).float()
            tf = torch.stack(torch.chunk(tf, dim=0, chunks=2), dim=1)
            text[name] = tf / tf.norm(dim=-1, keepdim=True)

    def score(path: str, tf: torch.Tensor) -> tuple[float, np.ndarray, float]:
        t0 = time.perf_counter()
        img = preprocess(Image.open(path).convert("RGB")).reshape(1, 3, size, size)
        with torch.no_grad():
            image_features, patch_features = model.encode_image(img, [6, 12, 18, 24], DPAM_layer=20)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            probs = ((image_features @ tf.permute(0, 2, 1)) / 0.07).softmax(-1)[:, 0, 1]
            maps = []
            for pf in patch_features:
                pf = pf / pf.norm(dim=-1, keepdim=True)
                sim, _ = AnomalyCLIP_lib.compute_similarity(pf, tf[0])
                sm = AnomalyCLIP_lib.get_similarity_map(sim[:, 1:, :], size)
                maps.append((sm[..., 1] + 1 - sm[..., 0]) / 2.0)
            amap = torch.stack(maps).sum(dim=0)[0].numpy()
        return float(probs[0]), gaussian_filter(amap, sigma=4), (time.perf_counter() - t0) * 1000

    manifest = json.loads(Path(args.manifest).read_text())
    out_path = Path(args.out)
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    for cat in args.categories:
        spec = manifest[cat]
        tf = text["mvtec" if cat == "stitch" else "visa"]
        calib = [score(i["path"], tf)[0] for i in spec["calib"]]
        ys, ss, ms, pix_y, pix_s = [], [], [], [], []
        rng = np.random.default_rng(0)
        for item in spec["test"]:
            s, amap, ms_ = score(item["path"], tf)
            ys.append(item["label"] != "good")
            ss.append(s)
            ms.append(ms_)
            if spec.get("masks"):
                if item.get("mask"):
                    m = (
                        np.asarray(
                            Image.open(item["mask"])
                            .convert("L")
                            .resize((size, size), Image.NEAREST)
                        )
                        > 127
                    )
                else:
                    m = np.zeros((size, size), dtype=bool)
                idx = rng.choice(size * size, 6000, replace=False)
                pix_y.append(m.ravel()[idx])
                pix_s.append(amap.ravel()[idx])
        y, s = np.array(ys), np.array(ss)
        thr = float(np.quantile(calib, 0.95))
        flagged = s > thr
        results[cat] = {
            "method": "AnomalyCLIP (ICLR'24), ViT-L/14@336, zero-shot",
            "checkpoint": "trained on MVTec AD"
            if cat == "stitch"
            else "trained on VisA (cross-dataset)",
            "image_size": size,
            "image_auroc": round(float(roc_auc_score(y, s)), 4),
            "pixel_auroc": round(
                float(roc_auc_score(np.concatenate(pix_y), np.concatenate(pix_s))), 4
            )
            if pix_y
            else None,
            "threshold": round(thr, 5),
            "recall_at_fpr": round(float(flagged[y].mean()), 3),
            "fpr_on_test_normals": round(float(flagged[~y].mean()), 3),
            "ms_per_image_cpu": round(float(np.mean(ms)), 1),
            "n_test": len(y),
        }
        out_path.write_text(json.dumps(results, indent=1) + "\n")
        print(cat, results[cat], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
