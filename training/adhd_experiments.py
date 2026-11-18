import csv
import copy  # ADDED NEW: Save the best joint-training model parameters.
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn  # ADDED NEW: Define trainable convolution layers and parameters.
import torch.nn.functional as F
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms
from medmnist import OCTMNIST

# ============================================================
# CPU THREAD CONFIGURATION
# ============================================================

# Limit PyTorch CPU threads to reduce contention when running
# multiple dataset experiments simultaneously.
torch.set_num_threads(4)

# ============================================================
# 2. EXPERIMENT CONFIGURATION
# ============================================================

# Dataset
DATASET = "CIFAR10"  # "MNIST", "FashionMNIST", or "SVHN" "EMNISTLetters", "OCTMNIST"
DATA_DIR = Path("./data")
RESULTS_DIR = Path("./results_CIFAR10_regional_joint_8192")  # Change this to a new directory for each dataset and feature extractor.

# ============================================================
# ADDED NEW: APPCIP CONVOLUTIONAL FEATURE EXTRACTOR
# ============================================================

# Select between the original regional feature extractor
# and the new jointly trained convolutional feature extractor.
FEATURE_EXTRACTOR = "regional_joint"      # "regional", "regional_joint" or "conv"

# Number of convolutional output channels.
# 1 channel -> 2x2 average pooling -> 196 features.
# 4 channels -> 4x4 average pooling -> 196 features.
CONV_CHANNELS = 4               # Supported: 1 or 4

# Convolution configuration.
CONV_KERNEL_SIZE = 3            # 3x3 convolution, stride 1
CONV_WEIGHT_BITS = 8            # Signed INT8 weights (-128 to +127)


# ============================================================
# ADDED NEW: JOINT CNN-HDC TRAINING CONFIGURATION
# ============================================================

# Training settings for the convolutional feature extractor
# and HDC class prototypes.
# JOINT_EPOCHS = 200
JOINT_BATCH_SIZE = 32

RETRAIN_EPOCHS = 100         # Original regional method
REGIONAL_JOINT_EPOCHS = 200  # Regional joint method
JOINT_EPOCHS = 200           # Convolutional joint method

# Separate learning rates for the three trainable components.
JOINT_CONV_LR = 1e-3            # Convolution weights
JOINT_THRESHOLD_LR = 1e-3       # Feature quantization thresholds
JOINT_PROTOTYPE_LR = 1e-2       # HDC class prototype scores

# Temperature for cross-entropy calculated from Hamming distances.
JOINT_LOSS_TEMPERATURE = 64.0

# Temperatures used for differentiable surrogate gradients.
# These affect training gradients, not the binary inference operations.
FEATURE_SOFT_TEMPERATURE = 0.10
BUNDLE_SOFT_TEMPERATURE = 5.0
PROTOTYPE_SOFT_TEMPERATURE = 1.0

# Number of training batches used to initialize the
# convolutional feature quantization thresholds.
THRESHOLD_INIT_BATCHES = 8

# Image and feature extraction
IMAGE_SIZE = 28                # Original MNIST image size
REGION_SIZE = 2                # 2x2 pixel regions
NUM_LEVELS = 4                 # 4 intensity levels (2 bits per feature)

# HDC configuration
HDC_DIM = 8192          # Hypervector dimension
FEATURE_HV_MODE = "hadamard"   # "random": approximately orthogonal HVs
                              # "hadamard": exactly pairwise orthogonal HVs
LEVEL_MODE = "correlated"      # Correlated level HVs preserve intensity similarity or "random"

# Fraction of bits flipped between the first and last level HV
# 0.5 means L0 and L3 differ in 50% of their bits
LEVEL_CORRELATION_RANGE = 1.0

# Three shared analog thresholds; four quantized intensity levels (2 bits/region)
LEVEL_THRESHOLDS = [0.10, 0.35, 0.70]
# LEVEL_THRESHOLDS = [0.30, 0.45, 0.60]
# LEVEL_THRESHOLDS = [0.125, 0.25, 0.375, 0.50, 0.625, 0.75, 0.875]


QUERY_POPCOUNT_THRESHOLD = 96 #96

# Retrain only the class prototypes. Select the best epoch on validation data.
# SVHN has 73,257 official training images. We will reserve approximately 10% for validation.
VALIDATION_SAMPLES = (
    12480 if DATASET == "EMNISTLetters"
    else 7326 if DATASET == "SVHN"
    else 5000 if DATASET == "CIFAR10"
    else 6000
)
# RETRAIN_EPOCHS = 75
# REGIONAL_JOINT_EPOCHS = 200  # Regional joint method
RETRAIN_INIT_STRENGTH = 64 #32 #16   # Scale of initial signed class-majority votes
RETRAIN_STEP = 1             # Integer update for each classification error

RETRAIN_MARGIN = 16

# Training configuration
BATCH_SIZE = 256
SEED = 42


# Hardware
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ============================================================
# DERIVED PARAMETERS
# ============================================================

REGIONS_PER_SIDE = IMAGE_SIZE // REGION_SIZE
NUM_FEATURES = REGIONS_PER_SIDE ** 2

BITS_PER_FEATURE = (NUM_LEVELS - 1).bit_length()
SENSOR_BITS_PER_IMAGE = NUM_FEATURES * BITS_PER_FEATURE

# ============================================================
# VALIDATION
# ============================================================

assert IMAGE_SIZE % REGION_SIZE == 0, \
    "Image size must be divisible by region size."

assert NUM_LEVELS >= 2, \
    "Number of levels must be at least 2."

assert HDC_DIM > 0, \
    "HDC dimension must be positive."

assert 0.0 <= LEVEL_CORRELATION_RANGE <= 1.0, \
    "LEVEL_CORRELATION_RANGE must be between 0 and 1."
assert len(LEVEL_THRESHOLDS) == NUM_LEVELS - 1
assert all(0.0 <= a < b < 1.0 for a, b in
           zip([0.0] + LEVEL_THRESHOLDS[:-1], LEVEL_THRESHOLDS))
assert VALIDATION_SAMPLES > 0
assert RETRAIN_EPOCHS >= 0
assert RETRAIN_INIT_STRENGTH > 0 and RETRAIN_STEP > 0

# ============================================================
# ADDED NEW: VALIDATION FOR CONVOLUTIONAL FEATURE EXTRACTOR
# ============================================================

# Only the original regional extractor and new convolutional
# extractor are supported.
assert FEATURE_EXTRACTOR in ("regional", "regional_joint", "conv")

# These checks apply only to the convolutional approach.
# The original regional pipeline remains unchanged.
if FEATURE_EXTRACTOR == "conv":

    # Both configurations must produce exactly 196 features.
    # 1 channel -> 2x2 pooling -> 1x14x14 = 196
    # 4 channels -> 4x4 pooling -> 4x7x7 = 196
    assert CONV_CHANNELS in (1, 4)

    # The proposed AppCiP frontend uses 3x3 convolution
    # with signed 8-bit quantized weights.
    assert CONV_KERNEL_SIZE == 3 and CONV_WEIGHT_BITS == 8

    # Keep the same HDC input format as the original pipeline.
    assert NUM_FEATURES == 196 and NUM_LEVELS == 4

    # Joint training requires a positive batch size.
    assert JOINT_BATCH_SIZE > 0 and JOINT_EPOCHS >= 0

    # Temperatures must be positive for the loss and
    # differentiable surrogate calculations.
    assert all(x > 0 for x in (
        JOINT_LOSS_TEMPERATURE,
        FEATURE_SOFT_TEMPERATURE,
        BUNDLE_SOFT_TEMPERATURE,
        PROTOTYPE_SOFT_TEMPERATURE
    ))


# ============================================================
# 3. RANDOM SEED AND DATASET LOADING
# ============================================================

def set_seed(seed):
    # Set random seeds for reproducible experiments
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_dataset():

    # ============================================================
    # OCTMNIST DATASET
    # ============================================================

    if DATASET == "OCTMNIST":

        # Original OCTMNIST images are 28x28 grayscale.
        transform = transforms.ToTensor()

        # Convolutional approach requires 32x32 input.
        # Add a 2-pixel zero border on each side.
        if FEATURE_EXTRACTOR == "conv":

            transform = transforms.Compose([
                transforms.Pad(2, fill=0),
                transforms.ToTensor()
            ])

        # Convert MedMNIST labels from shape [1] to scalar integers.
        # This is required by our existing HDC training code.
        options = dict(
            root=str(DATA_DIR),
            download=True,
            size=28,
            transform=transform,
            target_transform=lambda y: int(y.item())
        )

        # Use the OFFICIAL splits.
        train_data = OCTMNIST(split="train", **options)
        val_data = OCTMNIST(split="val", **options)
        test_data = OCTMNIST(split="test", **options)

        # Four classification categories.
        class_names = [
            "CNV",
            "DME",
            "DRUSEN",
            "NORMAL"
        ]

        # Make MedMNIST compatible with our existing code.
        for data in (train_data, val_data, test_data):

            data.classes = class_names

            data.targets = torch.as_tensor(
                data.labels.reshape(-1),
                dtype=torch.long
            )

        # Verify official dataset sizes.
        assert (
            len(train_data),
            len(val_data),
            len(test_data)
        ) == (97477, 10832, 1000)

        # Preserve compatibility with existing train_hdc().
        train_subset = Subset(
            train_data,
            range(len(train_data))
        )

        val_subset = Subset(
            val_data,
            range(len(val_data))
        )

        # Create data loaders.
        train_loader = DataLoader(
            train_subset,
            batch_size=BATCH_SIZE,
            shuffle=True
        )

        val_loader = DataLoader(
            val_subset,
            batch_size=BATCH_SIZE,
            shuffle=False
        )

        test_loader = DataLoader(
            test_data,
            batch_size=BATCH_SIZE,
            shuffle=False
        )

        print(f"Dataset: {DATASET}")
        print(f"Training samples: {len(train_subset)}")
        print(f"Validation samples: {len(val_subset)}")
        print(f"Test samples: {len(test_data)}")

        return train_loader, val_loader, test_loader, class_names

    if DATASET in ("SVHN", "CIFAR10"):

        # transform = transforms.Compose([
        #     transforms.ToTensor(),

        #     # RGB -> single channel using equal-weight averaging
        #     transforms.Lambda(
        #         lambda img: img.mean(dim=0, keepdim=True)
        #     ),

        #     transforms.Resize(
        #         (28, 28),
        #         interpolation=transforms.InterpolationMode.BILINEAR,
        #         antialias=True
        #     )
        # ])

        transform = transforms.Compose([
            transforms.Grayscale(num_output_channels=1),
            transforms.Resize(
                (28, 28),
                interpolation=transforms.InterpolationMode.BILINEAR,
                antialias=True
            ),
            transforms.ToTensor()
        ])

        # ============================================================
        # ADDED NEW: SVHN PREPROCESSING FOR CONVOLUTIONAL MODE
        # ============================================================

        # The original regional pipeline uses 28x28 grayscale images.
        # The convolutional pipeline uses 32x32 grayscale images.
        # SVHN is originally RGB, so we convert it to grayscale without resizing.
        # Grayscale conversion is performed in software and is not
        # included in the modeled AppCiP hardware.

        if FEATURE_EXTRACTOR == "conv":
            transform = transforms.Compose([
                transforms.Grayscale(num_output_channels=1),
                transforms.ToTensor()
            ])

        # ============================================================
        # SVHN AND CIFAR-10 DATASET LOADING
        # ============================================================

        if DATASET == "SVHN":

            train_data = datasets.SVHN(
                root=str(DATA_DIR),
                split="train",
                download=True,
                transform=transform
            )

            test_data = datasets.SVHN(
                root=str(DATA_DIR),
                split="test",
                download=True,
                transform=transform
            )

            # Make SVHN compatible with our HDC pipeline.
            train_data.targets = torch.as_tensor(train_data.labels)
            train_data.classes = [str(i) for i in range(10)]

        else:  # CIFAR10

            train_data = datasets.CIFAR10(
                root=str(DATA_DIR),
                train=True,
                download=True,
                transform=transform
            )

            test_data = datasets.CIFAR10(
                root=str(DATA_DIR),
                train=False,
                download=True,
                transform=transform
            )

    else:

        if DATASET == "EMNISTLetters":

            transform = transforms.ToTensor()

            # ============================================================
            # ADDED NEW: EMNIST PREPROCESSING FOR CONVOLUTIONAL MODE
            # ============================================================

            # EMNIST Letters contains 28x28 grayscale images.
            # The convolutional frontend expects 32x32 images.
            # Add a 2-pixel zero border on every side.
            # This preserves the original image values without interpolation.
            # Regional mode continues using the original 28x28 images.

            if FEATURE_EXTRACTOR == "conv":
                transform = transforms.Compose([
                    transforms.Pad(2, fill=0),
                    transforms.ToTensor()
                ])

            train_data = datasets.EMNIST(
                root=str(DATA_DIR),
                split="letters",
                train=True,
                download=True,
                transform=transform
            )

            test_data = datasets.EMNIST(
                root=str(DATA_DIR),
                split="letters",
                train=False,
                download=True,
                transform=transform
            )

            # EMNIST Letters labels are 1-26.
            # Convert to 0-25 for our HDC implementation.
            train_data.targets -= 1
            test_data.targets -= 1

            # 26 classes: A-Z
            train_data.classes = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            test_data.classes = train_data.classes

        else:

            # MNIST and FashionMNIST use the same dataset-loading method.
            if DATASET == "MNIST":
                dataset_class = datasets.MNIST
            elif DATASET == "FashionMNIST":
                dataset_class = datasets.FashionMNIST
            else:
                raise ValueError(f"Unknown dataset: {DATASET}")

            transform = transforms.ToTensor()

            # ============================================================
            # ADDED NEW: MNIST/FASHIONMNIST PREPROCESSING FOR CONV MODE
            # ============================================================

            # Both datasets contain 28x28 grayscale images.
            # Add a 2-pixel zero border to obtain a 32x32 input.
            # The original regional pipeline keeps its 28x28 input.

            if FEATURE_EXTRACTOR == "conv":
                transform = transforms.Compose([
                    transforms.Pad(2, fill=0),
                    transforms.ToTensor()
                ])

            train_data = dataset_class(
                root=str(DATA_DIR),
                train=True,
                download=True,
                transform=transform
            )

            test_data = dataset_class(
                root=str(DATA_DIR),
                train=False,
                download=True,
                transform=transform
            )

    # # Reserve 6,000 training images for model selection, never for updates.
    # # The official 10,000 test images are used only AFTER selection.
    # train_subset, val_subset = random_split(
    #     train_data,
    #     [len(train_data) - VALIDATION_SAMPLES, VALIDATION_SAMPLES],
    #     generator=torch.Generator().manual_seed(SEED)
    # )

    # Stratified split: approximately 10% of each class for validation
    targets = torch.as_tensor(train_data.targets)

    train_indices = []
    val_indices = []

    # Fixed random generator for reproducibility
    generator = torch.Generator().manual_seed(SEED)

    for class_id in range(len(train_data.classes)):

        # Find all images belonging to this class
        indices = torch.where(targets == class_id)[0]

        # Randomly shuffle images within this class
        indices = indices[torch.randperm(len(indices), generator=generator)]

        # Select approximately 10% of this class for validation
        n_val = round(len(indices) * VALIDATION_SAMPLES / len(train_data))

        # Ensure exactly VALIDATION_SAMPLES images overall
        if class_id == len(train_data.classes) - 1:
            n_val = VALIDATION_SAMPLES - len(val_indices)

        # Split class samples into validation and training
        val_indices.extend(indices[:n_val].tolist())
        train_indices.extend(indices[n_val:].tolist())

    # Create training and validation subsets
    train_subset = Subset(train_data, train_indices)
    val_subset = Subset(train_data, val_indices)

    train_loader = DataLoader(train_subset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_subset, batch_size=BATCH_SIZE, shuffle=False)
    test_loader = DataLoader(test_data, batch_size=BATCH_SIZE, shuffle=False)

    print(f"Dataset: {DATASET}")
    print(f"Training samples: {len(train_subset)}")
    print(f"Validation samples: {len(val_subset)}")
    print(f"Test samples: {len(test_data)}")

    return train_loader, val_loader, test_loader, train_data.classes

# ============================================================
# 4. REGIONAL FEATURE EXTRACTION
# ============================================================

def extract_features(images):

    # Step 1: Calculate average intensity of each region
    # Input:  [batch, 1, 28, 28]
    # Output: [batch, 1, 14, 14] for REGION_SIZE = 2
    regional_avg = F.avg_pool2d(
        images,
        kernel_size=REGION_SIZE,
        stride=REGION_SIZE
    )

    # Step 2: Quantize each regional average using configured thresholds.
    # For [0.10, 0.35, 0.70], levels are 0, 1, 2, or 3.
    thresholds = regional_avg.new_tensor(LEVEL_THRESHOLDS)
    levels = torch.bucketize(regional_avg, thresholds, right=True)

    # Step 3: Flatten regions into a feature vector
    # Output: [batch, 196]
    features = levels.flatten(start_dim=1)

    return features

# ============================================================
# 5. FEATURE AND LEVEL HYPERVECTOR GENERATION
# ============================================================

def generate_feature_hvs():

    if FEATURE_HV_MODE == "random":
        # Generate random binary HVs (approximately orthogonal)
        feature_hvs = torch.randint(
            0, 2, (NUM_FEATURES, HDC_DIM), device=DEVICE
        ).bool()

    elif FEATURE_HV_MODE == "hadamard":
        # Hadamard requires a power-of-two dimension
        assert HDC_DIM & (HDC_DIM - 1) == 0
        assert NUM_FEATURES < HDC_DIM

        # Generate exactly orthogonal binary HVs
        # Skip row 0 because it contains only zeros
        # rows = torch.arange(1, NUM_FEATURES + 1, device=DEVICE)[:, None]

        # # Select random, distinct Hadamard rows
        # # Preserve exact pairwise orthogonality while reducing repetitive patterns
        # row_ids = torch.randperm(HDC_DIM - 1, device=DEVICE)[:NUM_FEATURES] + 1
        # rows = row_ids[:, None]
        
        # Keep the original RNG consumption for a fair comparison
        # with the previous random-row experiment.
        _ = torch.randperm(HDC_DIM - 1, device=DEVICE)

        # Deterministic Hadamard row selection
        HADAMARD_STRIDE = 1597

        row_ids = (
            HADAMARD_STRIDE
            * torch.arange(1, NUM_FEATURES + 1, device=DEVICE)
        ) % HDC_DIM

        rows = row_ids[:, None]
        cols = torch.arange(HDC_DIM, device=DEVICE)[None, :]

        # Hadamard entries are the parity of bitwise AND
        bits = rows & cols
        feature_hvs = torch.zeros(
            (NUM_FEATURES, HDC_DIM), dtype=torch.bool, device=DEVICE
        )

        for bit in range(HDC_DIM.bit_length() - 1):
            feature_hvs ^= ((bits >> bit) & 1).bool()

    else:
        raise ValueError(f"Unknown FEATURE_HV_MODE: {FEATURE_HV_MODE}")

    return feature_hvs


def generate_level_hvs():

    if LEVEL_MODE == "random":
        # Independent random HVs (approximately orthogonal)
        level_hvs = torch.randint(
            0, 2, (NUM_LEVELS, HDC_DIM), device=DEVICE
        ).bool()

    elif LEVEL_MODE == "correlated":
        # Generate the first level randomly
        level_hvs = torch.zeros(
            (NUM_LEVELS, HDC_DIM), dtype=torch.bool, device=DEVICE
        )

        level_hvs[0] = torch.randint(
            0, 2, (HDC_DIM,), device=DEVICE
        ).bool()

        # # Flip different bits between consecutive levels
        # # L0 and the last level differ in approximately D/2 bits
        # total_flips = HDC_DIM // 2

        # Number of bits changed between the first and last level HV
        total_flips = int(HDC_DIM * LEVEL_CORRELATION_RANGE)
        assert NUM_LEVELS - 1 <= total_flips

        positions = torch.randperm(HDC_DIM, device=DEVICE)[:total_flips]

        for level in range(1, NUM_LEVELS):

            # Copy the previous level
            level_hvs[level] = level_hvs[level - 1]

            # Select a different set of bits for this transition
            start = (level - 1) * total_flips // (NUM_LEVELS - 1)
            end = level * total_flips // (NUM_LEVELS - 1)

            # Flip selected bits
            idx = positions[start:end]
            level_hvs[level, idx] = ~level_hvs[level, idx]

    else:
        raise ValueError(f"Unknown LEVEL_MODE: {LEVEL_MODE}")

    return level_hvs

# ============================================================
# 6. HDC IMAGE ENCODING
# ============================================================

def generate_tie_breaker_hv():
    # Random binary HV used when majority voting results in a tie
    # Generate once and reuse for all images
    return torch.randint(
        0, 2, (HDC_DIM,), device=DEVICE
    ).bool()


def encode_hdc(features, feature_hvs, level_hvs, tie_breaker_hv):

    # Move features to the same device as the hypervectors
    features = features.to(DEVICE)

    # Step 1: Select the level HV for each feature
    # Shape: [batch, 196, 2048]
    selected_levels = level_hvs[features]

    # Step 2: Bind feature HVs with selected level HVs using XOR
    # Shape: [batch, 196, 2048]
    bound_hvs = feature_hvs.unsqueeze(0) ^ selected_levels

    # Step 3: Count the number of 1s in each HV dimension
    # Shape: [batch, 2048]
    counts = bound_hvs.sum(dim=1)

    # # Step 4: Majority voting
    # # Output is 1 when more than half of the features vote 1
    # image_hvs = counts * 2 > NUM_FEATURES

    # # Resolve ties using the fixed random tie-breaker HV
    # ties = counts * 2 == NUM_FEATURES
    # image_hvs = torch.where(ties, tie_breaker_hv, image_hvs)
    # Step 4: Threshold-based bundling
    # Output 1 if popcount >= 96, otherwise 0
    image_hvs = counts >= QUERY_POPCOUNT_THRESHOLD #it was >= before

    return image_hvs

# ============================================================
# 7. TRAIN CLASS HYPERVECTORS
# ============================================================

def train_hdc(train_loader, feature_hvs, level_hvs, tie_breaker_hv):

    # A random_split Subset holds the original dataset under .dataset
    num_classes = len(train_loader.dataset.dataset.classes)  # 10 classes

    # Initialize counters for the number of 1s in each class
    class_counts = torch.zeros(
        (num_classes, HDC_DIM), dtype=torch.int32, device=DEVICE
    )

    # Count the number of training images in each class
    class_samples = torch.zeros(
        num_classes, dtype=torch.int32, device=DEVICE
    )

    # Process all training images in batches
    for images, labels in train_loader:

        images = images.to(DEVICE)
        labels = labels.to(DEVICE)

        # Extract regional intensity features
        features = extract_features(images)

        # Encode images into binary hypervectors
        image_hvs = encode_hdc(
            features, feature_hvs, level_hvs, tie_breaker_hv
        )

        # Add binary HVs to their corresponding class counters
        class_counts.index_add_(0, labels, image_hvs.int())

        # Count the number of images belonging to each class
        class_samples += torch.bincount(
            labels, minlength=num_classes
        ).int()

    # Majority voting: 1 if more than half the samples vote 1
    class_hvs = class_counts * 2 > class_samples[:, None]

    # Resolve ties using the fixed tie-breaker HV
    ties = class_counts * 2 == class_samples[:, None]
    class_hvs = torch.where(ties, tie_breaker_hv, class_hvs)

    return class_hvs, class_counts, class_samples

# ============================================================
# 8. HDC CLASSIFICATION AND EVALUATION
# ============================================================

@torch.no_grad()
def evaluate_hdc(test_loader, feature_hvs, level_hvs, tie_breaker_hv, class_hvs):

    num_classes = class_hvs.shape[0]

    # Counters for overall and per-class accuracy
    total = 0
    correct = 0

    class_total = torch.zeros(num_classes, device=DEVICE)
    class_correct = torch.zeros(num_classes, device=DEVICE)

    # Confusion matrix: rows = actual, columns = predicted
    confusion_matrix = torch.zeros(
        (num_classes, num_classes), dtype=torch.long, device=DEVICE
    )

    # Process test images in batches
    for images, labels in test_loader:

        images = images.to(DEVICE)
        labels = labels.to(DEVICE)

        # Step 1: Extract regional intensity features
        features = extract_features(images)

        # Step 2: Encode images into binary HVs
        image_hvs = encode_hdc(
            features, feature_hvs, level_hvs, tie_breaker_hv
        )

        # Step 3: Calculate Hamming distances using XOR + popcount
        # Output shape: [batch, num_classes]
        distances = (
            image_hvs[:, None, :] ^ class_hvs[None, :, :]
        ).sum(dim=2)

        # Step 4: Select the class with minimum Hamming distance
        predictions = distances.argmin(dim=1)

        # Step 5: Update overall accuracy counters
        matches = predictions == labels
        correct += matches.sum().item()
        total += labels.size(0)

        # Step 6: Update per-class accuracy counters
        class_total += torch.bincount(labels, minlength=num_classes)
        class_correct += torch.bincount(
            labels[matches], minlength=num_classes
        )

        # Count actual vs. predicted class combinations
        confusion_matrix += torch.bincount(
            labels * num_classes + predictions,
            minlength=num_classes * num_classes
        ).reshape(num_classes, num_classes)

    # Calculate overall accuracy (%)
    accuracy = 100.0 * correct / total

    # Calculate accuracy for each class (%)
    per_class_accuracy = (
        100.0 * class_correct / class_total.clamp(min=1)
    ).cpu().tolist()

    return accuracy, per_class_accuracy, confusion_matrix

# ============================================================
# 10. EXPERIMENT DIAGNOSTICS
# ============================================================

@torch.no_grad()
def analyze_feature_distribution(train_loader, output_dir):

    # Count how many times each intensity level appears
    level_counts = torch.zeros(
        NUM_LEVELS, dtype=torch.long, device=DEVICE
    )

    for images, labels in train_loader:

        images = images.to(DEVICE)

        # Extract regional features (levels 0 to NUM_LEVELS-1)
        features = extract_features(images)

        # Count occurrences of each level
        level_counts += torch.bincount(
            features.flatten(), minlength=NUM_LEVELS
        )

    # Calculate percentage of each level
    total = level_counts.sum().item()
    percentages = 100.0 * level_counts.float() / total

    # Save distribution to CSV
    with open(output_dir / "feature_distribution.csv", "w", newline="") as f:

        writer = csv.writer(f)
        writer.writerow(["Level", "Count", "Percentage"])

        for i in range(NUM_LEVELS):
            writer.writerow([
                i,
                level_counts[i].item(),
                percentages[i].item()
            ])


def save_confusion_matrix(confusion_matrix, class_names, output_dir):

    # Save confusion matrix to CSV
    # Rows = actual classes, Columns = predicted classes
    with open(output_dir / "confusion_matrix.csv", "w", newline="") as f:

        writer = csv.writer(f)

        # Write column labels
        writer.writerow(["Actual / Predicted"] + class_names)

        # Write each row of the confusion matrix
        for i, row in enumerate(confusion_matrix.cpu().tolist()):
            writer.writerow([class_names[i]] + row)

# ============================================================
# 11. ERROR-DRIVEN PROTOTYPE RETRAINING (ENCODER IS FIXED)
# ============================================================

@torch.no_grad()
def retrain_hdc(train_loader, val_loader, feature_hvs, level_hvs,
                tie_breaker_hv, initial_hvs, class_counts, class_samples):
    # Convert single-pass majority counts into small SIGNED integer scores.
    # Scores are training-only. Inference still uses binary class prototypes.
    signed_votes = class_counts * 2 - class_samples[:, None]
    scores = (
        signed_votes.float() / class_samples[:, None].clamp(min=1)
        * RETRAIN_INIT_STRENGTH
    ).round().int()

    # Ensure integer rounding preserves EXACTLY the initial binary prototypes.
    initial_signs = torch.where(initial_hvs, 1, -1).int()
    scores = torch.where(scores == 0, initial_signs, scores)
    prototypes = initial_hvs.clone()

    # Epoch 0 is the original one-pass model: it can win if retraining hurts.
    best_accuracy, _, _ = evaluate_hdc(
        val_loader, feature_hvs, level_hvs, tie_breaker_hv, prototypes
    )
    best_epoch = 0
    best_hvs = prototypes.clone()
    history = [{"epoch": 0, "validation_accuracy_percent": best_accuracy,
                "training_mistakes": None}]
    print(f"Epoch 0 (single-pass): validation accuracy = {best_accuracy:.2f}%")

    for epoch in range(1, RETRAIN_EPOCHS + 1):
        training_mistakes = 0
        for images, labels in train_loader:
            images, labels = images.to(DEVICE), labels.to(DEVICE)
            query_hvs = encode_hdc(
                extract_features(images), feature_hvs, level_hvs,
                tie_breaker_hv
            )

            # # Classify using CURRENT binary prototypes.
            # distances = (query_hvs[:, None, :] ^ prototypes[None, :, :]).sum(2)
            # predicted = distances.argmin(dim=1)
            # wrong = predicted != labels
            # training_mistakes += int(wrong.sum().item())

            # # For mistakes only: reinforce true class and suppress wrong class.
            # # Converting bits to +/-1 occurs OFFLINE for training only.
            # error_votes = query_hvs[wrong].int() * 2 - 1
            # scores.index_add_(0, labels[wrong], error_votes * RETRAIN_STEP)
            # scores.index_add_(0, predicted[wrong], -error_votes * RETRAIN_STEP)

            # Classify using CURRENT binary prototypes.
            distances = (query_hvs[:, None, :] ^ prototypes[None, :, :]).sum(2)
            predicted = distances.argmin(dim=1)

            # Count actual classification mistakes.
            wrong = predicted != labels
            training_mistakes += int(wrong.sum().item())

            # Distance to the true class.
            d_true = distances.gather(1, labels[:, None]).squeeze(1)

            # Find the closest competing class (excluding the true class).
            other_distances = distances.clone()
            other_distances.scatter_(1, labels[:, None], HDC_DIM + 1)

            d_competitor, competitor = other_distances.min(dim=1)

            # Positive margin: true class is closer.
            # Negative margin: a competing class is closer.
            margin = d_competitor - d_true

            # Update wrong predictions AND correctly classified images
            # with insufficient separation.
            needs_update = wrong | (margin < RETRAIN_MARGIN)

            # Convert selected image HVs into bipolar votes.
            update_votes = query_hvs[needs_update].int() * 2 - 1

            # Reinforce the true class.
            scores.index_add_(
                0, labels[needs_update],
                update_votes * RETRAIN_STEP
            )

            # Penalize the closest competing class.
            scores.index_add_(
                0, competitor[needs_update],
                -update_votes * RETRAIN_STEP
            )

            # # Re-binarize after each batch: hardware stores these bits only.
            prototypes = torch.where(scores == 0, tie_breaker_hv, scores > 0)

            # When a score is zero, preserve the previous prototype bit
            # Re-binarize after each batch
            # Positive score -> 1
            # Negative score -> 0
            # Zero score -> keep the previous prototype bit
            # prototypes = torch.where(scores == 0, prototypes, scores > 0)

        val_accuracy, _, _ = evaluate_hdc(
            val_loader, feature_hvs, level_hvs, tie_breaker_hv, prototypes
        )
        history.append({"epoch": epoch,
                        "validation_accuracy_percent": val_accuracy,
                        "training_mistakes": training_mistakes})
        print(f"Epoch {epoch}: validation = {val_accuracy:.2f}% "
              f"| training mistakes = {training_mistakes}")

        if val_accuracy > best_accuracy:  # Strict: retain earlier epoch on ties.
            best_accuracy = val_accuracy
            best_epoch = epoch
            best_hvs = prototypes.clone()

    return best_hvs, best_epoch, best_accuracy, history


# ============================================================
# 12. SAVE BEST MODEL FOR REPRODUCIBLE / HARDWARE INFERENCE
# ============================================================

def save_best_model(output_dir, feature_hvs, level_hvs, tie_breaker_hv,
                    best_class_hvs, class_names, best_epoch,
                    best_val_accuracy):
    hardware_dir = output_dir / "hardware_model"
    hardware_dir.mkdir(exist_ok=True)

    # All of these are the ACTUAL learned/generated bits, not just a random seed.
    tensors = {
        "feature_hvs": feature_hvs.detach().cpu().contiguous().bool(),
        "level_hvs": level_hvs.detach().cpu().contiguous().bool(),
        "class_hvs": best_class_hvs.detach().cpu().contiguous().bool(),
        "tie_breaker_hv": tie_breaker_hv.detach().cpu().contiguous().bool(),
    }

    config = {
        "dataset": DATASET,
        "class_names": list(class_names),
        "image_size": IMAGE_SIZE,
        "region_size": REGION_SIZE,
        "query_popcount_threshold": QUERY_POPCOUNT_THRESHOLD,
        "num_features": NUM_FEATURES,
        "num_levels": NUM_LEVELS,
        "level_thresholds": list(LEVEL_THRESHOLDS),
        "bits_per_feature": BITS_PER_FEATURE,
        "sensor_bits_per_image": SENSOR_BITS_PER_IMAGE,
        "hdc_dim": HDC_DIM,
        "feature_hv_mode": FEATURE_HV_MODE,
        "level_mode": LEVEL_MODE,
        "level_correlation_range": LEVEL_CORRELATION_RANGE,
        "best_epoch": best_epoch,
        "best_validation_accuracy_percent": best_val_accuracy,
        "seed": SEED,
        "encoding": "XOR feature-HV with level-HV, majority bundle",
        "inference": "Minimum Hamming distance to class prototypes",
        "feature_order": "Region indices in row-major order (top-left to bottom-right)",
        "retrain_method": "margin_based",
        "retrain_margin": RETRAIN_MARGIN,
    }

    # Convenient PyTorch checkpoint for reloading the complete trained model.
    torch.save({**tensors, "config": config}, output_dir / "best_model.pt")

    # Hardware-friendly raw bitstreams: each row is packed LOWEST bit first.
    # A D=2048 HV occupies exactly 256 bytes in a .bin file.
    binary_files = {}
    for name, tensor in tensors.items():
        array = tensor.numpy().astype(np.uint8)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        packed = np.packbits(array, axis=1, bitorder="little")
        path = hardware_dir / f"{name}.bin"
        packed.tofile(path)
        binary_files[name] = {
            "file": path.name,
            "rows": int(array.shape[0]),
            "bits_per_row": int(array.shape[1]),
            "bytes_per_row": int(packed.shape[1]),
        }

    # For Hadamard feature HVs, the row IDs enable a compact hardware
    # generator: F[region, bit] = parity(row_id[region] & bit_index).
    # This avoids storing the full 196x2048-bit feature-HV table on chip.
    if FEATURE_HV_MODE == "hadamard":
        n_bits = HDC_DIM.bit_length() - 1
        power_of_two_cols = [1 << k for k in range(n_bits)]
        row_bits = tensors["feature_hvs"].numpy()[:, power_of_two_cols]
        row_ids = (row_bits.astype(np.uint64)
                   * (1 << np.arange(n_bits, dtype=np.uint64))).sum(axis=1)
        row_dtype = "<u2" if HDC_DIM <= 65536 else "<u4"
        row_ids.astype(row_dtype).tofile(hardware_dir / "hadamard_row_ids.bin")
        config["hadamard_row_ids"] = {
            "file": "hadamard_row_ids.bin",
            "count": NUM_FEATURES,
            "dtype": "uint16 little-endian" if HDC_DIM <= 65536
                     else "uint32 little-endian",
            "formula": "parity(row_id[region] & bit_index)",
        }

    config["binary_export"] = {
        "bit_order": "little (dimension 0 is bit 0 of first byte)",
        "row_order": "row-major, no row headers or padding except last byte",
        "files": binary_files,
    }
    with open(hardware_dir / "manifest.json", "w") as f:
        json.dump(config, f, indent=4)

    # Model values are in best_model.pt; manifest describes raw exports.
    print(f"Best model saved: {output_dir / 'best_model.pt'}")
    print(f"Binary hardware export: {hardware_dir}")

# ============================================================
# ADDED NEW: APP-CiP-STYLE CONVOLUTION + HDC JOINT TRAINING
# ============================================================
# All original Hadamard/level HV functions and encode_hdc() ABOVE remain
# unchanged. The code below is an additional path, not a replacement for them.
#
# IMPORTANT HARDWARE SCOPE:
# - This is a PyTorch functional model of a PROPOSED modified AppCiP frontend.
# - Original AppCiP does NOT implement 8-bit weights, pooling, or these learned
#   2-bit output thresholds. All require circuit/control evaluation.
# - The convolution arithmetic below simulates signed INT8 weights, dequantized
#   by a per-output-channel scale; it is NOT a transistor-/ADC-level simulation.
# - We do NOT model sensor noise, analog MAC nonidealities, ADC energy, or pooling
#   circuits here. 392 bits/image refers only to the FINAL quantized features.


def inverse_softplus(x):
    # ADDED NEW: Stable inverse of softplus for strictly positive initial gaps.
    # softplus(inverse_softplus(x)) == x for positive x (up to precision).
    return x + torch.log(-torch.expm1(-x))

# ============================================================
# REGIONAL JOINT TRAINING — LEARNABLE THRESHOLDS
# ============================================================

class RegionalJointFeatureExtractor(nn.Module):

    def __init__(self):
        super().__init__()

        # Initialize with the original regional thresholds.
        t1, t2, t3 = LEVEL_THRESHOLDS

        # Parameterization guarantees:
        # 0 < t1 < t2 < t3 < 1
        fractions = torch.tensor([
            t1,
            (t2 - t1) / (1.0 - t1),
            (t3 - t2) / (1.0 - t2)
        ], dtype=torch.float32)

        # Three trainable parameters.
        self.threshold_raw = nn.Parameter(torch.logit(fractions))

        self.channels = 1

    def thresholds(self):

        # Convert trainable parameters to ordered thresholds.
        f = torch.sigmoid(self.threshold_raw)

        t1 = f[0]
        t2 = t1 + (1.0 - t1) * f[1]
        t3 = t2 + (1.0 - t2) * f[2]

        return torch.stack((t1, t2, t3)).unsqueeze(0)  # [1, 3]

    def pooled_values(self, images):

        # Original regional feature extraction.
        # [B, 1, 28, 28] -> [B, 1, 14, 14]

        return F.avg_pool2d(
            images,
            kernel_size=REGION_SIZE,
            stride=REGION_SIZE
        )

    def hard_features(self, pooled):

        # Exact hard quantization for forward/inference.
        # Output: [B, 196], values 0, 1, 2, 3.

        th = self.thresholds()[None, :, None, None, :]

        levels = (pooled.unsqueeze(-1) >= th).sum(dim=-1)

        return levels.flatten(start_dim=1).long()

    def soft_level_probabilities(self, pooled):

        # Differentiable approximation for backward gradients.
        # The hard features are still used in the forward pass.

        th = self.thresholds()[None, :, None, None, :]

        cumulative = torch.sigmoid(
            (pooled.unsqueeze(-1) - th)
            / FEATURE_SOFT_TEMPERATURE
        )

        a, b, c = cumulative.unbind(dim=-1)

        probs = torch.stack(
            (1.0 - a, a - b, b - c, c),
            dim=-1
        )

        return probs.reshape(
            pooled.shape[0],
            NUM_FEATURES,
            NUM_LEVELS
        )
    
class AppCiPConvFeatureExtractor(nn.Module):
    # ADDED NEW: One trainable 3x3 convolution and fixed spatial pooling.
    # Input:  [B, 1, 32, 32] (already grayscale).
    # Conv:   [B, C, 30, 30] with C = 1 or 4.
    # Crop:   [B, C, 28, 28] by selecting rows/cols 1..28.
    # Pool:   [B, 1, 14, 14] for C=1, OR [B, 4, 7, 7] for C=4.
    # Output: always 196 pooled real values -> 196 discrete levels in {0,1,2,3}.
    def __init__(self, channels):
        super().__init__()
        if channels not in (1, 4):
            raise ValueError("Exactly 196 features require 1 or 4 channels here")

        self.channels = channels
        self.pool_size = 2 if channels == 1 else 4
        self.conv = nn.Conv2d(
            in_channels=1,
            out_channels=channels,
            kernel_size=CONV_KERNEL_SIZE,
            stride=1,
            padding=0,
            bias=False  # No additional analog bias is assumed in modified AppCiP.
        )

        # ADDED NEW: Train one ordered set of 3 thresholds per output channel.
        # Using positive softplus gaps guarantees t1 < t2 < t3 during training.
        # Quartile-based initialization is performed AFTER loading train data.
        self.threshold_start = nn.Parameter(torch.zeros(channels))
        self.threshold_raw_gaps = nn.Parameter(torch.zeros(channels, 2))

    def quantized_weights(self):
        # ADDED NEW: Per-output-channel symmetric signed INT8 fake quantization.
        # Integer range [-128,127] has 256 representable values, although a
        # particular trained filter may use far fewer than 256 distinct codes.
        # Each channel has one scale. This preserves zero without a zero-point.
        w = self.conv.weight
        axes = (1, 2, 3)
        positive = w.detach().amax(dim=axes, keepdim=True).clamp(min=0) / 127.0
        negative = (-w.detach().amin(dim=axes, keepdim=True)).clamp(min=0) / 128.0
        scales = torch.maximum(positive, negative).clamp(min=1e-8)
        w_integer = torch.round(w / scales).clamp(-128, 127)

        # Forward value equals dequantized INT8; backward derivative w.r.t.
        # latent float weights is 1 (straight-through estimator, STE).
        w_fake = w + (w_integer * scales - w).detach()
        return w_fake, w_integer.to(torch.int8), scales

    def thresholds(self):
        # ADDED NEW: Three ordered real-valued thresholds, independent for each
        # convolution output channel. They are not the fixed pixel-intensity
        # LEVEL_THRESHOLDS of the original regional path.
        gaps = F.softplus(self.threshold_raw_gaps) + 1e-5
        t1 = self.threshold_start
        t2 = t1 + gaps[:, 0]
        t3 = t2 + gaps[:, 1]
        return torch.stack((t1, t2, t3), dim=1)  # [C, 3]

    def pooled_values(self, images):
        # ADDED NEW: Simulate convolution with deployed quantized weights.
        if images.ndim != 4 or tuple(images.shape[1:]) != (1, 32, 32):
            raise ValueError(f"Expected [B,1,32,32], received {tuple(images.shape)}")
        w_fake, _, _ = self.quantized_weights()
        conv_output = F.conv2d(images, w_fake, stride=1, padding=0)
        center_28 = conv_output[:, :, 1:29, 1:29]
        pooled = F.avg_pool2d(center_28, kernel_size=self.pool_size,
                              stride=self.pool_size)
        assert pooled.shape[1] * pooled.shape[2] * pooled.shape[3] == NUM_FEATURES
        return pooled

    def hard_features(self, pooled):
        # ADDED NEW: EXACT discrete 4-level quantization for inference and for
        # the hard forward branch during joint training. Equality goes to the
        # higher level, matching torch.bucketize(..., right=True).
        # Shape: [B,C,H,W] -> [B,196] of int64 levels 0..3.
        th = self.thresholds()[None, :, None, None, :]
        levels = (pooled.unsqueeze(-1) >= th).sum(dim=-1)
        return levels.flatten(start_dim=1).long()

    def soft_level_probabilities(self, pooled):
        # ADDED NEW: Differentiable BACKWARD surrogate for selecting one of
        # four fixed level HVs. The hard feature level is still used in the
        # ACTUAL forward inference computation via encode_hdc().
        # Ordered thresholds give nonnegative probabilities summing to one.
        th = self.thresholds()[None, :, None, None, :]
        cumulative = torch.sigmoid(
            (pooled.unsqueeze(-1) - th) / FEATURE_SOFT_TEMPERATURE
        )
        a, b, c = cumulative.unbind(dim=-1)
        probs = torch.stack((1.0 - a, a - b, b - c, c), dim=-1)
        return probs.reshape(pooled.shape[0], NUM_FEATURES, NUM_LEVELS)

    @torch.no_grad()
    def initialize_thresholds_from_train(self, train_loader):
        # ADDED NEW: Initialize each channel's thresholds to the train-only
        # 25th, 50th, 75th percentiles of initial pooled convolution values.
        # Validation and test samples MUST NOT be used for initialization.
        samples = []
        for batch_idx, (images, _labels) in enumerate(train_loader):
            if batch_idx >= THRESHOLD_INIT_BATCHES:
                break
            pooled = self.pooled_values(images.to(DEVICE))
            samples.append(pooled.permute(1, 0, 2, 3).reshape(self.channels, -1).cpu())
        if not samples:
            raise ValueError("Cannot initialize thresholds from an empty train set")
        # ADDED NEW: Initialize thresholds using non-zero convolution responses.
        # This avoids degenerate quartiles caused by large zero-valued backgrounds.
        # Zero-valued features are still included during training and inference.

        values = torch.cat(samples, dim=1)

        qs = torch.tensor([0.25, 0.50, 0.75])

        quartiles = torch.stack([
            torch.quantile(v[v != 0], qs)
            for v in values
        ]).to(device=DEVICE)  # [C, 3]
        self.threshold_start.copy_(quartiles[:, 0])
        positive_gaps = (quartiles[:, 1:] - quartiles[:, :-1] - 1e-5).clamp(min=1e-4)
        self.threshold_raw_gaps.copy_(inverse_softplus(positive_gaps))
        return self.thresholds().detach().cpu().tolist()

# ============================================================
# ADDED NEW: EXACT-HARD-FORWARD, SURROGATE-BACKWARD HDC ENCODER
# ============================================================


def encode_hdc_joint_train(pooled, frontend, feature_hvs, level_hvs,
                           tie_breaker_hv, bound_lookup):

    # ADDED NEW: The forward query bits are computed with the UNCHANGED
    # encode_hdc() function. Surrogate values only supply gradients during
    # backpropagation. Inference does not use the soft computation below.
    hard_levels = frontend.hard_features(pooled)

    hard_query = encode_hdc(
        hard_levels, feature_hvs, level_hvs, tie_breaker_hv
    ).float()

    # ADDED NEW: Soft probabilities replace integer level indexing ONLY in the
    # backward path. Bound LUT encodes all 196*4 combinations with the SAME
    # fixed feature/level HVs and the SAME XOR bit convention.
    probs = frontend.soft_level_probabilities(pooled)  # [B,196,4]

    # einsum avoids storing an enormous [B,196,D] float bound-HV tensor.
    # [B,196,4] x [196,4,4096] -> [B,4096]
    soft_counts = torch.einsum("bnl,nld->bd", probs, bound_lookup)

    # ADDED NEW: Relax the fixed integer popcount decision for gradients.
    # At inference, the exact comparison is still counts >= QUERY_POPCOUNT_THRESHOLD.
    # Subtract 0.5 to center this surrogate between adjacent integer counts.
    soft_query = torch.sigmoid(
        (soft_counts - (QUERY_POPCOUNT_THRESHOLD - 0.5))
        / BUNDLE_SOFT_TEMPERATURE
    )

    # ADDED NEW: Straight-through combination: numerically equal to hard_query
    # in the forward pass; backpropagation uses derivatives of soft_query.
    return hard_query + (soft_query - soft_query.detach())

def binarize_trainable_prototypes(prototype_scores):
    # ADDED NEW: Continuous trainable scores, binary 0/1 forward prototypes.
    # At inference a score >= 0 maps to bit 1, otherwise bit 0.
    hard = (prototype_scores >= 0).float()
    soft = torch.sigmoid(prototype_scores / PROTOTYPE_SOFT_TEMPERATURE)
    return hard + (soft - soft.detach())  # STE, binary forward

@torch.no_grad()
def initialize_conv_class_prototypes(train_loader, frontend, feature_hvs,
                                     level_hvs, tie_breaker_hv, num_classes):
    # ADDED NEW: Use original class-majority initialization logic, but obtain
    # features from the new convolution frontend (not regional averaging).
    # This initializes prototypes; all are subsequently trained jointly.
    frontend.eval()
    class_counts = torch.zeros(
        (num_classes, HDC_DIM), dtype=torch.int32, device=DEVICE
    )
    class_samples = torch.zeros(num_classes, dtype=torch.int32, device=DEVICE)

    for images, labels in train_loader:
        images, labels = images.to(DEVICE), labels.to(DEVICE)

        pooled = frontend.pooled_values(images)
        features = frontend.hard_features(pooled)

        query_hvs = encode_hdc(
            features, feature_hvs, level_hvs, tie_breaker_hv
        )

        class_counts.index_add_(0, labels, query_hvs.int())
        class_samples += torch.bincount(
            labels, minlength=num_classes
        ).int()

    prototypes = class_counts * 2 > class_samples[:, None]

    ties = class_counts * 2 == class_samples[:, None]
    prototypes = torch.where(ties, tie_breaker_hv, prototypes)

    return prototypes

@torch.no_grad()
def evaluate_conv_hdc(loader, frontend, class_hvs, feature_hvs,
                      level_hvs, tie_breaker_hv):
    # ADDED NEW: Use only real deployable operations for validation and test:
    # INT8-dequantized convolution, cropping, pooling, HARD four-level encoding,
    # UNCHANGED XOR/bundling, and minimum binary Hamming distance.

    # new comment
    # Shared HDC evaluation for conv and regional_joint.
    #
    # For conv: quantized convolution, cropping, and pooling.
    # For regional_joint: ONLY 2x2 average pooling (NO convolution).
    #
    # Both use hard 4-level quantization, binary XOR/bundling,
    # and minimum Hamming-distance classification.
    frontend.eval()
    num_classes = class_hvs.shape[0]
    total, correct = 0, 0
    class_total = torch.zeros(num_classes, device=DEVICE)
    class_correct = torch.zeros(num_classes, device=DEVICE)
    confusion_matrix = torch.zeros(
        (num_classes, num_classes), dtype=torch.long, device=DEVICE
    )

    for images, labels in loader:
        images, labels = images.to(DEVICE), labels.to(DEVICE)
        features = frontend.hard_features(frontend.pooled_values(images))
        query_hvs = encode_hdc(features, feature_hvs, level_hvs, tie_breaker_hv)
        distances = (query_hvs[:, None, :] ^ class_hvs[None, :, :]).sum(dim=2)
        predictions = distances.argmin(dim=1)
        matches = predictions == labels
        total += labels.numel()
        correct += matches.sum().item()
        class_total += torch.bincount(labels, minlength=num_classes)
        class_correct += torch.bincount(labels[matches], minlength=num_classes)
        confusion_matrix += torch.bincount(
            labels * num_classes + predictions,
            minlength=num_classes * num_classes
        ).reshape(num_classes, num_classes)

    accuracy = 100.0 * correct / total
    per_class = (100.0 * class_correct / class_total.clamp(min=1)).cpu().tolist()
    return accuracy, per_class, confusion_matrix

# ============================================================
# ADDED NEW: EVALUATE QUANTIZED THRESHOLD PRECISION
# ============================================================

# ============================================================
# EVALUATE LEARNED THRESHOLDS AT DIFFERENT BIT PRECISIONS
# ============================================================

@torch.no_grad()
def evaluate_threshold_precision(
    train_loader, val_loader, frontend,
    class_hvs, feature_hvs, level_hvs, tie_breaker_hv,
    test_loader=None, output_dir=None
):
    # Shared by both convolutional and regional_joint methods.
    #
    # IMPORTANT:
    # For regional_joint, NO convolution is performed.
    # The frontend uses 2x2 average pooling and learned thresholds.
    #
    # Calibration uses TRAINING data only.
    # The best model has already been selected using validation accuracy.
    # Threshold precision evaluation is for reporting only.
    # No model selection or parameter updates are performed here.
    # Test results are reported for hardware sensitivity analysis.

    frontend.eval()

    thresholds = frontend.thresholds().detach()
    channels = frontend.channels

    # --------------------------------------------------------
    # 1. Determine calibration range using training data only
    # --------------------------------------------------------

    vmin = torch.full(
        (channels,), float("inf"), device=DEVICE
    )
    vmax = torch.full(
        (channels,), float("-inf"), device=DEVICE
    )

    for images, _ in train_loader:

        images = images.to(DEVICE)
        pooled = frontend.pooled_values(images)

        vmin = torch.minimum(
            vmin, pooled.amin(dim=(0, 2, 3))
        )
        vmax = torch.maximum(
            vmax, pooled.amax(dim=(0, 2, 3))
        )

    # Include the learned thresholds in the calibration range.
    vmin = torch.minimum(vmin, thresholds[:, 0])
    vmax = torch.maximum(vmax, thresholds[:, -1])

    span = (vmax - vmin).clamp(min=1e-6)

    # --------------------------------------------------------
    # 2. Helper: evaluate quantized thresholds
    # --------------------------------------------------------

    def evaluate_quantized(loader, quantized_thresholds):

        correct = 0
        total = 0

        for images, labels in loader:

            images = images.to(DEVICE)
            labels = labels.to(DEVICE)

            pooled = frontend.pooled_values(images)

            # Apply the quantized thresholds.
            th = quantized_thresholds[None, :, None, None, :]

            features = (
                pooled.unsqueeze(-1) >= th
            ).sum(dim=-1).flatten(start_dim=1).long()

            # Original binary HDC encoding.
            query_hvs = encode_hdc(
                features, feature_hvs,
                level_hvs, tie_breaker_hv
            )

            # Minimum binary Hamming-distance classification.
            distances = (
                query_hvs[:, None, :] ^ class_hvs[None, :, :]
            ).sum(dim=2)

            predictions = distances.argmin(dim=1)

            correct += (predictions == labels).sum().item()
            total += labels.numel()

        return 100.0 * correct / total

    # --------------------------------------------------------
    # 3. Evaluate original FP32 thresholds
    # --------------------------------------------------------

    # Reuse evaluate_conv_hdc for both methods.
    # IMPORTANT: For regional_joint, NO convolution is performed.
    # The frontend determines the actual feature extraction.

    original_val_acc, _, _ = evaluate_conv_hdc(
        val_loader, frontend, class_hvs,
        feature_hvs, level_hvs, tie_breaker_hv
    )

    original_test_acc = None

    if test_loader is not None:

        original_test_acc, _, _ = evaluate_conv_hdc(
            test_loader, frontend, class_hvs,
            feature_hvs, level_hvs, tie_breaker_hv
        )

    results = []

    results.append({
        "precision_bits": "FP32",
        "validation_accuracy_percent": original_val_acc,
        "test_accuracy_percent": original_test_acc,
        "validation_delta_pp": 0.0,
        "test_delta_pp": 0.0 if test_loader is not None else None,
        "threshold_values": json.dumps(thresholds.cpu().tolist())
    })

    print("\n========== THRESHOLD PRECISION EVALUATION ==========")

    if test_loader is not None:
        print(
            f"FP32: validation = {original_val_acc:.2f}% | "
            f"test = {original_test_acc:.2f}%"
        )
    else:
        print(f"FP32: validation = {original_val_acc:.2f}%")

    # --------------------------------------------------------
    # 4. Evaluate quantized thresholds
    # --------------------------------------------------------

    for bits in [6, 8, 10, 12]:

        max_code = (1 << bits) - 1

        # Quantize using the training-data calibration range.
        codes = torch.round(
            (thresholds - vmin[:, None])
            / span[:, None] * max_code
        ).clamp(0, max_code)

        # Reconstruct the hardware-representable thresholds.
        quantized_thresholds = (
            vmin[:, None]
            + codes * span[:, None] / max_code
        )

        val_acc = evaluate_quantized(
            val_loader, quantized_thresholds
        )

        test_acc = None

        if test_loader is not None:
            test_acc = evaluate_quantized(
                test_loader, quantized_thresholds
            )

        val_delta = val_acc - original_val_acc

        test_delta = (
            test_acc - original_test_acc
            if test_acc is not None else None
        )

        results.append({
            "precision_bits": bits,
            "validation_accuracy_percent": val_acc,
            "test_accuracy_percent": test_acc,
            "validation_delta_pp": val_delta,
            "test_delta_pp": test_delta,
            "threshold_values": json.dumps(
                quantized_thresholds.cpu().tolist()
            )
        })

        if test_acc is not None:
            print(
                f"{bits}-bit: validation = {val_acc:.2f}% "
                f"({val_delta:+.2f} pp) | "
                f"test = {test_acc:.2f}% "
                f"({test_delta:+.2f} pp)"
            )
        else:
            print(
                f"{bits}-bit: validation = {val_acc:.2f}% "
                f"({val_delta:+.2f} pp)"
            )

    # --------------------------------------------------------
    # 5. Save results to CSV
    # --------------------------------------------------------

    if output_dir is not None:

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        csv_path = output_dir / "threshold_precision.csv"

        with open(csv_path, "w", newline="") as f:

            writer = csv.DictWriter(
                f, fieldnames=list(results[0].keys())
            )

            writer.writeheader()
            writer.writerows(results)

        print(f"\nThreshold precision results saved to: {csv_path}")

    return results

@torch.no_grad()
def analyze_conv_feature_distribution(loader, frontend, output_dir):
    # ADDED NEW: Inspect feature-level usage AFTER learning the convolution and
    # thresholds. Output format matches the original feature_distribution.csv.
    frontend.eval()
    level_counts = torch.zeros(NUM_LEVELS, dtype=torch.long, device=DEVICE)

    for images, _labels in loader:
        images = images.to(DEVICE)
        features = frontend.hard_features(frontend.pooled_values(images))
        level_counts += torch.bincount(features.flatten(), minlength=NUM_LEVELS)

    total = level_counts.sum().item()

    with open(output_dir / "feature_distribution.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Level", "Count", "Percentage"])

        for i in range(NUM_LEVELS):
            writer.writerow([
                i,
                level_counts[i].item(),
                100.0 * level_counts[i].item() / total
            ])

def train_joint_conv_hdc(train_loader, val_loader, frontend, feature_hvs,
                         level_hvs, tie_breaker_hv, initial_class_hvs):
    # ADDED NEW: JOINTLY optimize 3 parameter groups with the HDC loss only:
    #    (1) latent weights -> fake-quantized signed INT8 during each forward,
    #    (2) ordered analog output thresholds (3 per convolution channel),
    #    (3) continuous prototype scores -> binary prototype bits per forward.
    # Fixed Hadamard feature HVs and correlated level HVs NEVER get gradients.
    num_classes = initial_class_hvs.shape[0]
    prototype_scores = nn.Parameter(
        initial_class_hvs.float().mul(2.0).sub(1.0).to(DEVICE)
    )

    optimizer = torch.optim.Adam([
        {"params": [frontend.conv.weight], "lr": JOINT_CONV_LR},
        {"params": [frontend.threshold_start, frontend.threshold_raw_gaps],
         "lr": JOINT_THRESHOLD_LR},
        {"params": [prototype_scores], "lr": JOINT_PROTOTYPE_LR},
    ])

    # ADDED NEW: Precompute all fixed possible XOR-bound HVs only once.
    # This is a training-only lookup. The exact encoder above is still used
    # in the hard forward pass and all validation/test evaluations.
    bound_lookup = (
        feature_hvs[:, None, :] ^ level_hvs[None, :, :]
    ).float().contiguous()  # [196,4,4096] (immutable)

    # ADDED NEW: Select the best CHECKPOINT by hard, discrete validation
    # accuracy, rather than by the relaxed training loss.
    initial_accuracy, _, _ = evaluate_conv_hdc(
        val_loader, frontend, initial_class_hvs, feature_hvs,
        level_hvs, tie_breaker_hv
    )
    best_accuracy = initial_accuracy
    best_epoch = 0
    best_frontend_state = copy.deepcopy(frontend.state_dict())
    best_class_hvs = initial_class_hvs.detach().clone()
    history = [{"epoch": 0, "validation_accuracy_percent": best_accuracy,
                "training_loss": None, "training_mistakes": None}]
    print(f"Epoch 0 (initialized prototypes): validation = {best_accuracy:.2f}%")

    for epoch in range(1, JOINT_EPOCHS + 1):
        frontend.train()
        running_loss = 0.0
        running_count = 0
        training_mistakes = 0

        for images, labels in train_loader:
            images, labels = images.to(DEVICE), labels.to(DEVICE)
            optimizer.zero_grad(set_to_none=True)

            # ADDED NEW: Forward uses deployable quantized convolution weights.
            pooled = frontend.pooled_values(images)
            query = encode_hdc_joint_train(
                pooled, frontend, feature_hvs, level_hvs,
                tie_breaker_hv, bound_lookup
            )
            prototypes = binarize_trainable_prototypes(prototype_scores)

            # ADDED NEW: Numerically EXACT Hamming distances in forward pass:
            # XOR(q,p) == q + p - 2*q*p when q and p are binary.
            # Soft derivatives through q/p allow true end-to-end gradients.
            distances = (query[:, None, :] + prototypes[None, :, :]
                         - 2.0 * query[:, None, :] * prototypes[None, :, :]).sum(-1)
            logits = -distances / JOINT_LOSS_TEMPERATURE
            loss = F.cross_entropy(logits, labels)
            loss.backward()
            optimizer.step()

            with torch.no_grad():
                batch_n = labels.numel()
                running_loss += float(loss.item()) * batch_n
                running_count += batch_n
                training_mistakes += (logits.argmax(dim=1) != labels).sum().item()

        # ADDED NEW: Evaluate with EXACT original binary encoder, NOT soft STE.
        class_hvs = (prototype_scores.detach() >= 0)
        val_accuracy, _, _ = evaluate_conv_hdc(
            val_loader, frontend, class_hvs, feature_hvs,
            level_hvs, tie_breaker_hv
        )

        mean_loss = running_loss / running_count
        history.append({"epoch": epoch, "validation_accuracy_percent": val_accuracy,
                        "training_loss": mean_loss,
                        "training_mistakes": training_mistakes})
        print(f"Epoch {epoch}: val = {val_accuracy:.2f}% "
              f"| CE = {mean_loss:.4f} | mistakes = {training_mistakes}")

        if val_accuracy > best_accuracy:
            best_accuracy = val_accuracy
            best_epoch = epoch
            best_frontend_state = copy.deepcopy(frontend.state_dict())
            best_class_hvs = class_hvs.clone()

    # ADDED NEW: Restore the SAME epoch's frontend and prototype bits.
    frontend.load_state_dict(best_frontend_state)
    frontend.eval()
    return best_class_hvs, best_epoch, best_accuracy, history

# ============================================================
# REGIONAL JOINT TRAINING — THRESHOLDS + HDC PROTOTYPES
# ============================================================

def train_joint_regional_hdc(train_loader, val_loader, frontend,
                             feature_hvs, level_hvs, tie_breaker_hv,
                             initial_class_hvs):

    # Jointly train:
    # 1. Three shared regional thresholds
    # 2. HDC class prototype scores
    #
    # Forward: exact binary HDC operations.
    # Backward: STE-based gradients.
    #
    # Hadamard feature HVs and level HVs remain fixed.

    # Initialize trainable prototype scores from binary class-majority HVs.
    prototype_scores = nn.Parameter(
        initial_class_hvs.float().mul(2.0).sub(1.0).to(DEVICE)
    )

    # Only thresholds and prototype scores are trainable.
    optimizer = torch.optim.Adam([
        {
            "params": [frontend.threshold_raw],
            "lr": JOINT_THRESHOLD_LR
        },
        {
            "params": [prototype_scores],
            "lr": JOINT_PROTOTYPE_LR
        }
    ])

    # Precompute all feature-HV XOR level-HV combinations.
    # Used only for the differentiable backward approximation.
    bound_lookup = (
        feature_hvs[:, None, :] ^ level_hvs[None, :, :]
    ).float().contiguous()

    # --------------------------------------------------------
    # Evaluate initial model (epoch 0)
    # --------------------------------------------------------

    initial_accuracy, _, _ = evaluate_conv_hdc(
        val_loader, frontend, initial_class_hvs,
        feature_hvs, level_hvs, tie_breaker_hv
    )

    best_accuracy = initial_accuracy
    best_epoch = 0

    # Save BOTH thresholds and prototypes from the same epoch.
    best_frontend_state = copy.deepcopy(frontend.state_dict())
    best_class_hvs = initial_class_hvs.detach().clone()

    history = [{
        "epoch": 0,
        "validation_accuracy_percent": best_accuracy,
        "training_loss": None,
        "training_mistakes": None
    }]

    print(
        f"Epoch 0 (initialized prototypes): "
        f"validation = {best_accuracy:.2f}%"
    )

    # --------------------------------------------------------
    # Joint training
    # --------------------------------------------------------

    for epoch in range(1, REGIONAL_JOINT_EPOCHS + 1):

        frontend.train()

        running_loss = 0.0
        running_count = 0
        training_mistakes = 0

        for images, labels in train_loader:

            images = images.to(DEVICE)
            labels = labels.to(DEVICE)

            optimizer.zero_grad(set_to_none=True)

            # Step 1: Original 2x2 regional averaging.
            pooled = frontend.pooled_values(images)

            # Step 2: Encode using hard HDC in forward,
            # with surrogate gradients in backward.
            query = encode_hdc_joint_train(
                pooled, frontend, feature_hvs, level_hvs,
                tie_breaker_hv, bound_lookup
            )

            # Step 3: Binary prototypes in forward,
            # STE-based gradients in backward.
            prototypes = binarize_trainable_prototypes(
                prototype_scores
            )

            # Step 4: Exact Hamming distances in forward.
            # XOR(q,p) = q + p - 2*q*p for binary values.
            distances = (
                query[:, None, :]
                + prototypes[None, :, :]
                - 2.0 * query[:, None, :] * prototypes[None, :, :]
            ).sum(dim=-1)

            # Step 5: Classification loss.
            logits = -distances / JOINT_LOSS_TEMPERATURE

            loss = F.cross_entropy(logits, labels)

            # Step 6: Jointly update thresholds and prototypes.
            loss.backward()
            optimizer.step()

            # Training statistics.
            with torch.no_grad():

                batch_n = labels.numel()

                running_loss += float(loss.item()) * batch_n
                running_count += batch_n

                training_mistakes += (
                    logits.argmax(dim=1) != labels
                ).sum().item()

        # ----------------------------------------------------
        # Validation with exact binary HDC
        # ----------------------------------------------------

        class_hvs = (prototype_scores.detach() >= 0)

        val_accuracy, _, _ = evaluate_conv_hdc(
            val_loader, frontend, class_hvs,
            feature_hvs, level_hvs, tie_breaker_hv
        )

        mean_loss = running_loss / running_count

        history.append({
            "epoch": epoch,
            "validation_accuracy_percent": val_accuracy,
            "training_loss": mean_loss,
            "training_mistakes": training_mistakes
        })

        current_thresholds = (
            frontend.thresholds().detach().cpu().flatten().tolist()
        )

        print(
            f"Epoch {epoch}: val = {val_accuracy:.2f}% "
            f"| CE = {mean_loss:.4f} "
            f"| mistakes = {training_mistakes} "
            f"| thresholds = {[round(t, 4) for t in current_thresholds]}"
        )

        # Save the best thresholds and prototypes together.
        if val_accuracy > best_accuracy:

            best_accuracy = val_accuracy
            best_epoch = epoch

            best_frontend_state = copy.deepcopy(frontend.state_dict())
            best_class_hvs = class_hvs.clone()

    # --------------------------------------------------------
    # Restore best validation checkpoint
    # --------------------------------------------------------

    frontend.load_state_dict(best_frontend_state)
    frontend.eval()

    return best_class_hvs, best_epoch, best_accuracy, history

def save_best_conv_model(output_dir, frontend, feature_hvs, level_hvs,
                         tie_breaker_hv, best_class_hvs, class_names,
                         best_epoch, best_val_accuracy):
    # ADDED NEW: Reuse the UNCHANGED original binary-HV export, then add the
    # exact learned convolution and channel-specific threshold configuration.
    save_best_model(
        output_dir, feature_hvs, level_hvs, tie_breaker_hv,
        best_class_hvs, class_names, best_epoch, best_val_accuracy
    )
    hardware_dir = output_dir / "hardware_model"
    with torch.no_grad():
        _fake_weights, w_integer, scales = frontend.quantized_weights()
        weight_array = w_integer.detach().cpu().numpy().astype(np.int8)
        scale_array = scales.reshape(-1).detach().cpu().numpy().astype(np.float32)
        thresholds_array = frontend.thresholds().detach().cpu().numpy().astype(np.float32)

    # ADDED NEW: Signed INT8 weights are serialized in [output_channel,1,3,3]
    # row-major order. The per-channel float32 scale defines their real value.
    # These scales would need to be implemented/calibrated in a physical chip.
    weight_array.tofile(hardware_dir / "conv_weights_int8.bin")
    scale_array.tofile(hardware_dir / "conv_weight_scales_float32.bin")
    thresholds_array.tofile(hardware_dir / "conv_thresholds_float32.bin")

    config_path = hardware_dir / "manifest.json"
    with open(config_path) as f:
        manifest = json.load(f)
    manifest.update({
        "feature_extractor": "appcip_style_conv_qat",
        "retrain_method": "joint_ste_gradient",
        "retrain_margin": None,
        "input_shape": [1, 32, 32],
        "convolution_kernel_size": 3,
        "convolution_channels": frontend.channels,
        #"svhn_photodiode_channel": CONV_SENSOR_COLOR if DATASET == "SVHN" else None,
        "input_color_mode": "grayscale",
        "convolution_stride": 1,
        "convolution_padding": 0,
        "convolution_bias": False,
        "conv_output_per_channel": [30, 30],
        "center_crop_output_per_channel": [28, 28],
        "pooling": {"mode": "average", "kernel": frontend.pool_size,
                    "stride": frontend.pool_size},
        "feature_order": "channel-major, then pooled row-major; 196 values",
        "level_thresholds": thresholds_array.tolist(),
        "level_thresholds_note": "3 trained thresholds per convolution channel; four output levels 0..3",
        "convolution_weights": {
            "file": "conv_weights_int8.bin", "shape": list(weight_array.shape),
            "dtype": "int8", "integer_range": [-128, 127],
            "real_weight": "integer_weight * per_output_channel_scale"
        },
        "convolution_weight_scales": "conv_weight_scales_float32.bin",
        "convolution_thresholds": "conv_thresholds_float32.bin",
        "encoding": "XOR fixed feature HV with fixed level HV, threshold-based bundling",
        "training": "Joint QAT/STE with Hamming-distance cross-entropy",
        "hardware_status": "Proposed AppCiP modification; NOT validated as an analog circuit"
    })
    with open(config_path, "w") as f:
        json.dump(manifest, f, indent=4)

    # ADDED NEW: Complete replay checkpoint with both original HDC bits and
    # trained frontend's latent weights. No validation/test samples saved.
    checkpoint_path = output_dir / "best_model.pt"
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    checkpoint["config"] = manifest
    checkpoint["conv_frontend_state_dict"] = {
        k: v.detach().cpu().clone() for k, v in frontend.state_dict().items()
    }
    checkpoint["conv_weights_int8"] = torch.from_numpy(weight_array.copy())
    checkpoint["conv_weight_scales"] = torch.from_numpy(scale_array.copy())
    checkpoint["conv_thresholds"] = torch.from_numpy(thresholds_array.copy())
    torch.save(checkpoint, checkpoint_path)
    print("INT8 convolution weights and trained thresholds saved to:", hardware_dir)

# ============================================================
# REGIONAL JOINT TRAINING — SAVE BEST MODEL
# ============================================================

def save_best_regional_joint_model(
    output_dir, frontend, feature_hvs, level_hvs,
    tie_breaker_hv, best_class_hvs, class_names,
    best_epoch, best_val_accuracy
):
    # Reuse the original HDC model-saving function.
    # IMPORTANT: This is the regional method; NO convolution is used.
    # Only the three shared regional thresholds and HDC prototypes
    # are learned. Feature HVs and level HVs remain fixed.

    save_best_model(
        output_dir, feature_hvs, level_hvs, tie_breaker_hv,
        best_class_hvs, class_names, best_epoch, best_val_accuracy
    )

    hardware_dir = output_dir / "hardware_model"

    # Get the three learned thresholds from the best epoch.
    with torch.no_grad():
        learned_thresholds = (
            frontend.thresholds()
            .detach()
            .cpu()
            .flatten()
            .numpy()
            .astype(np.float32)
        )

    # Save thresholds as three float32 values.
    learned_thresholds.tofile(
        hardware_dir / "regional_thresholds_float32.bin"
    )

    # --------------------------------------------------------
    # Update hardware manifest
    # --------------------------------------------------------

    manifest_path = hardware_dir / "manifest.json"

    with open(manifest_path) as f:
        manifest = json.load(f)

    manifest.update({
        "feature_extractor": "regional_joint",
        "training": "Joint STE training of thresholds and HDC prototypes",
        "retrain_method": "joint_ste_gradient",
        "retrain_margin": None,
        "region_size": REGION_SIZE,
        "num_features": NUM_FEATURES,
        "num_levels": NUM_LEVELS,
        "initial_level_thresholds": list(LEVEL_THRESHOLDS),
        "level_thresholds": learned_thresholds.tolist(),
        "level_thresholds_note": (
            "Three learned thresholds shared across all 196 regions"
        ),
        "regional_thresholds": {
            "file": "regional_thresholds_float32.bin",
            "count": 3,
            "dtype": "float32"
        },
        "pooling": {
            "mode": "average",
            "kernel": REGION_SIZE,
            "stride": REGION_SIZE
        },
        "encoding": (
            "XOR fixed feature HV with fixed level HV, "
            "threshold-based bundling"
        ),
        "inference": "Minimum Hamming distance to binary class prototypes"
    })

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    # --------------------------------------------------------
    # Update PyTorch checkpoint
    # --------------------------------------------------------

    checkpoint_path = output_dir / "best_model.pt"

    checkpoint = torch.load(
        checkpoint_path, map_location="cpu", weights_only=False
    )

    checkpoint["config"] = manifest

    checkpoint["regional_frontend_state_dict"] = {
        k: v.detach().cpu().clone()
        for k, v in frontend.state_dict().items()
    }

    checkpoint["regional_thresholds"] = torch.from_numpy(
        learned_thresholds.copy()
    )

    torch.save(checkpoint, checkpoint_path)

    print("Learned regional thresholds:", learned_thresholds.tolist())
    print("Regional joint model saved to:", checkpoint_path)
    print("Hardware model saved to:", hardware_dir)

def run_conv_experiment():
    # ADDED NEW: Separate joint-training entry point. The original main below
    # is untouched and still executes when FEATURE_EXTRACTOR == "regional".

    # ADDED NEW: All convolution inputs are single-channel grayscale images.
    # SVHN is converted to grayscale while preserving its 32x32 resolution.
    # MNIST, FashionMNIST, and EMNIST Letters are zero-padded from 28x28 to 32x32.

    folder_name = (
        f"{time.strftime('%Y%m%d_%H%M%S')}_"
        f"{DATASET}_D{HDC_DIM}_C{CONV_CHANNELS}_INT8_L{NUM_LEVELS}_joint"
    )

    output_dir = RESULTS_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    train_loader, val_loader, test_loader, class_names = load_dataset()

    # ADDED NEW: Generate HDC HVs BEFORE initializing the convolution.
    # This preserves the generated HVs across C=1 and C=4 for the same RNG seed.
    feature_hvs = generate_feature_hvs()
    level_hvs = generate_level_hvs()
    tie_breaker_hv = generate_tie_breaker_hv()

    frontend = AppCiPConvFeatureExtractor(CONV_CHANNELS).to(DEVICE)

    # ADDED NEW: Legacy DataLoader uses BATCH_SIZE=256. Make a smaller
    # training DataLoader only for the differentiable joint training pass.
    # The train/validation/test dataset SUBSETS remain exactly the same.
    joint_loader = DataLoader(
        train_loader.dataset, batch_size=JOINT_BATCH_SIZE, shuffle=True
    )

    initial_thresholds = frontend.initialize_thresholds_from_train(train_loader)
    print("Initial train-only thresholds by channel:", initial_thresholds)

    # ADDED NEW: Initialize prototypes from real discrete HDC queries before
    # starting joint training. This is not a temporary CNN classifier.
    start = time.perf_counter()

    initial_class_hvs = initialize_conv_class_prototypes(
        train_loader, frontend, feature_hvs, level_hvs,
        tie_breaker_hv, len(class_names)
    )

    if DEVICE.type == "cuda":
        torch.cuda.synchronize()

    prototype_init_time = time.perf_counter() - start

    start = time.perf_counter()

    best_class_hvs, best_epoch, best_val_accuracy, history = train_joint_conv_hdc(
        joint_loader, val_loader, frontend, feature_hvs, level_hvs,
        tie_breaker_hv, initial_class_hvs
    )


    if DEVICE.type == "cuda":
        torch.cuda.synchronize()

    joint_train_time = time.perf_counter() - start

    # ============================================================
    # ADDED NEW: THRESHOLD PRECISION EXPERIMENT
    # ============================================================
    # Evaluate learned convolutional thresholds at different precisions.
    # Reporting only: does NOT affect model selection or update parameters.
    # Evaluate FP32, 6, 8, 10, and 12-bit thresholds on validation and test.

    evaluate_threshold_precision(
        train_loader, val_loader, frontend,
        best_class_hvs, feature_hvs,
        level_hvs, tie_breaker_hv,
        test_loader=test_loader,
        output_dir=output_dir
    )

    # ADDED NEW: Save frozen frontend and class bits selected by VAL only.
    with open(output_dir / "training_history.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "epoch", "validation_accuracy_percent", "training_loss",
            "training_mistakes"
        ])
        writer.writeheader()
        writer.writerows(history)

    save_best_conv_model(
        output_dir, frontend, feature_hvs, level_hvs, tie_breaker_hv,
        best_class_hvs, class_names, best_epoch, best_val_accuracy
    )

    analyze_conv_feature_distribution(train_loader, frontend, output_dir)

    # ADDED NEW: Official test evaluated ONCE with frozen best validation epoch.
    start = time.perf_counter()

    accuracy, per_class_accuracy, confusion_matrix = evaluate_conv_hdc(
        test_loader, frontend, best_class_hvs, feature_hvs,
        level_hvs, tie_breaker_hv
    )

    if DEVICE.type == "cuda":
        torch.cuda.synchronize()

    test_time = time.perf_counter() - start

    save_confusion_matrix(confusion_matrix, class_names, output_dir)

    with torch.no_grad():
        _, w_int, w_scales = frontend.quantized_weights()
        learned_thresholds = frontend.thresholds().detach().cpu().tolist()

    results = {
        "dataset": DATASET,
        "feature_extractor": "conv",
        "input_size": [32, 32],
        "convolution_channels": CONV_CHANNELS,
        "input_color_mode": "grayscale",
        "convolution_kernel_size": 3,
        "convolution_weights_bits": 8,
        "convolution_weight_integer_min": int(w_int.min().item()),
        "convolution_weight_integer_max": int(w_int.max().item()),
        "convolution_weight_scales": w_scales.reshape(-1).detach().cpu().tolist(),
        "pooling_size": frontend.pool_size,
        "num_features": NUM_FEATURES,
        "num_levels": NUM_LEVELS,
        "level_thresholds_per_channel": learned_thresholds,
        "sensor_bits_per_image": SENSOR_BITS_PER_IMAGE,
        "hdc_dim": HDC_DIM,
        "feature_hv_mode": FEATURE_HV_MODE,
        "level_mode": LEVEL_MODE,
        "level_correlation_range": LEVEL_CORRELATION_RANGE,
        "query_popcount_threshold": QUERY_POPCOUNT_THRESHOLD,
        "best_epoch": best_epoch,
        "initial_validation_accuracy_percent": history[0]["validation_accuracy_percent"],
        "best_validation_accuracy_percent": best_val_accuracy,
        "accuracy_percent": accuracy,
        "per_class_accuracy_percent": dict(zip(class_names, per_class_accuracy)),
        "training_samples": len(train_loader.dataset),
        "validation_samples": len(val_loader.dataset),
        "test_samples": len(test_loader.dataset),
        "prototype_initialization_time_seconds": prototype_init_time,
        "joint_training_time_seconds": joint_train_time,
        "testing_time_seconds": test_time,
        "joint_batch_size": JOINT_BATCH_SIZE,
        "seed": SEED,
        "device": str(DEVICE),
    }

    with open(output_dir / "results.json", "w") as f:
        json.dump(results, f, indent=4)

    report = [
        "========== ADHD — APPCIP-STYLE JOINT TRAINING ==========",
        f"Dataset: {DATASET}",
        f"Convolution filters: {CONV_CHANNELS}, kernel: 3x3, signed INT8 weights",
        f"Conv 30x30 -> crop 28x28 -> {frontend.pool_size}x{frontend.pool_size} avgpool",
        f"Trained thresholds (each channel): {learned_thresholds}",
        f"Final features: {NUM_FEATURES}, 2 bits each = {SENSOR_BITS_PER_IMAGE} bits/image",
        f"Hadamard dimension: {HDC_DIM}, popcount threshold: {QUERY_POPCOUNT_THRESHOLD}",
        f"Train / validation / test: {len(train_loader.dataset)} / "
        f"{len(val_loader.dataset)} / {len(test_loader.dataset)}",
        f"Best epoch: {best_epoch}",
        f"Best validation accuracy: {best_val_accuracy:.2f}%",
        f"Final TEST accuracy: {accuracy:.2f}%",
        f"Prototype initialization time: {prototype_init_time:.2f} s",
        f"Joint training time: {joint_train_time:.2f} s",
        f"Testing time: {test_time:.2f} s",
        "Per-class TEST accuracy:",
    ]

    for name, acc in zip(class_names, per_class_accuracy):
        report.append(f"  {name}: {acc:.2f}%")

    with open(output_dir / "report.txt", "w") as f:
        f.write("\n".join(report) + "\n")

    print("\n" + "\n".join(report))
    print(f"\nResults saved to: {output_dir}")

# ============================================================
# REGIONAL JOINT TRAINING — COMPLETE EXPERIMENT
# ============================================================

def run_regional_joint_experiment():

    # --------------------------------------------------------
    # 1. Create a separate output directory
    # --------------------------------------------------------

    folder_name = (
        f"{time.strftime('%Y%m%d_%H%M%S')}_"
        f"{DATASET}_D{HDC_DIM}_R{REGION_SIZE}_L{NUM_LEVELS}_regional_joint"
    )

    output_dir = RESULTS_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------
    # 2. Load the original dataset
    # --------------------------------------------------------

    # IMPORTANT:
    # This is the regional method, so no convolution-related
    # padding or preprocessing is applied.
    # The original training/validation/test splits are preserved.

    train_loader, val_loader, test_loader, class_names = load_dataset()

    # --------------------------------------------------------
    # 3. Generate the original fixed HDC hypervectors
    # --------------------------------------------------------

    # Same deterministic Hadamard feature HVs.
    # Same correlated level HVs.
    # Same tie-breaker HV.

    feature_hvs = generate_feature_hvs()
    level_hvs = generate_level_hvs()
    tie_breaker_hv = generate_tie_breaker_hv()

    # --------------------------------------------------------
    # 4. Initialize regional frontend
    # --------------------------------------------------------

    # No convolution.
    # Fixed 2x2 average pooling and three shared trainable thresholds.

    frontend = RegionalJointFeatureExtractor().to(DEVICE)

    initial_thresholds = (
        frontend.thresholds().detach().cpu().flatten().tolist()
    )

    print("Initial regional thresholds:", initial_thresholds)

    # --------------------------------------------------------
    # 5. Initialize class prototypes using majority voting
    # --------------------------------------------------------

    start = time.perf_counter()

    # Reuse the prototype-initialization function originally
    # written for the convolutional method.
    #
    # IMPORTANT: No convolution is performed here.
    # The RegionalJointFeatureExtractor supplies the original
    # 2x2 averages and hard quantized regional features.
    # The HDC prototype initialization is unchanged.

    initial_class_hvs = initialize_conv_class_prototypes(
        train_loader, frontend, feature_hvs,
        level_hvs, tie_breaker_hv, len(class_names)
    )

    if DEVICE.type == "cuda":
        torch.cuda.synchronize()

    prototype_init_time = time.perf_counter() - start

    # --------------------------------------------------------
    # 6. Jointly train regional thresholds and class prototypes
    # --------------------------------------------------------

    start = time.perf_counter()

    best_class_hvs, best_epoch, best_val_accuracy, history = (
        train_joint_regional_hdc(
            train_loader, val_loader, frontend,
            feature_hvs, level_hvs, tie_breaker_hv,
            initial_class_hvs
        )
    )

    if DEVICE.type == "cuda":
        torch.cuda.synchronize()

    joint_train_time = time.perf_counter() - start

    # The training function has restored BOTH:
    # - Best regional thresholds
    # - Best binary class prototypes
    # from the same best validation epoch.

    learned_thresholds = (
        frontend.thresholds().detach().cpu().flatten().tolist()
    )

    print("Best learned regional thresholds:", learned_thresholds)

    # --------------------------------------------------------
    # 7. Save training history
    # --------------------------------------------------------

    with open(output_dir / "training_history.csv", "w", newline="") as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "epoch",
                "validation_accuracy_percent",
                "training_loss",
                "training_mistakes"
            ]
        )

        writer.writeheader()
        writer.writerows(history)

    # --------------------------------------------------------
    # 8. Save the best model and hardware files
    # --------------------------------------------------------

    save_best_regional_joint_model(
        output_dir, frontend, feature_hvs, level_hvs,
        tie_breaker_hv, best_class_hvs, class_names,
        best_epoch, best_val_accuracy
    )

    # --------------------------------------------------------
    # 9. Analyze learned feature distribution
    # --------------------------------------------------------

    # Reuse the feature-distribution function from convolutional HDC.
    # IMPORTANT: No convolution is performed here.
    # Features come from the regional frontend with learned thresholds.

    analyze_conv_feature_distribution(
        train_loader, frontend, output_dir
    )

    # --------------------------------------------------------
    # 10. Evaluate threshold precision
    # --------------------------------------------------------

    # Reuse the existing threshold-precision evaluation.
    # IMPORTANT: No convolution is performed here.
    # We quantize the three learned REGIONAL thresholds.
    # This evaluates FP32, 6-bit, 8-bit, 10-bit, and 12-bit
    # thresholds on the validation dataset.

    # Reuse threshold-precision evaluation from the convolutional method.
    # IMPORTANT: No convolution is performed here.
    # Thresholds belong to the 2x2 regional feature extractor.
    #
    # Reporting only: does NOT affect model selection or update parameters.
    # Evaluate FP32, 6, 8, 10, and 12-bit thresholds on validation and test.

    evaluate_threshold_precision(
        train_loader, val_loader, frontend,
        best_class_hvs, feature_hvs,
        level_hvs, tie_breaker_hv,
        test_loader=test_loader,
        output_dir=output_dir
    )

    # --------------------------------------------------------
    # 11. Final test evaluation
    # --------------------------------------------------------

    start = time.perf_counter()

    # Reuse the existing HDC evaluation function from convolutional HDC.
    # IMPORTANT: No convolution is performed here.
    # The RegionalJointFeatureExtractor provides 2x2 regional averages
    # and learned thresholds. All HDC operations remain unchanged.
    # Evaluation uses HARD features and binary class prototypes.

    accuracy, per_class_accuracy, confusion_matrix = evaluate_conv_hdc(
        test_loader, frontend, best_class_hvs,
        feature_hvs, level_hvs, tie_breaker_hv
    )

    if DEVICE.type == "cuda":
        torch.cuda.synchronize()

    test_time = time.perf_counter() - start

    save_confusion_matrix(confusion_matrix, class_names, output_dir)

    # --------------------------------------------------------
    # 12. Save results.json
    # --------------------------------------------------------

    results = {
        "dataset": DATASET,
        "feature_extractor": "regional_joint",
        "training_method": "joint_ste_gradient",
        "image_size": IMAGE_SIZE,
        "region_size": REGION_SIZE,
        "num_features": NUM_FEATURES,
        "num_levels": NUM_LEVELS,
        "initial_level_thresholds": list(LEVEL_THRESHOLDS),
        "learned_level_thresholds": learned_thresholds,
        "bits_per_feature": BITS_PER_FEATURE,
        "sensor_bits_per_image": SENSOR_BITS_PER_IMAGE,
        "hdc_dim": HDC_DIM,
        "feature_hv_mode": FEATURE_HV_MODE,
        "level_mode": LEVEL_MODE,
        "level_correlation_range": LEVEL_CORRELATION_RANGE,
        "query_popcount_threshold": QUERY_POPCOUNT_THRESHOLD,
        "training_epochs": REGIONAL_JOINT_EPOCHS,
        "threshold_learning_rate": JOINT_THRESHOLD_LR,
        "prototype_learning_rate": JOINT_PROTOTYPE_LR,
        "batch_size": BATCH_SIZE,
        "best_epoch": best_epoch,
        "initial_validation_accuracy_percent":
            history[0]["validation_accuracy_percent"],
        "best_validation_accuracy_percent": best_val_accuracy,
        "accuracy_percent": accuracy,
        "per_class_accuracy_percent":
            dict(zip(class_names, per_class_accuracy)),
        "training_samples": len(train_loader.dataset),
        "validation_samples": len(val_loader.dataset),
        "test_samples": len(test_loader.dataset),
        "prototype_initialization_time_seconds": prototype_init_time,
        "joint_training_time_seconds": joint_train_time,
        "testing_time_seconds": test_time,
        "seed": SEED,
        "device": str(DEVICE)
    }

    with open(output_dir / "results.json", "w") as f:
        json.dump(results, f, indent=4)

    # --------------------------------------------------------
    # 13. Save report.txt
    # --------------------------------------------------------

    report = [
        "========== ADHD — REGIONAL JOINT TRAINING ==========",
        f"Dataset: {DATASET}",
        f"Region size: {REGION_SIZE}x{REGION_SIZE}",
        f"Features: {NUM_FEATURES}",
        f"Levels: {NUM_LEVELS}",
        f"Initial thresholds: {LEVEL_THRESHOLDS}",
        f"Learned thresholds: {learned_thresholds}",
        f"Sensor output: {SENSOR_BITS_PER_IMAGE} bits/image",
        f"HDC dimension: {HDC_DIM}",
        f"Feature HV mode: {FEATURE_HV_MODE}",
        f"Level HV mode: {LEVEL_MODE}",
        f"Level correlation range: {LEVEL_CORRELATION_RANGE}",
        "Training: Joint STE-based thresholds and prototypes",
        f"Training epochs: {REGIONAL_JOINT_EPOCHS}",
        f"Batch size: {BATCH_SIZE}",
        f"Train / validation / test: "
        f"{len(train_loader.dataset)} / "
        f"{len(val_loader.dataset)} / "
        f"{len(test_loader.dataset)}",
        f"Epoch 0 validation accuracy: "
        f"{history[0]['validation_accuracy_percent']:.2f}%",
        f"Best epoch: {best_epoch}",
        f"Best validation accuracy: {best_val_accuracy:.2f}%",
        f"Final TEST accuracy: {accuracy:.2f}%",
        f"Prototype initialization time: {prototype_init_time:.2f} s",
        f"Joint training time: {joint_train_time:.2f} s",
        f"Test time: {test_time:.2f} s",
        "Per-class TEST accuracy:"
    ]

    for name, acc in zip(class_names, per_class_accuracy):
        report.append(f"  {name}: {acc:.2f}%")

    with open(output_dir / "report.txt", "w") as f:
        f.write("\n".join(report) + "\n")

    print("\n" + "\n".join(report))
    print(f"\nResults saved to: {output_dir}")

# ============================================================
# 9. MAIN EXPERIMENT
# ============================================================

if __name__ == "__main__":
    set_seed(SEED)

    # ============================================================
    # SELECT FEATURE EXTRACTION AND TRAINING APPROACH
    # ============================================================

    # Method 1: Convolutional features with joint STE training.
    if FEATURE_EXTRACTOR == "conv":
        run_conv_experiment()
        raise SystemExit(0)

    # Method 2: Regional features with joint STE training.
    # No convolution. Learn three shared regional thresholds
    # and binary HDC class prototypes together.
    if FEATURE_EXTRACTOR == "regional_joint":
        run_regional_joint_experiment()
        raise SystemExit(0)

    # Method 3: Original regional HDC with fixed thresholds.
    # The original integer margin-based retraining continues below.

    # The original regional HDC pipeline continues below unchanged.
    folder_name = (
        f"{time.strftime('%Y%m%d_%H%M%S')}_"
        f"{DATASET}_D{HDC_DIM}_R{REGION_SIZE}_L{NUM_LEVELS}_retrain"
    )
    output_dir = RESULTS_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Never use the official test set to select the best epoch.
    train_loader, val_loader, test_loader, class_names = load_dataset()

    # Fixed encoder. Save its exact bit patterns with the best prototypes.
    feature_hvs = generate_feature_hvs()
    level_hvs = generate_level_hvs()
    tie_breaker_hv = generate_tie_breaker_hv()

    # Diagnostics are independent of training and model selection.
    analyze_feature_distribution(train_loader, output_dir)

    start = time.perf_counter()
    initial_hvs, class_counts, class_samples = train_hdc(
        train_loader, feature_hvs, level_hvs, tie_breaker_hv
    )
    if DEVICE.type == "cuda":
        torch.cuda.synchronize()
    single_pass_time = time.perf_counter() - start

    # Error-driven retraining of class prototypes ONLY.
    start = time.perf_counter()
    best_class_hvs, best_epoch, best_val_accuracy, history = retrain_hdc(
        train_loader, val_loader, feature_hvs, level_hvs,
        tie_breaker_hv, initial_hvs, class_counts, class_samples
    )
    if DEVICE.type == "cuda":
        torch.cuda.synchronize()
    retrain_time = time.perf_counter() - start

    # Record validation history so we know exactly why this epoch won.
    with open(output_dir / "training_history.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "epoch", "validation_accuracy_percent", "training_mistakes"
        ])
        writer.writeheader()
        writer.writerows(history)

    # Freeze the best model BEFORE examining the test set.
    save_best_model(
        output_dir, feature_hvs, level_hvs, tie_breaker_hv,
        best_class_hvs, class_names, best_epoch, best_val_accuracy
    )

    # Official test set: evaluated ONCE, using the selected checkpoint.
    start = time.perf_counter()
    accuracy, per_class_accuracy, confusion_matrix = evaluate_hdc(
        test_loader, feature_hvs, level_hvs, tie_breaker_hv, best_class_hvs
    )
    if DEVICE.type == "cuda":
        torch.cuda.synchronize()
    test_time = time.perf_counter() - start
    save_confusion_matrix(confusion_matrix, class_names, output_dir)

    results = {
        "dataset": DATASET,
        "image_size": IMAGE_SIZE,
        "region_size": REGION_SIZE,
        "num_features": NUM_FEATURES,
        "num_levels": NUM_LEVELS,
        "level_thresholds": LEVEL_THRESHOLDS,
        "bits_per_feature": BITS_PER_FEATURE,
        "sensor_bits_per_image": SENSOR_BITS_PER_IMAGE,
        "hdc_dim": HDC_DIM,
        "feature_hv_mode": FEATURE_HV_MODE,
        "level_mode": LEVEL_MODE,
        "level_correlation_range": LEVEL_CORRELATION_RANGE,
        "retraining_epochs": RETRAIN_EPOCHS,
        "retrain_init_strength": RETRAIN_INIT_STRENGTH,
        "retrain_step": RETRAIN_STEP,
        "best_epoch": best_epoch,
        "initial_validation_accuracy_percent": history[0]["validation_accuracy_percent"],
        "best_validation_accuracy_percent": best_val_accuracy,
        "accuracy_percent": accuracy,
        "per_class_accuracy_percent": dict(zip(class_names, per_class_accuracy)),
        "training_samples": len(train_loader.dataset),
        "validation_samples": len(val_loader.dataset),
        "test_samples": len(test_loader.dataset),
        "single_pass_training_time_seconds": single_pass_time,
        "retraining_time_seconds": retrain_time,
        "testing_time_seconds": test_time,
        "batch_size": BATCH_SIZE,
        "seed": SEED,
        "device": str(DEVICE),
    }
    with open(output_dir / "results.json", "w") as f:
        json.dump(results, f, indent=4)

    report = [
        "========== ADHD V1 — RETRAINING RESULTS ==========",
        f"Dataset: {DATASET}",
        f"Region size: {REGION_SIZE}x{REGION_SIZE}",
        f"Levels: {NUM_LEVELS}, thresholds: {LEVEL_THRESHOLDS}",
        f"Sensor output: {SENSOR_BITS_PER_IMAGE} bits/image",
        f"HDC dimension: {HDC_DIM}",
        f"Feature HV mode: {FEATURE_HV_MODE}",
        f"Level HV mode: {LEVEL_MODE}",
        f"Level correlation range: {LEVEL_CORRELATION_RANGE}",
        f"Train / validation / test: {len(train_loader.dataset)} / "
        f"{len(val_loader.dataset)} / {len(test_loader.dataset)}",
        f"Epoch 0 validation accuracy: {history[0]['validation_accuracy_percent']:.2f}%",
        f"Best epoch: {best_epoch}",
        f"Best validation accuracy: {best_val_accuracy:.2f}%",
        f"Final TEST accuracy (selected checkpoint): {accuracy:.2f}%",
        f"Single-pass train time: {single_pass_time:.2f} s",
        f"Retrain/validation time: {retrain_time:.2f} s",
        f"Test time: {test_time:.2f} s",
        "Per-class TEST accuracy:",
    ]
    for name, acc in zip(class_names, per_class_accuracy):
        report.append(f"  {name}: {acc:.2f}%")
    with open(output_dir / "report.txt", "w") as f:
        f.write("\n".join(report) + "\n")
    print("\n" + "\n".join(report))
    print(f"\nResults saved to: {output_dir}")
