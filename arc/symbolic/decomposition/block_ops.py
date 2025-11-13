"""Block-level operations library for composition.

This module provides primitives for concatenating, tiling, and composing
grid blocks with proper boundary protocols and alignment operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np

from arc.symbolic.dsl.types import Grid


class Alignment(Enum):
    """Alignment options for block composition."""
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    CENTER_LEFT = "center_left"
    CENTER = "center"
    CENTER_RIGHT = "center_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"


class Direction(Enum):
    """Direction for concatenation."""
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


@dataclass
class BoundaryProtocol:
    """Protocol for handling boundaries during composition.
    
    Attributes:
        padding: Number of cells to pad between blocks
        fill_color: Color to use for padding
        merge_adjacent: Whether to merge adjacent cells of same color
    """
    padding: int = 0
    fill_color: int = 0
    merge_adjacent: bool = False


class BlockOperations:
    """Library of block-level operations for grid composition.
    
    This class provides primitives for:
    - Concatenating grids horizontally or vertically
    - Tiling grids in patterns
    - Aligning and spacing blocks
    - Handling boundaries during composition
    
    Requirements: 9.5
    """
    
    @staticmethod
    def concatenate(
        blocks: List[Grid],
        direction: Direction = Direction.HORIZONTAL,
        boundary: Optional[BoundaryProtocol] = None
    ) -> Grid:
        """Concatenate multiple grids in a specified direction.
        
        Args:
            blocks: List of grids to concatenate
            direction: Direction of concatenation (horizontal or vertical)
            boundary: Boundary protocol for handling spacing
            
        Returns:
            Concatenated grid
            
        Requirements: 9.5
        """
        if not blocks:
            return Grid(np.array([[0]], dtype=np.int16))
        
        if len(blocks) == 1:
            return blocks[0]
        
        boundary = boundary or BoundaryProtocol()
        
        if direction == Direction.HORIZONTAL:
            return BlockOperations._concatenate_horizontal(blocks, boundary)
        else:
            return BlockOperations._concatenate_vertical(blocks, boundary)
    
    @staticmethod
    def _concatenate_horizontal(
        blocks: List[Grid],
        boundary: BoundaryProtocol
    ) -> Grid:
        """Concatenate grids horizontally."""
        # Find maximum height
        max_height = max(grid.shape[0] for grid in blocks)
        
        # Calculate total width
        total_width = sum(grid.shape[1] for grid in blocks)
        if boundary.padding > 0:
            total_width += boundary.padding * (len(blocks) - 1)
        
        # Create result array
        result = np.full((max_height, total_width), boundary.fill_color, dtype=np.int16)
        
        # Place each block
        col_offset = 0
        for i, grid in enumerate(blocks):
            h, w = grid.shape
            # Center vertically if needed
            row_offset = (max_height - h) // 2
            result[row_offset:row_offset + h, col_offset:col_offset + w] = grid.data
            col_offset += w
            if i < len(blocks) - 1:
                col_offset += boundary.padding
        
        return Grid(result)
    
    @staticmethod
    def _concatenate_vertical(
        blocks: List[Grid],
        boundary: BoundaryProtocol
    ) -> Grid:
        """Concatenate grids vertically."""
        # Find maximum width
        max_width = max(grid.shape[1] for grid in blocks)
        
        # Calculate total height
        total_height = sum(grid.shape[0] for grid in blocks)
        if boundary.padding > 0:
            total_height += boundary.padding * (len(blocks) - 1)
        
        # Create result array
        result = np.full((total_height, max_width), boundary.fill_color, dtype=np.int16)
        
        # Place each block
        row_offset = 0
        for i, grid in enumerate(blocks):
            h, w = grid.shape
            # Center horizontally if needed
            col_offset = (max_width - w) // 2
            result[row_offset:row_offset + h, col_offset:col_offset + w] = grid.data
            row_offset += h
            if i < len(blocks) - 1:
                row_offset += boundary.padding
        
        return Grid(result)
    
    @staticmethod
    def tile(
        block: Grid,
        rows: int,
        cols: int,
        boundary: Optional[BoundaryProtocol] = None
    ) -> Grid:
        """Tile a grid in a rows x cols pattern.
        
        Args:
            block: The grid to tile
            rows: Number of rows in the tiling
            cols: Number of columns in the tiling
            boundary: Boundary protocol for spacing between tiles
            
        Returns:
            Tiled grid
            
        Requirements: 9.5
        """
        if rows <= 0 or cols <= 0:
            return Grid(np.array([[0]], dtype=np.int16))
        
        boundary = boundary or BoundaryProtocol()
        
        # Create rows of tiles
        tile_rows = []
        for _ in range(rows):
            row_blocks = [block] * cols
            tile_row = BlockOperations.concatenate(
                row_blocks,
                Direction.HORIZONTAL,
                boundary
            )
            tile_rows.append(tile_row)
        
        # Concatenate rows vertically
        return BlockOperations.concatenate(
            tile_rows,
            Direction.VERTICAL,
            boundary
        )
    
    @staticmethod
    def align(
        block: Grid,
        canvas_shape: Tuple[int, int],
        alignment: Alignment = Alignment.CENTER,
        fill_color: int = 0
    ) -> Grid:
        """Align a block within a larger canvas.
        
        Args:
            block: The grid to align
            canvas_shape: Shape of the target canvas (height, width)
            alignment: Alignment position
            fill_color: Color to fill empty space
            
        Returns:
            Aligned grid on canvas
            
        Requirements: 9.5
        """
        canvas_h, canvas_w = canvas_shape
        block_h, block_w = block.shape
        
        # Create canvas
        result = np.full((canvas_h, canvas_w), fill_color, dtype=np.int16)
        
        # Calculate position based on alignment
        if alignment == Alignment.TOP_LEFT:
            row, col = 0, 0
        elif alignment == Alignment.TOP_CENTER:
            row, col = 0, (canvas_w - block_w) // 2
        elif alignment == Alignment.TOP_RIGHT:
            row, col = 0, canvas_w - block_w
        elif alignment == Alignment.CENTER_LEFT:
            row, col = (canvas_h - block_h) // 2, 0
        elif alignment == Alignment.CENTER:
            row, col = (canvas_h - block_h) // 2, (canvas_w - block_w) // 2
        elif alignment == Alignment.CENTER_RIGHT:
            row, col = (canvas_h - block_h) // 2, canvas_w - block_w
        elif alignment == Alignment.BOTTOM_LEFT:
            row, col = canvas_h - block_h, 0
        elif alignment == Alignment.BOTTOM_CENTER:
            row, col = canvas_h - block_h, (canvas_w - block_w) // 2
        elif alignment == Alignment.BOTTOM_RIGHT:
            row, col = canvas_h - block_h, canvas_w - block_w
        else:
            row, col = 0, 0
        
        # Ensure block fits in canvas
        row = max(0, min(row, canvas_h - block_h))
        col = max(0, min(col, canvas_w - block_w))
        
        # Place block on canvas
        result[row:row + block_h, col:col + block_w] = block.data
        
        return Grid(result)
    
    @staticmethod
    def add_spacing(
        block: Grid,
        top: int = 0,
        bottom: int = 0,
        left: int = 0,
        right: int = 0,
        fill_color: int = 0
    ) -> Grid:
        """Add spacing around a block.
        
        Args:
            block: The grid to add spacing to
            top: Spacing to add at top
            bottom: Spacing to add at bottom
            left: Spacing to add at left
            right: Spacing to add at right
            fill_color: Color to use for spacing
            
        Returns:
            Grid with added spacing
            
        Requirements: 9.5
        """
        h, w = block.shape
        new_h = h + top + bottom
        new_w = w + left + right
        
        result = np.full((new_h, new_w), fill_color, dtype=np.int16)
        result[top:top + h, left:left + w] = block.data
        
        return Grid(result)
    
    @staticmethod
    def overlay(
        base: Grid,
        overlay: Grid,
        position: Tuple[int, int],
        transparent_color: Optional[int] = None
    ) -> Grid:
        """Overlay one grid on top of another.
        
        Args:
            base: The base grid
            overlay: The grid to overlay
            position: (row, col) position to place overlay
            transparent_color: Color to treat as transparent (not copied)
            
        Returns:
            Grid with overlay applied
            
        Requirements: 9.5
        """
        result = base.data.copy()
        row, col = position
        overlay_h, overlay_w = overlay.shape
        base_h, base_w = base.shape
        
        # Calculate valid region to copy
        src_row_start = max(0, -row)
        src_col_start = max(0, -col)
        src_row_end = min(overlay_h, base_h - row)
        src_col_end = min(overlay_w, base_w - col)
        
        dst_row_start = max(0, row)
        dst_col_start = max(0, col)
        dst_row_end = dst_row_start + (src_row_end - src_row_start)
        dst_col_end = dst_col_start + (src_col_end - src_col_start)
        
        # Copy overlay data
        overlay_data = overlay.data[src_row_start:src_row_end, src_col_start:src_col_end]
        
        if transparent_color is not None:
            # Only copy non-transparent pixels
            mask = overlay_data != transparent_color
            result[dst_row_start:dst_row_end, dst_col_start:dst_col_end][mask] = overlay_data[mask]
        else:
            # Copy all pixels
            result[dst_row_start:dst_row_end, dst_col_start:dst_col_end] = overlay_data
        
        return Grid(result)
