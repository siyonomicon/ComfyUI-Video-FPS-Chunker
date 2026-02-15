from __future__ import annotations

import subprocess
import tempfile
import os
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io, Input


class VideoInfo(io.ComfyNode):
    """
    Get metadata information from a video file.
    Returns FPS, resolution, duration, total frames, and codec.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="VideoInfo",
            display_name="Video Info",
            category="video/processing",
            description="Get video metadata (FPS, resolution, duration, frames, codec)",
            inputs=[
                io.Video.Input("video", tooltip="Video to analyze"),
            ],
            outputs=[
                io.Float.Output(display_name="fps"),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
                io.Float.Output(display_name="duration"),
                io.Int.Output(display_name="total_frames"),
                io.String.Output(display_name="codec"),
            ],
        )

    @classmethod
    def get_ffmpeg_path(cls):
        """Get ffmpeg binary path"""
        import shutil
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
    def execute(cls, video: Input.Video) -> io.NodeOutput:
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
            ffmpeg_path = cls.get_ffmpeg_path()
            ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")

            # Get video stream info
            cmd = [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-count_frames",
                "-show_entries", "stream=r_frame_rate,width,height,codec_name,nb_read_frames,duration",
                "-of", "json",
                video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            import json
            data = json.loads(result.stdout)
            stream = data["streams"][0]

            # Parse FPS
            fps_str = stream["r_frame_rate"]
            if '/' in fps_str:
                num, den = map(int, fps_str.split('/'))
                fps = num / den
            else:
                fps = float(fps_str)

            # Get dimensions
            width = int(stream["width"])
            height = int(stream["height"])

            # Get codec
            codec = stream.get("codec_name", "unknown")

            # Get total frames
            total_frames = int(stream.get("nb_read_frames", 0))

            # Get duration
            duration = float(stream.get("duration", 0))
            if duration == 0 and total_frames > 0 and fps > 0:
                duration = total_frames / fps

            print(f"Video Info: {width}x{height} @ {fps:.2f} FPS, {total_frames} frames, {duration:.2f}s, codec: {codec}")

            return io.NodeOutput(fps, width, height, duration, total_frames, codec)

        finally:
            # Clean up temporary video if created
            if cleanup_temp and temp_video_path and os.path.exists(temp_video_path):
                os.remove(temp_video_path)
                os.rmdir(os.path.dirname(temp_video_path))


class VideoInfoExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            VideoInfo,
        ]
