"""Color normalization for canonical relabeling of grids."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

from arc.symbolic.dsl.types import Grid
from arc.symbolic.search.types import TrainingExample


@dataclass(frozen=True)
class ColorMapping:
    """Represents a color mapping for normalization.
    
    Attributes:
        forward: Maps original colors to canonical colors
        backward: Maps canonical colors back to original colors
        canonical_order: The canonical ordering of colors
    """
    
    forward: Dict[int, int]
    backward: Dict[int, int]
    canonical_order: Tuple[int, ...]
    
    def invert(self) -> ColorMapping:
        """Invert the color mapping.
        
        Returns:
            A new ColorMapping with forward and backward swapped
        """
        return ColorMapping(
            forward=dict(self.backward),
            backward=dict(self.forward),
            canonical_order=self.canonical_order,
        )
    
    def compose(self, other: ColorMapping) -> ColorMapping:
        """Compose this mapping with another mapping.
        
        Args:
            other: Another ColorMapping to compose with
            
        Returns:
            A new ColorMapping representing self ∘ other
        """
        # Compose forward mappings: (self ∘ other)(x) = self(other(x))
        composed_forward = {}
        for orig_color in other.forward:
            intermediate = other.forward[orig_color]
            if intermediate in self.forward:
                composed_forward[orig_color] = self.forward[intermediate]
            else:
                composed_forward[orig_color] = intermediate
        
        # Compose backward mappings
        composed_backward = {}
        for canon_color in self.backward:
            intermediate = self.backward[canon_color]
            if intermediate in other.backward:
                composed_backward[canon_color] = other.backward[intermediate]
            else:
                composed_backward[canon_color] = intermediate
        
        return ColorMapping(
            forward=composed_forward,
            backward=composed_backward,
            canonical_order=self.canonical_order,
        )
    
    def apply_to_color(self, color: int) -> int:
        """Apply the mapping to a single color value.
        
        Args:
            color: The color to map
            
        Returns:
            The mapped color (or original if not in mapping)
        """
        return self.forward.get(color, color)
    
    def __repr__(self) -> str:
        return f"ColorMapping(forward={self.forward}, canonical_order={self.canonical_order})"


class ColorNormalizer:
    """Normalizes color labels in grids to canonical form.
    
    This class implements canonical relabeling strategies to reduce
    search space by treating color-permuted grids as equivalent.
    """
    
    def __init__(self, strategy: str = "frequency"):
        """Initialize the ColorNormalizer.
        
        Args:
            strategy: Normalization strategy to use:
                - "frequency": Order by frequency (most common first)
                - "appearance": Order by first appearance
                - "sorted": Simple sorted order
        """
        self.strategy = strategy
    
    def canonical_relabel(
        self,
        examples: List[TrainingExample]
    ) -> Tuple[List[TrainingExample], ColorMapping]:
        """Normalize examples to canonical color labels.
        
        Args:
            examples: List of training examples to normalize
            
        Returns:
            Tuple of (normalized_examples, color_mapping)
        """
        if not examples:
            return [], ColorMapping(forward={}, backward={}, canonical_order=())
        
        # Collect all colors from all examples
        all_colors = set()
        for example in examples:
            all_colors.update(np.unique(example.input_grid.data))
            all_colors.update(np.unique(example.output_grid.data))
        
        # Compute canonical ordering based on strategy
        if self.strategy == "frequency":
            mapping = self._compute_frequency_mapping(examples, all_colors)
        elif self.strategy == "appearance":
            mapping = self._compute_appearance_mapping(examples, all_colors)
        else:  # sorted
            mapping = self._compute_sorted_mapping(all_colors)
        
        # Apply mapping to all examples
        normalized_examples = []
        for example in examples:
            normalized_input = self.apply_mapping(example.input_grid, mapping)
            normalized_output = self.apply_mapping(example.output_grid, mapping)
            normalized_examples.append(
                TrainingExample(
                    input_grid=normalized_input,
                    output_grid=normalized_output,
                    metadata={**example.metadata, "color_mapping": mapping},
                )
            )
        
        return normalized_examples, mapping
    
    def compute_color_mapping(
        self,
        input_grid: Grid,
        output_grid: Grid
    ) -> ColorMapping:
        """Compute color mapping for a single input-output pair.
        
        Args:
            input_grid: Input grid
            output_grid: Output grid
            
        Returns:
            ColorMapping for this pair
        """
        # Collect colors from both grids
        all_colors = set()
        all_colors.update(np.unique(input_grid.data))
        all_colors.update(np.unique(output_grid.data))
        
        if self.strategy == "frequency":
            # Count frequencies in both grids
            color_counts = {}
            for color in all_colors:
                count_input = np.sum(input_grid.data == color)
                count_output = np.sum(output_grid.data == color)
                color_counts[color] = count_input + count_output
            
            # Sort by frequency (descending), then by color value
            sorted_colors = sorted(
                all_colors,
                key=lambda c: (-color_counts[c], c)
            )
        elif self.strategy == "appearance":
            # Order by first appearance in input, then output
            sorted_colors = []
            seen = set()
            
            # Scan input grid row by row
            for row in input_grid.data:
                for color in row:
                    if color not in seen:
                        sorted_colors.append(int(color))
                        seen.add(color)
            
            # Scan output grid for any remaining colors
            for row in output_grid.data:
                for color in row:
                    if color not in seen:
                        sorted_colors.append(int(color))
                        seen.add(color)
        else:  # sorted
            sorted_colors = sorted(all_colors)
        
        # Create mapping
        forward = {orig: canon for canon, orig in enumerate(sorted_colors)}
        backward = {canon: orig for orig, canon in forward.items()}
        
        return ColorMapping(
            forward=forward,
            backward=backward,
            canonical_order=tuple(sorted_colors),
        )
    
    def apply_mapping(
        self,
        grid: Grid,
        mapping: ColorMapping
    ) -> Grid:
        """Apply color mapping to a grid.
        
        Args:
            grid: Grid to transform
            mapping: ColorMapping to apply
            
        Returns:
            New grid with mapped colors
        """
        new_data = grid.data.copy()
        for orig_color, canon_color in mapping.forward.items():
            new_data[grid.data == orig_color] = canon_color
        return Grid(new_data)
    
    def _compute_frequency_mapping(
        self,
        examples: List[TrainingExample],
        all_colors: set
    ) -> ColorMapping:
        """Compute mapping based on color frequency."""
        # Count total occurrences of each color
        color_counts = {color: 0 for color in all_colors}
        for example in examples:
            for color in all_colors:
                color_counts[color] += np.sum(example.input_grid.data == color)
                color_counts[color] += np.sum(example.output_grid.data == color)
        
        # Sort by frequency (descending), then by color value
        sorted_colors = sorted(
            all_colors,
            key=lambda c: (-color_counts[c], c)
        )
        
        # Create mapping
        forward = {orig: canon for canon, orig in enumerate(sorted_colors)}
        backward = {canon: orig for orig, canon in forward.items()}
        
        return ColorMapping(
            forward=forward,
            backward=backward,
            canonical_order=tuple(sorted_colors),
        )
    
    def _compute_appearance_mapping(
        self,
        examples: List[TrainingExample],
        all_colors: set
    ) -> ColorMapping:
        """Compute mapping based on order of appearance."""
        sorted_colors = []
        seen = set()
        
        # Scan all examples in order
        for example in examples:
            # Scan input grid
            for row in example.input_grid.data:
                for color in row:
                    if color not in seen:
                        sorted_colors.append(int(color))
                        seen.add(color)
            
            # Scan output grid
            for row in example.output_grid.data:
                for color in row:
                    if color not in seen:
                        sorted_colors.append(int(color))
                        seen.add(color)
        
        # Add any remaining colors (shouldn't happen, but be safe)
        for color in sorted(all_colors - seen):
            sorted_colors.append(color)
        
        # Create mapping
        forward = {orig: canon for canon, orig in enumerate(sorted_colors)}
        backward = {canon: orig for orig, canon in forward.items()}
        
        return ColorMapping(
            forward=forward,
            backward=backward,
            canonical_order=tuple(sorted_colors),
        )
    
    def _compute_sorted_mapping(
        self,
        all_colors: set
    ) -> ColorMapping:
        """Compute simple sorted mapping."""
        sorted_colors = sorted(all_colors)
        
        # Create mapping
        forward = {orig: canon for canon, orig in enumerate(sorted_colors)}
        backward = {canon: orig for orig, canon in forward.items()}
        
        return ColorMapping(
            forward=forward,
            backward=backward,
            canonical_order=tuple(sorted_colors),
        )
