from __future__ import annotations

import os
import glob
import subprocess
import shutil
import tempfile
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
import folder_paths


class ConcatenateVideosFromDirectory(io.ComfyNode):
    """
    Concatenates video files from a directory based on glob pattern.
    Saves the result to ComfyUI output directory with numbered filename.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ConcatenateVideosFromDirectory",
            display_name="Concatenate Videos From Directory",
            category="video/processing",
            description="Combine videos from directory by glob pattern, save with numbered output",
            inputs=[
                io.String.Input(
                    "directory_path",
                    default="",
                    tooltip="Absolute path to directory containing videos"
                ),
                io.String.Input(
                    "glob_pattern",
                    default="*-audio.mp4",
                    tooltip="Glob pattern to match video files (e.g., *.mp4, *-audio.mp4)"
                ),
                io.String.Input(
                    "output_prefix",
                    default="concatenated",
                    tooltip="Output prefix (supports subdirs: 'vace/vid' or just 'vid')"
                ),
            ],
            outputs=[
                io.String.Output(
                    "output_path",
                    tooltip="Absolute path to the concatenated video file"
                ),
            ],
            is_output_node=True,
        )

    @classmethod
    def get_ffmpeg_path(cls):
        """Get ffmpeg binary path"""
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg

        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass

        raise RuntimeError("ffmpeg not found")

    @classmethod
    def get_next_counter(cls, output_dir: str, prefix: str) -> int:
        """Find the next available counter for the output filename"""
        # Look for existing files matching the pattern
        pattern = os.path.join(output_dir, f"{prefix}_*.mp4")
        existing_files = glob.glob(pattern)

        if not existing_files:
            return 1

        # Extract counters from existing files
        counters = []
        for filepath in existing_files:
            basename = os.path.basename(filepath)
            # Remove prefix and extension
            try:
                counter_part = basename[len(prefix)+1:-4]  # +1 for underscore, -4 for .mp4
                counter = int(counter_part)
                counters.append(counter)
            except (ValueError, IndexError):
                continue

        return max(counters) + 1 if counters else 1

    @classmethod
    def execute(cls, directory_path: str, glob_pattern: str, output_prefix: str) -> io.NodeOutput:
        # Create input directory if it doesn't exist
        os.makedirs(directory_path, exist_ok=True)

        if not os.path.isdir(directory_path):
            raise ValueError(f"Path is not a directory: {directory_path}")

        # Find matching video files
        search_pattern = os.path.join(directory_path, glob_pattern)
        video_files = sorted(glob.glob(search_pattern))

        if not video_files:
            raise ValueError(f"No videos found matching pattern: {glob_pattern} in {directory_path}")

        print(f"Found {len(video_files)} videos to concatenate:")
        for i, vf in enumerate(video_files):
            print(f"  {i}: {os.path.basename(vf)}")

        # Get ffmpeg path
        try:
            ffmpeg_path = cls.get_ffmpeg_path()
        except RuntimeError as e:
            raise RuntimeError(f"FFmpeg not found: {e}")

        # Parse output prefix to handle subdirectories
        output_base = folder_paths.get_output_directory()

        # Split prefix into directory and filename parts
        prefix_parts = output_prefix.split('/')
        if len(prefix_parts) > 1:
            # Has subdirectory
            subdir = '/'.join(prefix_parts[:-1])
            filename_prefix = prefix_parts[-1]
            full_output_dir = os.path.join(output_base, subdir)
        else:
            # No subdirectory
            full_output_dir = output_base
            filename_prefix = output_prefix

        # Create output directory if needed
        os.makedirs(full_output_dir, exist_ok=True)

        # Get next counter
        counter = cls.get_next_counter(full_output_dir, filename_prefix)

        # Generate output filename
        output_filename = f"{filename_prefix}_{counter:04d}.mp4"
        output_path = os.path.join(full_output_dir, output_filename)

        # Create temporary concat file for ffmpeg
        temp_concat_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        try:
            # Write file list for ffmpeg concat demuxer
            for video_file in video_files:
                # Escape single quotes and write in ffmpeg concat format
                escaped_path = video_file.replace("'", "'\\''")
                temp_concat_file.write(f"file '{escaped_path}'\n")
            temp_concat_file.close()

            # Concatenate videos using ffmpeg concat demuxer
            cmd = [
                ffmpeg_path,
                "-f", "concat",
                "-safe", "0",
                "-i", temp_concat_file.name,
                "-c", "copy",  # Stream copy for fast concatenation
                "-y",
                output_path
            ]

            print(f"Concatenating {len(video_files)} videos...")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)

            print(f"✓ Saved concatenated video: {output_path}")
            print(f"  Output: {output_filename}")
            print(f"  Location: {full_output_dir}")

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg concatenation failed: {e.stderr}")
        finally:
            # Clean up temporary file
            if os.path.exists(temp_concat_file.name):
                os.unlink(temp_concat_file.name)

        return io.NodeOutput(output_path)


class ConcatenateVideosExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            ConcatenateVideosFromDirectory,
        ]
