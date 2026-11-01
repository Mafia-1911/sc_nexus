# AnomalyCLIP baseline (C5-AC01)

AnomalyCLIP (Zhou et al., ICLR 2024, MIT licence) scored on C5's own split, zero-shot and on the
CPU, so it can be compared row by row with DINOv2 few/zero-shot in
`docs/model-cards/c5-defect-intel.md`. It runs in an isolated PyTorch venv under
`data/cache/aclip/` (never committed) so PyTorch never enters the app's dependencies.

Cross-dataset protocol (as in the paper): MVTec categories use the checkpoint trained on VisA;
StitchNet uses the one trained on MVTec. Threshold = 95th percentile of the same 30 calibration
normals; image size 518; pixel AUROC on 6,000 sampled pixels per image.

```bash
A=data/cache/aclip
git clone https://github.com/zqhang/AnomalyCLIP.git $A/repo
git -C $A/repo checkout 3911738c0867544f545a076ad78f3f11d9ecbfdf   # 2025-07-08, checkpoints included
uv venv --python 3.12 $A/venv
uv pip install --python $A/venv/bin/python --index-url https://download.pytorch.org/whl/cpu \
  torch==2.5.1 torchvision==0.20.1
uv pip install --python $A/venv/bin/python numpy scipy scikit-learn pillow ftfy regex tqdm
uv run python packages/c5_defect_intel/baselines/aclip_manifest.py $A/manifest.json
$A/venv/bin/python -I packages/c5_defect_intel/baselines/anomalyclip_eval.py \
  --repo $PWD/$A/repo --manifest $A/manifest.json --clip-cache $PWD/$A/clip \
  --out docs/model-cards/c5-eval-anomalyclip.json \
  --categories pill capsule stitch carpet leather --threads 4
```

The first run downloads OpenAI CLIP ViT-L/14@336px (934 MB, SHA-256 checked) into `$A/clip`.
Results are written per category to `docs/model-cards/c5-eval-anomalyclip.json`.
