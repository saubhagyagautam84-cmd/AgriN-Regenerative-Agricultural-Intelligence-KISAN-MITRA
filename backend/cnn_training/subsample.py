"""
One-off: subsample the full PlantVillage subset down to N images/class into
a separate folder, so training has far fewer steps/epoch. This machine's
8GB RAM struggles with the full ~11k-image set (see train.py / train_lowmem.py
docstrings for the memory-pressure story) - transfer learning with a frozen
MobileNetV2 base converges to >90% val_accuracy within 1-2 epochs regardless
of dataset size in the thousands, so trading dataset size for a fast, stable
run is a reasonable call here.
"""

import os
import random
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "PlantVillage-Dataset", "raw", "color")
DST = os.path.join(HERE, "subset_small")
PER_CLASS = 300

random.seed(42)

if os.path.exists(DST):
    shutil.rmtree(DST)
os.makedirs(DST)

for class_name in os.listdir(SRC):
    src_class_dir = os.path.join(SRC, class_name)
    if not os.path.isdir(src_class_dir):
        continue
    images = os.listdir(src_class_dir)
    chosen = random.sample(images, min(PER_CLASS, len(images)))
    dst_class_dir = os.path.join(DST, class_name)
    os.makedirs(dst_class_dir, exist_ok=True)
    for img_name in chosen:
        shutil.copyfile(os.path.join(src_class_dir, img_name), os.path.join(dst_class_dir, img_name))
    print(f"{class_name}: {len(chosen)} images")

print("Done. Subsampled dataset at:", DST)
