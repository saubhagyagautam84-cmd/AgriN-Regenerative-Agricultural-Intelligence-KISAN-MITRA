"""
Standalone inference CLI for the trained crop-health CNN - adapted from the
notebook's Step 12 reference code.

Runs inside backend/cnn_training/.venv (Python 3.11 + TensorFlow), NOT the
main backend's venv (Python 3.14, which has no TensorFlow wheel). The main
backend calls this as a subprocess and reads the JSON line from stdout - see
backend/services/regen/cnn_health.py for the bridge.

Usage:
    .venv\\Scripts\\python.exe predict.py <path-to-image>

Prints exactly one line of JSON to stdout:
    {"disease_class": "...", "confidence": 91.2, "health_status": "Healthy",
     "health_score": 91.2}
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import tensorflow as tf

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "crop_health_model.h5")
LABELS_PATH = os.path.join(HERE, "labels.json")
IMG_SIZE = (224, 224)


def predict_crop_health(image_path: str) -> dict:
    model = tf.keras.models.load_model(MODEL_PATH)
    with open(LABELS_PATH) as f:
        class_names = json.load(f)

    img = tf.keras.utils.load_img(image_path, target_size=IMG_SIZE)
    img_array = tf.keras.utils.img_to_array(img)
    img_array = tf.expand_dims(img_array, 0)
    predictions = model.predict(img_array, verbose=0)
    predicted_class = class_names[int(np.argmax(predictions[0]))]
    confidence = float(np.max(predictions[0]) * 100)

    is_healthy = "healthy" in predicted_class.lower()
    return {
        "disease_class": predicted_class,
        "confidence": round(confidence, 1),
        "health_status": "Healthy" if is_healthy else "Diseased",
        "health_score": confidence if is_healthy else round(100 - confidence, 1),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: predict.py <image_path>"}))
        sys.exit(1)
    try:
        result = predict_crop_health(sys.argv[1])
        print(json.dumps(result))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
