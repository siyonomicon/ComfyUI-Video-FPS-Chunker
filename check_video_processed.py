from __future__ import annotations

import os
import json
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
import folder_paths


class ProcessedVideosDB:
    """
    Simple JSON database to track which videos have been processed.
    Stores video hash -> chunk directory mapping.
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
                print(f"Error loading processed videos database: {e}")
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
            print(f"Error saving processed videos database: {e}")

    def is_processed(self, video_hash: str) -> bool:
        """Check if video has been processed"""
        return video_hash in self.data

    def get_chunk_dir(self, video_hash: str) -> str | None:
        """Get chunk directory for processed video"""
        return self.data.get(video_hash)

    def mark_processed(self, video_hash: str, chunk_dir: str):
        """Mark video as processed with its chunk directory"""
        self.data[video_hash] = chunk_dir
        self.save()


# Initialize processed videos database
PROCESSED_VIDEOS_DB_PATH = os.path.join(
    folder_paths.get_output_directory(),
    "processed_videos.json"
)
PROCESSED_DB = ProcessedVideosDB(PROCESSED_VIDEOS_DB_PATH)


class CheckVideoProcessed(io.ComfyNode):
    """
    Check if a video has already been processed (chunked).
    Returns the existing chunk directory if found, otherwise returns empty string.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="CheckVideoProcessed",
            display_name="Check Video Processed",
            category="video/processing",
            description="Check if video has already been chunked",
            inputs=[
                io.Video.Input("video", tooltip="Video to check"),
            ],
            outputs=[
                io.String.Output(display_name="chunk_dir_path"),
                io.Boolean.Output(display_name="is_processed"),
            ],
        )

    @classmethod
    def execute(cls, video: io.Video.Type) -> io.NodeOutput:
        import hashlib

        # Get video source
        video_source = video.get_stream_source()

        # Calculate video hash
        if isinstance(video_source, str):
            video_path = video_source
        else:
            # For BytesIO, we can't easily hash without reading
            # Return not processed
            return io.NodeOutput("", False)

        sha256_hash = hashlib.sha256()
        with open(video_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        video_hash = sha256_hash.hexdigest()[:16]

        # Check if processed
        if PROCESSED_DB.is_processed(video_hash):
            chunk_dir = PROCESSED_DB.get_chunk_dir(video_hash)

            # Verify chunk directory and files actually exist
            if os.path.exists(chunk_dir) and os.path.isdir(chunk_dir):
                # Check if there are any .mp4 files in the directory
                chunks = [f for f in os.listdir(chunk_dir) if f.endswith('.mp4')]
                if len(chunks) > 0:
                    print(f"Video already processed: {chunk_dir} ({len(chunks)} chunks found)")
                    return io.NodeOutput(chunk_dir, True)
                else:
                    print(f"Chunk directory exists but no chunks found: {chunk_dir}")
            else:
                print(f"Chunk directory no longer exists: {chunk_dir}")

            # Chunks don't exist - remove from database and return not processed
            print(f"Removing stale entry from database for hash: {video_hash}")
            if video_hash in PROCESSED_DB.data:
                del PROCESSED_DB.data[video_hash]
                PROCESSED_DB.save()

            return io.NodeOutput("", False)
        else:
            print(f"Video not yet processed (hash: {video_hash})")
            return io.NodeOutput("", False)


class CheckVideoProcessedExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            CheckVideoProcessed,
        ]
