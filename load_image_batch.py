from __future__ import annotations

import os
import json
import glob
from pathlib import Path
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io, Input, InputImpl
import folder_paths


class ImageDatabase:
    """
    Simple JSON-based database to track image batch processing state.
    Stores counters, paths, and patterns per label.
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.data = {}
        self.load()

    def load(self):
        """Load database from JSON file"""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"Error loading image batch database: {e}")
                self.data = {}
        else:
            self.data = {}

    def save(self):
        """Save database to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"Error saving image batch database: {e}")

    def get(self, category: str, key: str, default=None):
        """Get value from database"""
        if category not in self.data:
            return default
        return self.data[category].get(key, default)

    def insert(self, category: str, key: str, value):
        """Insert or update value in database"""
        if category not in self.data:
            self.data[category] = {}
        self.data[category][key] = value
        self.save()

    def category_exists(self, category: str) -> bool:
        """Check if category exists"""
        return category in self.data

    def key_exists(self, category: str, key: str) -> bool:
        """Check if key exists in category"""
        return category in self.data and key in self.data[category]


# Initialize image batch database
IMAGE_BATCH_DB_PATH = os.path.join(
    folder_paths.get_output_directory(),
    "image_batch_state.json"
)
IMAGE_DB = ImageDatabase(IMAGE_BATCH_DB_PATH)

# Allowed image extensions
ALLOWED_IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif')


class LoadImageBatch(io.ComfyNode):
    """
    Load images from a directory in incremental mode.
    Tracks which image was last processed and automatically moves to the next one.
    """

    def __init__(self):
        self.IDB = IMAGE_DB

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LoadImageBatch",
            display_name="Load Image Batch",
            category="image/processing",
            description="Load images incrementally from a directory, tracking progress",
            inputs=[
                io.String.Input(
                    "path",
                    default="",
                    tooltip="Directory path containing images"
                ),
                io.String.Input(
                    "pattern",
                    default="*",
                    tooltip="Glob pattern to filter images (e.g., *.png)"
                ),
                io.String.Input(
                    "label",
                    default="Batch 001",
                    tooltip="Unique label to track this batch's progress"
                ),
                io.Int.Input(
                    "index",
                    default=0,
                    min=0,
                    max=150000,
                    step=1,
                    tooltip="Manual index override (only used in manual mode)"
                ),
            ],
            outputs=[
                io.Image.Output(display_name="image"),
                io.String.Output(display_name="filename"),
                io.Int.Output(display_name="current_index"),
                io.Int.Output(display_name="total_images"),
            ],
        )

    @classmethod
    def execute(cls, path: str, pattern: str, label: str, index: int) -> io.NodeOutput:
        if not os.path.exists(path):
            raise ValueError(f"Path does not exist: {path}")

        # Initialize batch loader
        loader = cls.BatchImageLoader(path, label, pattern)

        if len(loader.image_paths) == 0:
            raise ValueError(f"No images found in {path} with pattern {pattern}")

        # Get next image in incremental mode
        image_path, filename = loader.get_next_image()

        if image_path is None:
            raise ValueError("No valid image found")

        # Load image
        image = InputImpl.ImageFromFile(image_path)

        current_index = loader.index - 1  # -1 because get_next_image already incremented
        if current_index < 0:
            current_index = len(loader.image_paths) - 1

        total_images = len(loader.image_paths)

        print(f"[LoadImageBatch] {label} - Loaded: {filename} ({current_index + 1}/{total_images})")

        return io.NodeOutput(image, filename, current_index, total_images)

    class BatchImageLoader:
        def __init__(self, directory_path: str, label: str, pattern: str):
            self.IDB = IMAGE_DB
            self.image_paths = []
            self.load_images(directory_path, pattern)
            self.image_paths.sort()

            # Check if path or pattern changed
            stored_directory_path = self.IDB.get('Batch Paths', label)
            stored_pattern = self.IDB.get('Batch Patterns', label)

            if stored_directory_path != directory_path or stored_pattern != pattern:
                # Reset counter if path or pattern changed
                self.index = 0
                self.IDB.insert('Batch Counters', label, 0)
                self.IDB.insert('Batch Paths', label, directory_path)
                self.IDB.insert('Batch Patterns', label, pattern)
                print(f"[LoadImageBatch] {label} - Path or pattern changed, resetting counter")
            else:
                # Load existing counter
                self.index = self.IDB.get('Batch Counters', label, 0)

            self.label = label

        def load_images(self, directory_path: str, pattern: str):
            """Load all image files matching the pattern"""
            search_pattern = os.path.join(glob.escape(directory_path), pattern)
            for file_path in glob.glob(search_pattern, recursive=True):
                if file_path.lower().endswith(ALLOWED_IMAGE_EXT):
                    abs_file_path = os.path.abspath(file_path)
                    self.image_paths.append(abs_file_path)

        def get_image_by_id(self, image_id: int):
            """Get image by index"""
            if image_id < 0 or image_id >= len(self.image_paths):
                print(f"[LoadImageBatch] Invalid image index: {image_id}")
                return (None, None)

            image_path = self.image_paths[image_id]
            filename = os.path.basename(image_path)
            return (image_path, filename)

        def get_next_image(self):
            """Get next image in incremental mode"""
            if self.index >= len(self.image_paths):
                self.index = 0

            image_path = self.image_paths[self.index]
            filename = os.path.basename(image_path)

            # Increment index for next time
            self.index += 1
            if self.index >= len(self.image_paths):
                self.index = 0

            # Save updated index
            self.IDB.insert('Batch Counters', self.label, self.index)

            return (image_path, filename)

    @classmethod
    def fingerprint_inputs(cls, path: str, pattern: str, label: str, index: int):
        """Return NaN to force re-execution each time (incremental mode)"""
        return float("NaN")


class LoadImageBatchExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            LoadImageBatch,
        ]
