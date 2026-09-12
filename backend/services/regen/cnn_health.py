"""
STEP 4 - CNN crop health check.

The trained model (MobileNetV2 transfer learning on PlantVillage, see
backend/cnn_training/train.py) runs in an ISOLATED Python 3.11 +
TensorFlow venv (backend/cnn_training/.venv) because TensorFlow has no
wheel for the Python 3.14 this main backend runs on. `predict_crop_health`
bridges to it as a subprocess, exactly the same swap-point signature the
placeholder used before training happened - nothing in main.py, M1 or M3
needs to change.

Coverage note: PlantVillage only has 14 crop species, so this model only
recognises Corn (maize), Potato and Soybean out of Kisan Sathi's 18 crops -
every other crop's photo falls back to the baseline placeholder below (that
is expected and reported honestly in the result note, not silently wrong).

Graceful degradation: if the trained model files aren't present (fresh
checkout before training), or the subprocess fails or times out, this
returns the same baseline placeholder result Part B originally shipped
with - the health-check module never blocks the rest of the pipeline.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../backend
CNN_TRAINING_DIR = BACKEND_DIR / "cnn_training"

TRAINING_VENV_PYTHON = CNN_TRAINING_DIR / ".venv" / "Scripts" / "python.exe"
PREDICT_SCRIPT = CNN_TRAINING_DIR / "predict.py"
MODEL_FILE = CNN_TRAINING_DIR / "crop_health_model.h5"
LABELS_FILE = CNN_TRAINING_DIR / "labels.json"

SUBPROCESS_TIMEOUT_SECONDS = 30


@dataclass
class CropHealthResult:
    score: float  # 0-1, 1.0 = fully healthy
    label: str
    is_placeholder: bool
    note: str


def _baseline_placeholder(note: str) -> CropHealthResult:
    return CropHealthResult(score=1.0, label="unscored", is_placeholder=True, note=note)


def _model_is_ready() -> bool:
    return TRAINING_VENV_PYTHON.exists() and PREDICT_SCRIPT.exists() and MODEL_FILE.exists() and LABELS_FILE.exists()


def predict_crop_health(image_bytes: bytes) -> CropHealthResult:
    if not _model_is_ready():
        return _baseline_placeholder(
            "No trained health-check model is deployed yet. The photo was "
            "received but not analysed - baseline health (1.0) was assumed "
            "for the rotation and fertiliser modules."
        )

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        completed = subprocess.run(
            [str(TRAINING_VENV_PYTHON), str(PREDICT_SCRIPT), tmp_path],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _baseline_placeholder(
            "The crop health model took too long to respond - baseline health (1.0) was assumed."
        )
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass

    if completed.returncode != 0 or not completed.stdout.strip():
        return _baseline_placeholder(
            f"Crop health model failed to run ({completed.stderr.strip()[:200] or 'no output'}) "
            "- baseline health (1.0) was assumed."
        )

    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return _baseline_placeholder(
            "Crop health model returned an unreadable result - baseline health (1.0) was assumed."
        )

    if "error" in result:
        return _baseline_placeholder(f"Crop health check failed ({result['error']}) - baseline health (1.0) assumed.")

    health_score = float(result["health_score"]) / 100.0
    status = result["health_status"]
    disease = result["disease_class"]
    confidence = result["confidence"]

    return CropHealthResult(
        score=round(health_score, 3),
        label=disease,
        is_placeholder=False,
        note=f"{status} - {disease.replace('_', ' ').replace('___', ' - ')} ({confidence}% confidence).",
    )
