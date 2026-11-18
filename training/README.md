# ADHD — In-Sensor Features and HDC Training Experiments

This directory contains the **Python reference implementation and training/evaluation pipeline** for ADHD (Analog-Domain Hyperdimensional Detection). It complements the [FPGA/ASIC HDC backend](../README.md) in this repository.

The experimental pipeline combines sensor-oriented low-bitwidth visual feature extraction with **binary hyperdimensional computing (HDC)**. The code evaluates regional and convolutional feature frontends using hard, 4-level features and binary HDC encoding/classification at inference.

> **Implementation scope:** This script is a PyTorch *functional* model of the proposed in-sensor feature computation and an offline training/evaluation pipeline. It does **not** implement a physical image sensor, analog circuit nonidealities, sensor energy, or measured end-to-end hardware latency. RGB-to-grayscale conversion and any resizing occur in software in these experiments.

## Included configurations

Set `FEATURE_EXTRACTOR` near the top of [`adhd_experiments.py`](adhd_experiments.py):

| Setting | Frontend | Offline training |
| --- | --- | --- |
| `"regional"` | Fixed-threshold 2×2 regional averaging | Initialize class prototypes by majority bundling, then apply integer, margin-based prototype retraining. Thresholds stay fixed. |
| `"regional_joint"` | 2×2 regional averaging; three shared trainable quantization thresholds | Joint STE/gradient training of regional thresholds and class prototype scores. Starts from `[0.10, 0.35, 0.70]`. |
| `"conv"` | Modified AppCiP-style 3×3 convolution, spatial averaging, and three thresholds per channel | Joint STE/gradient training of fake-quantized signed INT8 convolution weights, thresholds, and class prototype scores. |

The convolutional configuration supports `CONV_CHANNELS = 1` or `4` (default `4`). All configurations produce **196 four-level features**, corresponding to **392 bits per image** at the proposed sensor-output boundary.

### Regional frontend (28×28 grayscale input)

1. Calculate nonoverlapping **2×2 average intensity**, producing a 14×14 grid (196 values).
2. Compare each value with **three shared thresholds** to assign levels 0–3.
3. Emit 196 two-bit feature values (392 bits/image).

For the RGB **SVHN** and **CIFAR-10** datasets, the training loader converts to grayscale and resizes 32×32 images to 28×28 in software. The MNIST-family and OCTMNIST data are already 28×28 grayscale.

### Convolutional frontend (32×32 grayscale input)

1. For a 28×28 grayscale dataset, **zero-pad by two pixels per side** to obtain 32×32; native 32×32 SVHN/CIFAR-10 is converted to grayscale without resizing.
2. Apply **3×3 valid convolution**, stride 1, no bias, with fake-quantized signed INT8 weights: 30×30 per output channel.
3. Select the central **28×28** convolution responses per channel.
4. Average-pool: with 4 channels use **4×4 pooling → 4×7×7 = 196 values**; with 1 channel use **2×2 pooling → 14×14 = 196 values**.
5. Quantize using **three trainable thresholds per channel** to levels 0–3, yielding 392 bits/image.

Convolutional thresholds are initialized from nonzero training-set convolution responses (25th, 50th, and 75th percentiles), not from `LEVEL_THRESHOLDS`.

### Shared binary HDC backend (Python reference)

- Binary feature HVs are derived from Sylvester Hadamard parity with deterministic row stride `1597`; level HVs use the configured correlation mode.
- Select a level HV per feature, bind using XOR, and bundle the 196 bound HVs by integer popcount with `QUERY_POPCOUNT_THRESHOLD = 96`.
- Initialize one binary class prototype per class and select predictions by **minimum Hamming distance**.
- The hypervector dimension is controlled by `HDC_DIM` (default **8192**). Training may use continuous surrogate parameters and gradients, but reported inference uses **hard quantized features and binary HDC operations**.

The FPGA hardware in the parent repository has its own independently verified implementation and validation instructions; this script is **not** a full FPGA deployment flow or an automated end-to-end hardware/ML integration.

## Supported datasets

Use the exact `DATASET` string below. Downloading is handled by torchvision or MedMNIST on first use.

| Dataset setting | Classes | Training | Validation | Test | Split |
| --- | ---: | ---: | ---: | ---: | --- |
| `"MNIST"` | 10 | 54,000 | 6,000 | 10,000 | Stratified from official train |
| `"FashionMNIST"` | 10 | 54,000 | 6,000 | 10,000 | Stratified from official train |
| `"EMNISTLetters"` | 26 | 112,320 | 12,480 | 20,800 | Stratified from official train; labels remapped to 0–25 |
| `"SVHN"` | 10 | 65,931 | 7,326 | 26,032 | Stratified from official train |
| `"CIFAR10"` | 10 | 45,000 | 5,000 | 10,000 | Stratified from official train |
| `"OCTMNIST"` | 4 | 97,477 | 10,832 | 1,000 | Official MedMNIST train/val/test |

The stratified splits use `SEED = 42`. Validation data are used for checkpoint selection; the official test split is separate.

## Installation

Python **3.10+** is recommended. From the repository root:

```bash
cd training
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For GPU training, install a mutually compatible **PyTorch + torchvision** pair for your CUDA driver/runtime using the official PyTorch installation instructions, then install the remaining dependencies. The script automatically selects CUDA when available, otherwise CPU.

## Run an experiment

Edit these settings near the top of `adhd_experiments.py`:

```python
DATASET = "CIFAR10"
FEATURE_EXTRACTOR = "regional_joint"  # regional | regional_joint | conv
HDC_DIM = 8192
RESULTS_DIR = Path("./results_CIFAR10_regional_joint_8192")

# Only for FEATURE_EXTRACTOR = "conv":
CONV_CHANNELS = 4  # 1 or 4
```

Then run, from inside `training/`:

```bash
python adhd_experiments.py
```

The script runs **one dataset and one selected method per invocation**. For reproducible comparisons, keep the seed, dataset splits, HDC dimension, and preprocessing conventions consistent. Change `RESULTS_DIR` for each experiment to avoid mixing outputs.

### Training settings

- Fixed regional training: `RETRAIN_EPOCHS`, `RETRAIN_MARGIN`, `RETRAIN_INIT_STRENGTH`, `RETRAIN_STEP`.
- Fully joint regional training: `REGIONAL_JOINT_EPOCHS`, `JOINT_THRESHOLD_LR`, `JOINT_PROTOTYPE_LR` (and `BATCH_SIZE`).
- Joint convolutional training: `JOINT_EPOCHS`, `JOINT_BATCH_SIZE`, `JOINT_CONV_LR`, `JOINT_THRESHOLD_LR`, `JOINT_PROTOTYPE_LR`.
- Quantization: `LEVEL_THRESHOLDS`, `NUM_LEVELS`, `QUERY_POPCOUNT_THRESHOLD`.

## Saved outputs

Each experiment creates a timestamped subdirectory inside `RESULTS_DIR`, containing relevant files such as:

| Output | Content |
| --- | --- |
| `results.json`, `report.txt` | Accuracy, experiment settings, runtime measurements, and per-class accuracy |
| `training_history.csv` | Validation accuracy and training diagnostics by epoch |
| `confusion_matrix.csv` | Classification confusion matrix |
| `feature_distribution.csv` | Counts of quantized feature levels |
| `best_model.pt` | Best validation-selected binary HVs, metadata, and (for joint modes) learned frontend state |
| `hardware_model/` | Packed binary HDC HV exports, manifest, and applicable learned thresholds or convolution weights |
| `threshold_precision.csv` | For joint modes: post-training test of FP32 versus 6/8/10/12-bit threshold representation |

Runtime figures reported by the Python script are software execution times, **not** sensor/FPGA energy or end-to-end hardware latency.

## Repository relationship

The top-level [`README.md`](../README.md) documents synthesizable HDC hardware, verification, and FPGA/ASIC measurements. This directory separately documents **offline training and feature-extraction experiments**. The two components share the binary-HDC concept and feature format, but no combined sensor-to-FPGA system benchmark is claimed here.

## License

See the [repository license](../LICENSE).
