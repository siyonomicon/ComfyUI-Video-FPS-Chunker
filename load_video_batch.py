from __future__ import annotations

import os
import json
import glob
from pathlib import Path
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io, Input, InputImpl
import folder_paths


class VideoDatabase:
    """
    Simple JSON-based database to track video batch processing state.
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
                print(f"Error loading video batch database: {e}")
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
            print(f"Error saving video batch database: {e}")

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


# Initialize video batch database
VIDEO_BATCH_DB_PATH = os.path.join(
    folder_paths.get_output_directory(),
    "video_batch_state.json"
)
VIDEO_DB = VideoDatabase(VIDEO_BATCH_DB_PATH)

# Allowed video extensions
ALLOWED_VIDEO_EXT = ('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.mpg', '.mpeg')


class LoadVideoBatch(io.ComfyNode):
    """
    Load videos from a directory in incremental mode.
    Tracks which video was last processed and automatically moves to the next one.
    """

    def __init__(self):
        self.VDB = VIDEO_DB

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LoadVideoBatch",
            display_name="Load Video Batch",
            category="video/processing",
            description="Load videos incrementally from a directory, tracking progress",
            inputs=[
                io.String.Input(
                    "path",
                    default="",
                    tooltip="Directory path containing videos"
                ),
                io.String.Input(
                    "pattern",
                    default="*",
                    tooltip="Glob pattern to filter videos (e.g., *.mp4)"
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
                io.Video.Output(display_name="video"),
                io.String.Output(display_name="filename"),
                io.Int.Output(display_name="current_index"),
                io.Int.Output(display_name="total_videos"),
            ],
        )

    @classmethod
    def execute(cls, path: str, pattern: str, label: str, index: int) -> io.NodeOutput:
        if not os.path.exists(path):
            raise ValueError(f"Path does not exist: {path}")

        # Initialize batch loader
        loader = cls.BatchVideoLoader(path, label, pattern)

        if len(loader.video_paths) == 0:
            raise ValueError(f"No videos found in {path} with pattern {pattern}")

        # Get next video in incremental mode
        video_path, filename = loader.get_next_video()

        if video_path is None:
            raise ValueError("No valid video found")

        # Load video
        video = InputImpl.VideoFromFile(video_path)

        current_index = loader.index - 1  # -1 because get_next_video already incremented
        if current_index < 0:
            current_index = len(loader.video_paths) - 1

        total_videos = len(loader.video_paths)

        print(f"[LoadVideoBatch] {label} - Loaded: {filename} ({current_index + 1}/{total_videos})")

        return io.NodeOutput(video, filename, current_index, total_videos)

    class BatchVideoLoader:
        def __init__(self, directory_path: str, label: str, pattern: str):
            self.VDB = VIDEO_DB
            self.video_paths = []
            self.load_videos(directory_path, pattern)
            self.video_paths.sort()

            # Check if path or pattern changed
            stored_directory_path = self.VDB.get('Batch Paths', label)
            stored_pattern = self.VDB.get('Batch Patterns', label)

            if stored_directory_path != directory_path or stored_pattern != pattern:
                # Reset counter if path or pattern changed
                self.index = 0
                self.VDB.insert('Batch Counters', label, 0)
                self.VDB.insert('Batch Paths', label, directory_path)
                self.VDB.insert('Batch Patterns', label, pattern)
                print(f"[LoadVideoBatch] {label} - Path or pattern changed, resetting counter")
            else:
                # Load existing counter
                self.index = self.VDB.get('Batch Counters', label, 0)

            self.label = label

        def load_videos(self, directory_path: str, pattern: str):
            """Load all video files matching the pattern"""
            search_pattern = os.path.join(glob.escape(directory_path), pattern)
            for file_path in glob.glob(search_pattern, recursive=True):
                if file_path.lower().endswith(ALLOWED_VIDEO_EXT):
                    abs_file_path = os.path.abspath(file_path)
                    self.video_paths.append(abs_file_path)

        def get_video_by_id(self, video_id: int):
            """Get video by index"""
            if video_id < 0 or video_id >= len(self.video_paths):
                print(f"[LoadVideoBatch] Invalid video index: {video_id}")
                return (None, None)

            video_path = self.video_paths[video_id]
            filename = os.path.basename(video_path)
            return (video_path, filename)

        def get_next_video(self):
            """Get next video in incremental mode"""
            if self.index >= len(self.video_paths):
                self.index = 0

            video_path = self.video_paths[self.index]
            filename = os.path.basename(video_path)

            # Increment index for next time
            self.index += 1
            if self.index >= len(self.video_paths):
                self.index = 0

            # Save updated index
            self.VDB.insert('Batch Counters', self.label, self.index)

            return (video_path, filename)

    @classmethod
    def fingerprint_inputs(cls, path: str, pattern: str, label: str, index: int):
        """Return NaN to force re-execution each time (incremental mode)"""
        return float("NaN")


class LoadVideoBatchExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            LoadVideoBatch,
        ]
