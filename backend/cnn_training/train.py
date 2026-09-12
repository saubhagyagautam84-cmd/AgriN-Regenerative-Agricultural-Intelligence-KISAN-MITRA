"""
Kisan Sathi - Crop Health CNN, adapted from the provided Colab notebook for
LOCAL execution (no GPU, Python 3.11 + TensorFlow 2.15 in this isolated
backend/cnn_training/.venv - the main backend runs Python 3.14, which has no
TensorFlow wheel yet, hence the separate environment).

Deviations from the original notebook, and why:
  * No `!pip install` / Colab magics - this runs as a plain script.
  * TARGET_CROPS narrowed to ["Corn", "Potato", "Soybean"] - the only 3 of
    Kisan Sathi's 18 crops that actually exist in PlantVillage's 14 species
    (Wheat, Rice, Cotton, Sugarcane, Mustard, Chickpea, Groundnut, Pearl
    Millet, Lentil, Pigeon Pea, Green Gram, Black Gram, Sorghum, Barley,
    Sunflower have no PlantVillage data at all).
  * The dataset was already sparse-checked-out to just those 3 species'
    folders (see backend/cnn_training/PlantVillage-Dataset/raw/color), so
    there is no need to build a separate filtered/symlinked directory -
    DATA_DIR points straight at it.
  * EPOCHS left at 8 as in the original; on CPU this is expected to take
    considerably longer than Colab's 20-30 min GPU estimate.
  * Step 8 (optional fine-tuning) and Step 11 (Colab zip/download) are
    dropped - not applicable outside Colab.

Run from backend/cnn_training/:
    .venv\\Scripts\\python.exe train.py
"""

from __future__ import annotations

import json
import os

import numpy as np
import tensorflow as tf

print("TensorFlow version:", tf.__version__)
print("GPU available:", tf.config.list_physical_devices("GPU"))

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "PlantVillage-Dataset", "raw", "color")
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 8

print("Classes found:", os.listdir(DATA_DIR))

# --- Step 4: train/validation datasets -------------------------------------
train_ds = tf.keras.utils.image_dataset_from_directory(
    DATA_DIR,
    validation_split=0.2,
    subset="training",
    seed=42,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
)
val_ds = tf.keras.utils.image_dataset_from_directory(
    DATA_DIR,
    validation_split=0.2,
    subset="validation",
    seed=42,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
)

class_names = train_ds.class_names
print("Training on", len(class_names), "classes:", class_names)

with open(os.path.join(HERE, "labels.json"), "w") as f:
    json.dump(class_names, f, indent=2)

AUTOTUNE = tf.data.AUTOTUNE
train_ds = train_ds.cache().prefetch(buffer_size=AUTOTUNE)
val_ds = val_ds.cache().prefetch(buffer_size=AUTOTUNE)

# --- Step 5: MobileNetV2 transfer learning ----------------------------------
data_augmentation = tf.keras.Sequential(
    [
        tf.keras.layers.RandomFlip("horizontal"),
        tf.keras.layers.RandomRotation(0.1),
        tf.keras.layers.RandomZoom(0.1),
    ]
)
preprocess_input = tf.keras.applications.mobilenet_v2.preprocess_input

base_model = tf.keras.applications.MobileNetV2(
    input_shape=IMG_SIZE + (3,), include_top=False, weights="imagenet"
)
base_model.trainable = False

inputs = tf.keras.Input(shape=IMG_SIZE + (3,))
x = data_augmentation(inputs)
x = preprocess_input(x)
x = base_model(x, training=False)
x = tf.keras.layers.GlobalAveragePooling2D()(x)
x = tf.keras.layers.Dropout(0.3)(x)
outputs = tf.keras.layers.Dense(len(class_names), activation="softmax")(x)
model = tf.keras.Model(inputs, outputs)

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)
model.summary()

# --- Step 6: train -----------------------------------------------------------
history = model.fit(train_ds, validation_data=val_ds, epochs=EPOCHS)

final_val_acc = history.history["val_accuracy"][-1] * 100
print(f"\nFinal validation accuracy: {final_val_acc:.1f}%")

# --- Step 9: save the model (two formats) ------------------------------------
model.save(os.path.join(HERE, "crop_health_model.h5"))

converter = tf.lite.TFLiteConverter.from_keras_model(model)
tflite_model = converter.convert()
with open(os.path.join(HERE, "crop_health_model.tflite"), "wb") as f:
    f.write(tflite_model)

print("Saved: crop_health_model.h5, crop_health_model.tflite, labels.json")

# --- Step 10: quick sanity check on one image --------------------------------
import random

test_class = random.choice(class_names)
test_class_dir = os.path.join(DATA_DIR, test_class)
test_img_name = random.choice(os.listdir(test_class_dir))
test_img_path = os.path.join(test_class_dir, test_img_name)

img = tf.keras.utils.load_img(test_img_path, target_size=IMG_SIZE)
img_array = tf.keras.utils.img_to_array(img)
img_array = tf.expand_dims(img_array, 0)
predictions = model.predict(img_array)
predicted_class = class_names[np.argmax(predictions[0])]
confidence = np.max(predictions[0]) * 100
print(f"Sanity check - actual: {test_class}, predicted: {predicted_class} ({confidence:.1f}%)")
