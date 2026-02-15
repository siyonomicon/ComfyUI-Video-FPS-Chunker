from __future__ import annotations

import torch
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io, Input


class ImageBatchAccumulator(io.ComfyNode):
    """
    Accumulates image batches by concatenating them.
    Useful for collecting processed chunks into a single batch.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ImageBatchAccumulator",
            display_name="Image Batch Accumulator",
            category="image/batch",
            description="Accumulate image batches by concatenation",
            inputs=[
                io.Image.Input("current_batch", optional=True, tooltip="Current accumulated batch (empty on first iteration)"),
                io.Image.Input("new_batch", tooltip="New batch to add"),
                io.Boolean.Input("should_add", default=True, tooltip="Whether to add this batch"),
            ],
            outputs=[
                io.Image.Output(display_name="accumulated_batch"),
                io.Int.Output(display_name="total_frames"),
            ],
        )

    @classmethod
    def execute(cls, new_batch: Input.Image, should_add: bool, current_batch: Input.Image = None) -> io.NodeOutput:
        # If should_add is False, return current batch unchanged
        if not should_add:
            if current_batch is not None:
                total_frames = current_batch.shape[0]
                return io.NodeOutput(current_batch, total_frames)
            else:
                # No current batch and not adding, return empty
                return io.NodeOutput(new_batch[:0], 0)  # Empty batch with same shape

        # If no current batch, start with new batch
        if current_batch is None:
            total_frames = new_batch.shape[0]
            return io.NodeOutput(new_batch, total_frames)

        # Concatenate along batch dimension (dim 0)
        accumulated = torch.cat([current_batch, new_batch], dim=0)
        total_frames = accumulated.shape[0]

        print(f"Accumulated: {current_batch.shape[0]} + {new_batch.shape[0]} = {total_frames} frames")

        return io.NodeOutput(accumulated, total_frames)


class ConditionalImageBatchAccumulator(io.ComfyNode):
    """
    Accumulates image batches with index-based conditional logic.
    Useful for skipping specific chunks (e.g., skip index 0).
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ConditionalImageBatchAccumulator",
            display_name="Conditional Batch Accumulator",
            category="image/batch",
            description="Accumulate batches with index condition (e.g., skip index 0)",
            inputs=[
                io.Image.Input("current_batch", optional=True, tooltip="Current accumulated batch"),
                io.Image.Input("new_batch", tooltip="New batch to potentially add"),
                io.Int.Input("current_index", tooltip="Current chunk index"),
                io.Int.Input("skip_index", default=0, tooltip="Index to skip (default: 0)"),
            ],
            outputs=[
                io.Image.Output(display_name="accumulated_batch"),
                io.Int.Output(display_name="total_frames"),
                io.Int.Output(display_name="chunks_added"),
            ],
        )

    @classmethod
    def execute(cls, new_batch: Input.Image, current_index: int, skip_index: int = 0, current_batch: Input.Image = None) -> io.NodeOutput:
        # Check if we should skip this index
        should_skip = (current_index == skip_index)

        if should_skip:
            print(f"Skipping chunk at index {current_index}")
            if current_batch is not None:
                total_frames = current_batch.shape[0]
                # Count chunks by dividing by typical chunk size (approximate)
                chunks_added = total_frames // new_batch.shape[0] if new_batch.shape[0] > 0 else 0
                return io.NodeOutput(current_batch, total_frames, chunks_added)
            else:
                # Nothing accumulated yet and skipping this one
                return io.NodeOutput(new_batch[:0], 0, 0)  # Empty batch

        # Add this batch
        if current_batch is None:
            total_frames = new_batch.shape[0]
            chunks_added = 1
            print(f"Starting accumulation with chunk {current_index}: {total_frames} frames")
            return io.NodeOutput(new_batch, total_frames, chunks_added)

        # Concatenate
        accumulated = torch.cat([current_batch, new_batch], dim=0)
        total_frames = accumulated.shape[0]
        chunks_added = total_frames // new_batch.shape[0] if new_batch.shape[0] > 0 else 0

        print(f"Added chunk {current_index}: {current_batch.shape[0]} + {new_batch.shape[0]} = {total_frames} frames ({chunks_added} chunks)")

        return io.NodeOutput(accumulated, total_frames, chunks_added)


class ImageBatchAccumulatorExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            ImageBatchAccumulator,
            ConditionalImageBatchAccumulator,
        ]
