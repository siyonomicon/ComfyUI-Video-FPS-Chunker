from .video_fps_chunker import VideoFPSChunkerExtension
from .load_video_batch import LoadVideoBatchExtension
from .load_image_batch import LoadImageBatchExtension
from .check_video_processed import CheckVideoProcessedExtension
from .video_info import VideoInfoExtension
from .image_batch_accumulator import ImageBatchAccumulatorExtension
from .concatenate_videos import ConcatenateVideosExtension
from comfy_api.latest import ComfyExtension, io
from typing_extensions import override


class VideoProcessingExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        chunker_ext = VideoFPSChunkerExtension()
        batch_ext = LoadVideoBatchExtension()
        image_batch_ext = LoadImageBatchExtension()
        check_ext = CheckVideoProcessedExtension()
        info_ext = VideoInfoExtension()
        accumulator_ext = ImageBatchAccumulatorExtension()
        concat_ext = ConcatenateVideosExtension()

        chunker_nodes = await chunker_ext.get_node_list()
        batch_nodes = await batch_ext.get_node_list()
        image_batch_nodes = await image_batch_ext.get_node_list()
        check_nodes = await check_ext.get_node_list()
        info_nodes = await info_ext.get_node_list()
        accumulator_nodes = await accumulator_ext.get_node_list()
        concat_nodes = await concat_ext.get_node_list()

        return chunker_nodes + batch_nodes + image_batch_nodes + check_nodes + info_nodes + accumulator_nodes + concat_nodes


async def comfy_entrypoint() -> VideoProcessingExtension:
    return VideoProcessingExtension()
