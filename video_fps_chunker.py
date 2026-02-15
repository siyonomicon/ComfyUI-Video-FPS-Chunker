from __future__ import annotations

import os
import hashlib
import subprocess
import shutil
import tempfile
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io, Input
import folder_paths


class VideoFPSChunker(io.ComfyNode):
    """
    Reduces video FPS to 16 by stretching duration (no frame loss),
    then splits into configurable frame chunks saved as separate MP4 files.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="VideoFPSChunker",
            display_name="Video FPS Chunker",
            category="video/processing",
            description="Reduce FPS to 16 (stretch duration) and split into chunks",
            inputs=[
                io.Video.Input("video", tooltip="The video to process"),
                io.String.Input(
                    "output_dir",
                    default="video_chunks",
                    tooltip="Base output directory name"
                ),
                io.Int.Input(
                    "frames_per_chunk",
                    default=77,
                    min=1,
                    max=10000,
                    step=1,
                    tooltip="Number of frames per chunk"
                ),
            ],
            outputs=[
                io.String.Output(display_name="chunk_dir_path"),
            ],
        )

    @classmethod
    def get_ffmpeg_path(cls):
        """Get ffmpeg binary path, prefer system installation over imageio-ffmpeg"""
        # Try system ffmpeg first
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            return system_ffmpeg

        # Try imageio-ffmpeg
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass

        raise RuntimeError("ffmpeg not found. Install ffmpeg or imageio-ffmpeg package.")

    @classmethod
    def calculate_video_hash(cls, video_path: str) -> str:
        """Calculate SHA256 hash of video file"""
        sha256_hash = hashlib.sha256()
        with open(video_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()[:16]  # Use first 16 chars for shorter names

    @classmethod
    def get_video_fps(cls, ffmpeg_path: str, video_path: str) -> float:
        """Get video FPS using ffprobe"""
        ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")

        cmd = [
            ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        fps_str = result.stdout.strip()

        # Parse frame rate
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = num / den
        else:
            fps = float(fps_str)

        return fps

    @classmethod
    def execute(cls, video: Input.Video, output_dir: str, frames_per_chunk: int) -> io.NodeOutput:
        # Get video source
        video_source = video.get_stream_source()

        # Handle both file path and BytesIO
        temp_video_path = None
        cleanup_temp = False

        if isinstance(video_source, str):
            video_path = video_source
        else:
            # BytesIO - save to temporary file
            temp_dir = tempfile.mkdtemp()
            temp_video_path = os.path.join(temp_dir, "input_video.mp4")
            with open(temp_video_path, "wb") as f:
                video_source.seek(0)
                f.write(video_source.read())
            video_path = temp_video_path
            cleanup_temp = True

        try:
            # Get ffmpeg path
            try:
                ffmpeg_path = cls.get_ffmpeg_path()
            except RuntimeError as e:
                raise RuntimeError(f"FFmpeg not found: {e}")

            # Calculate video hash
            video_hash = cls.calculate_video_hash(video_path)

            # Get original FPS
            try:
                original_fps = cls.get_video_fps(ffmpeg_path, video_path)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to get video FPS: {e.stderr}")

            if original_fps <= 0:
                raise ValueError(f"Invalid FPS detected: {original_fps}")

            # Calculate PTS multiplier to stretch duration
            target_fps = 16
            pts_multiplier = original_fps / target_fps

            # Create output directory structure
            output_base = folder_paths.get_output_directory()
            chunk_base_dir = os.path.join(output_base, output_dir, video_hash)
            os.makedirs(chunk_base_dir, exist_ok=True)

            # Step 1: Convert to 16 FPS by stretching duration
            temp_stretched = os.path.join(chunk_base_dir, "_temp_stretched.mp4")

            cmd_stretch = [
                ffmpeg_path,
                "-i", video_path,
                "-vf", f"setpts={pts_multiplier}*PTS",
                "-r", "16",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-an",  # Remove audio
                "-y",
                temp_stretched
            ]

            try:
                result = subprocess.run(cmd_stretch, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to stretch video to 16 FPS: {e.stderr}")

            # Step 2: Split into chunks using segment muxer
            chunk_pattern = os.path.join(chunk_base_dir, "%d.mp4")

            cmd_chunk = [
                ffmpeg_path,
                "-i", temp_stretched,
                "-c:v", "copy",  # Copy codec for speed
                "-f", "segment",
                "-segment_frames", str(frames_per_chunk),
                "-reset_timestamps", "1",
                "-y",
                chunk_pattern
            ]

            try:
                result = subprocess.run(cmd_chunk, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to split video into chunks: {e.stderr}")

            # Clean up temporary stretched video
            if os.path.exists(temp_stretched):
                os.remove(temp_stretched)

            # Verify chunks were created
            chunks = sorted([f for f in os.listdir(chunk_base_dir) if f.endswith('.mp4')])
            if not chunks:
                raise RuntimeError("No chunks were created. Video might be too short or invalid.")

            # Return absolute path to chunk directory
            chunk_dir_realpath = os.path.realpath(chunk_base_dir)

            print(f"Video processed successfully: {len(chunks)} chunks ({frames_per_chunk} frames each) created in {chunk_dir_realpath}")

            return io.NodeOutput(chunk_dir_realpath)

        finally:
            # Clean up temporary video if created
            if cleanup_temp and temp_video_path and os.path.exists(temp_video_path):
                os.remove(temp_video_path)
                os.rmdir(os.path.dirname(temp_video_path))


class VideoFPSChunkerExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            VideoFPSChunker,
        ]
