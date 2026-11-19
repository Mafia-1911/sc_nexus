# MVTec AD Sample Images: Source & Licensing Information

These sample images are drawn directly from the official **MVTec Anomaly Detection (MVTec AD)** benchmark dataset.

## Dataset Reference
* **Authors**: Paul Bergmann, Michael Fauser, David Sattlegger, Carsten Steger
* **Paper**: *"MVTec AD — A Comprehensive Real-World Dataset for Unsupervised Anomaly Detection"*, IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 2019.
* **Official Website**: [https://www.mvtec.com/company/research/datasets/mvtec-ad](https://www.mvtec.com/company/research/datasets/mvtec-ad)
* **Dataset Hosting / Mirror**: Hugging Face dataset mirror `foersben/mvtec-ad` ([https://huggingface.co/datasets/foersben/mvtec-ad](https://huggingface.co/datasets/foersben/mvtec-ad))

## Licensing Terms
* The MVTec AD dataset is made available under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)**.
* **License summary**: You are free to share and adapt the material for non-commercial evaluation and research purposes, provided appropriate attribution is given.
* **Full Legal Code**: [https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode)

## Included Sample Artifacts
1. **`capsule_good.png`**:
   * *Domain*: Pharmaceutical capsules inspection.
   * *Origin Path*: `capsule/test/good/000.png`
   * *Ground Truth Label*: Normal / Flawless (no defect).
   * *Resolution*: 1000 x 1000 pixels RGB.
2. **`capsule_defect.png`**:
   * *Domain*: Pharmaceutical capsules inspection.
   * *Origin Path*: `capsule/test/crack/000.png`
   * *Ground Truth Label*: Anomalous / Defective (surface crack / fracture).
   * *Resolution*: 1000 x 1000 pixels RGB.
3. **`zipper_good.png`**:
   * *Domain*: Garments & apparel hardware quality inspection.
   * *Origin Path*: `zipper/test/good/000.png`
   * *Ground Truth Label*: Normal / Flawless (intact slider and teeth).
   * *Resolution*: 1024 x 1024 pixels RGB.
4. **`zipper_defect.png`**:
   * *Domain*: Garments & apparel hardware quality inspection.
   * *Origin Path*: `zipper/test/broken_teeth/000.png`
   * *Ground Truth Label*: Anomalous / Defective (broken zipper teeth).
   * *Resolution*: 1024 x 1024 pixels RGB.
