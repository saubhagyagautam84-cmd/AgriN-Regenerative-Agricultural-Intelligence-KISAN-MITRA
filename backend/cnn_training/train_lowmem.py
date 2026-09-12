"""
Low-memory fallback variant of train.py, for this machine's ~8GB RAM (of
which very little is free once TensorFlow, the OS and everything else in
the background is running).

Differences from train.py:
  * No `.cache()` on the datasets - re-decodes images from disk each epoch
    instead of holding the whole dataset as tensors in RAM. Slower per
    epoch, but avoids the memory growth that caused thrashing.
  * BATCH_SIZE lowered 32 -> 16 - halves peak activation memory.
  * ModelCheckpoint callback saves the best model after every epoch, so a
    crash partway through does not lose everything already learned.
  * EarlyStopping so a plateau doesn't waste time once memory is tight.

Run from backend/cnn_training/:
    .venv\\Scripts\\python.exe train_lowmem.py
"""

from __future__ import annotations

import json
import os

import numpy as np
import tensorflow as tf

print("TensorFlow version:", tf.__version__)

HERE = os.path.dirname(os.path.abspath(__file__))
# Subsampled to 300 images/class (see subsample.py) - this 8GB-RAM machine
# thrashed badly on the full ~11k-image set; the first (uncheckpointed) run
# already proved val_accuracy plateaus at ~95.5% within 1-2 epochs regardless,
# so trading dataset size for a fast, stable run is the right call here.
DATA_DIR = os.path.join(HERE, "subset_small")
IMG_SIZE = (224, 224)
BATCH_SIZE = 16
EPOCHS = 5
CHECKPOINT_PATH = os.path.join(HERE, "crop_health_model.h5")

train_ds = tf.keras.utils.image_dataset_from_directory(
    DATA_DIR, validation_split=0.2, subset="training", seed=42, image_size=IMG_SIZE, batch_size=BATCH_SIZE
)
val_ds = tf.keras.utils.image_dataset_from_directory(
    DATA_DIR, validation_split=0.2, subset="validation", seed=42, image_size=IMG_SIZE, batch_size=BATCH_SIZE
)

class_names = train_ds.class_names
print("Training on", len(class_names), "classes:", class_names)
with open(os.path.join(HERE, "labels.json"), "w") as f:
    json.dump(class_names, f, indent=2)

# No .cache() here on purpose - see module docstring.
AUTOTUNE = tf.data.AUTOTUNE
train_ds = train_ds.prefetch(buffer_size=1)
val_ds = val_ds.prefetch(buffer_size=1)

data_augmentation = tf.keras.Sequential(
    [tf.keras.layers.RandomFlip("horizontal"), tf.keras.layers.RandomRotation(0.1), tf.keras.layers.RandomZoom(0.1)]
)
preprocess_input = tf.keras.applications.mobilenet_v2.preprocess_input
base_model = tf.keras.applications.MobileNetV2(input_shape=IMG_SIZE + (3,), include_top=False, weights="imagenet")
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

callbacks = [
    tf.keras.callbacks.ModelCheckpoint(CHECKPOINT_PATH, monitor="val_accuracy", save_best_only=True, verbose=1),
    tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=3, restore_best_weights=True),
]

history = model.fit(train_ds, validation_data=val_ds, epochs=EPOCHS, callbacks=callbacks)

final_val_acc = max(history.history["val_accuracy"]) * 100
print(f"\nBest validation accuracy: {final_val_acc:.1f}% (checkpoint already saved to {CHECKPOINT_PATH})")

converter = tf.lite.TFLiteConverter.from_keras_model(model)
tflite_model = converter.convert()
with open(os.path.join(HERE, "crop_health_model.tflite"), "wb") as f:
    f.write(tflite_model)
print("Saved: crop_health_model.tflite, labels.json (crop_health_model.h5 saved via checkpoint)")
