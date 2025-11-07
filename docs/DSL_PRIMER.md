# Tri-ARC DSL Primer

This primer pairs each Phase 2 primitive and combinator with a worked example. The JSON fixtures under `fixtures/dsl/spec_examples/` mirror the examples below and are consumed by the automated DSL tests.

All grids are shown using zero-based colour ids. Region masks use `1` for cells included in the region and `0` otherwise.

## Grid Primitives

### identity - `fixtures/dsl/spec_examples/identity.json`

Identity leaves the grid unchanged.

**Program**
```
(pipeline
  (apply identity))
```
**Input grid**
```
[0, 1]
[2, 3]
```
**Output grid**
```
[0, 1]
[2, 3]
```


### rotate - `fixtures/dsl/spec_examples/rotate.json`

Rotate by one quarter turn clockwise.

**Program**
```
(pipeline
  (apply rotate 1))
```
**Input grid**
```
[1, 2]
[3, 4]
```
**Output grid**
```
[3, 1]
[4, 2]
```


### reflect - `fixtures/dsl/spec_examples/reflect.json`

Mirror across the vertical axis.

**Program**
```
(pipeline
  (apply reflect "vertical"))
```
**Input grid**
```
[1, 2, 3]
[4, 5, 6]
[7, 8, 9]
```
**Output grid**
```
[3, 2, 1]
[6, 5, 4]
[9, 8, 7]
```


### transpose - `fixtures/dsl/spec_examples/transpose.json`

Swap rows and columns for a rectangular grid.

**Program**
```
(pipeline
  (apply transpose))
```
**Input grid**
```
[1, 2, 3]
[4, 5, 6]
```
**Output grid**
```
[1, 4]
[2, 5]
[3, 6]
```


### replace_colour - `fixtures/dsl/spec_examples/replace_colour.json`

Replace colour 1 with colour 3 across the grid.

**Program**
```
(pipeline
  (apply replace_colour 1 3))
```
**Input grid**
```
[1, 1, 0]
[2, 1, 2]
[0, 1, 0]
```
**Output grid**
```
[3, 3, 0]
[2, 3, 2]
[0, 3, 0]
```


### flood_fill - `fixtures/dsl/spec_examples/flood_fill.json`

Flood fill from the top-left cell with colour 5.

**Program**
```
(pipeline
  (apply flood_fill (tuple 0 0) 5))
```
**Input grid**
```
[1, 1, 0]
[1, 0, 0]
[2, 2, 2]
```
**Output grid**
```
[5, 5, 0]
[5, 0, 0]
[2, 2, 2]
```


### paint_region - `fixtures/dsl/spec_examples/paint_region.json`

Fill the previously selected bounding box with colour 4.

**Program**
```
(pipeline
  (apply region_from_bbox 0 0 1 1)
  (apply paint_region @last_region 4))
```
**Input grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Output grid**
```
[4, 4, 0]
[4, 4, 0]
[0, 0, 0]
```


### extract_region - `fixtures/dsl/spec_examples/extract_region.json`

Crop the bounding box covering colour 2 cells.

**Program**
```
(pipeline
  (apply region_where_colour 2)
  (apply extract_region @last_region 0))
```
**Input grid**
```
[2, 2, 0]
[2, 0, 0]
[3, 3, 3]
```
**Output grid**
```
[2, 2]
[2, 0]
```

### trim_background - `fixtures/dsl/spec_examples/trim_background.json`

Automatically crop uniform padding by detecting the dominant background colour.

**Program**
```
(pipeline
  (apply trim_background))
```
**Input grid**
```
[0, 0, 0, 0, 0]
[0, 2, 2, 2, 0]
[0, 2, 2, 2, 0]
[0, 2, 2, 2, 0]
[0, 0, 0, 0, 0]
```
**Output grid**
```
[2, 2, 2]
[2, 2, 2]
[2, 2, 2]
```


### place - `fixtures/dsl/spec_examples/place.json`

Extract a patch and place it in the top-right corner.

**Program**
```
(pipeline
  (apply region_where_colour 2)
  (apply extract_region @last_region 0)
  (apply place @current_grid (tuple 0 2) "overwrite" @last_grid))
```
**Input grid**
```
[0, 0, 0, 0]
[0, 2, 2, 0]
[0, 2, 2, 0]
[0, 0, 0, 0]
```
**Output grid**
```
[0, 0, 2, 2]
[0, 2, 2, 2]
[0, 2, 2, 0]
[0, 0, 0, 0]
```


### map_cells - `fixtures/dsl/spec_examples/map_cells.json`

Recolour the ring of ones to colour 3 using a constant lambda.

**Program**
```
(pipeline
  (apply region_where_colour 1)
  (apply map_cells @last_region (lambda (cell) 3)))
```
**Input grid**
```
[0, 1, 0]
[1, 1, 1]
[0, 1, 0]
```
**Output grid**
```
[0, 3, 0]
[3, 3, 3]
[0, 3, 0]
```


## Region and Object Primitives

### region_all - `fixtures/dsl/spec_examples/region_all.json`

Create a region covering the entire grid.

**Program**
```
(pipeline
  (apply region_all))
```
**Input grid**
```
[0, 0]
[0, 0]
```
**Output grid**
```
[0, 0]
[0, 0]
```
**Region mask**
```
[1, 1]
[1, 1]
```


### region_where_colour - `fixtures/dsl/spec_examples/region_where_colour.json`

Select all cells with colour 1.

**Program**
```
(pipeline
  (apply region_where_colour 1))
```
**Input grid**
```
[1, 2, 1]
[2, 1, 0]
[0, 0, 1]
```
**Output grid**
```
[1, 2, 1]
[2, 1, 0]
[0, 0, 1]
```
**Region mask**
```
[1, 0, 1]
[0, 1, 0]
[0, 0, 1]
```


### region_from_bbox - `fixtures/dsl/spec_examples/region_from_bbox.json`

Create a rectangular region from coordinates.

**Program**
```
(pipeline
  (apply region_from_bbox 0 1 1 2))
```
**Input grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Output grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Region mask**
```
[0, 1, 1]
[0, 1, 1]
[0, 0, 0]
```


### region_outline - `fixtures/dsl/spec_examples/region_outline.json`

Take the perimeter of a previously created region mask.

**Program**
```
(pipeline
  (apply region_from_bbox 0 0 2 2)
  (apply region_outline @last_region))
```
**Region mask**
```
[1, 1, 1]
[1, 0, 1]
[1, 1, 1]
```


### region_expand - `fixtures/dsl/spec_examples/region_expand.json`

Dilate a region by one step using four-connectivity.

**Program**
```
(pipeline
  (apply region_where_colour 2)
  (apply region_expand @last_region 1))
```
**Input grid**
```
[0, 0, 0, 0]
[0, 2, 0, 0]
[0, 0, 0, 0]
[0, 0, 0, 0]
```
**Region mask**
```
[0, 1, 0, 0]
[1, 1, 1, 0]
[0, 1, 0, 0]
[0, 0, 0, 0]
```


### detect_objects - `fixtures/dsl/spec_examples/detect_objects.json`

Detect separate components for colour 2 and colour 3.

**Program**
```
(pipeline
  (apply detect_objects 4))
```
**Input grid**
```
[0, 2, 0, 0]
[0, 2, 0, 0]
[0, 0, 3, 3]
[0, 0, 3, 3]
```
**Output grid**
```
[0, 2, 0, 0]
[0, 2, 0, 0]
[0, 0, 3, 3]
[0, 0, 3, 3]
```
**Region 0 mask**
```
[0, 1, 0, 0]
[0, 1, 0, 0]
[0, 0, 0, 0]
[0, 0, 0, 0]
```
**Region 1 mask**
```
[0, 0, 0, 0]
[0, 0, 0, 0]
[0, 0, 1, 1]
[0, 0, 1, 1]
```


### select_object - `fixtures/dsl/spec_examples/select_object.json`

Select the largest object detected in the previous step.

**Program**
```
(pipeline
  (apply detect_objects 4)
  (apply select_object "largest"))
```
**Input grid**
```
[0, 2, 0, 0]
[0, 2, 0, 0]
[0, 0, 3, 3]
[0, 0, 3, 3]
```
**Output grid**
```
[0, 2, 0, 0]
[0, 2, 0, 0]
[0, 0, 3, 3]
[0, 0, 3, 3]
```
**Region mask**
```
[0, 0, 0, 0]
[0, 0, 0, 0]
[0, 0, 1, 1]
[0, 0, 1, 1]
```


### push_region - `fixtures/dsl/spec_examples/push_region.json`

Push a region onto the object stack.

**Program**
```
(pipeline
  (apply region_from_bbox 0 0 1 1)
  (apply push_region @last_region))
```
**Input grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Output grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Region 0 mask**
```
[1, 1, 0]
[1, 1, 0]
[0, 0, 0]
```
**Region 1 mask**
```
[1, 1, 0]
[1, 1, 0]
[0, 0, 0]
```
**Stack size after stage:** 2


### pop_region - `fixtures/dsl/spec_examples/pop_region.json`

Pop the most recently pushed region.

**Program**
```
(pipeline
  (apply region_from_bbox 0 0 1 1)
  (apply push_region @last_region)
  (apply pop_region))
```
**Input grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Output grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Region mask**
```
[1, 1, 0]
[1, 1, 0]
[0, 0, 0]
```
**Stack size after stage:** 1


### majority_colour - `fixtures/dsl/spec_examples/majority_colour.json`

Return the dominant colour inside a region.

**Program**
```
(pipeline
  (apply region_where_colour 1)
  (apply majority_colour @last_region))
```
**Input grid**
```
[1, 1, 2]
[1, 2, 2]
[1, 1, 2]
```
**Output grid**
```
[1, 1, 2]
[1, 2, 2]
[1, 1, 2]
```
**Scalar value:** 1


### count_cells - `fixtures/dsl/spec_examples/count_cells.json`

Count the number of cells inside a bounding box region.

**Program**
```
(pipeline
  (apply region_from_bbox 0 0 1 2)
  (apply count_cells @last_region))
```
**Input grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Output grid**
```
[0, 0, 0]
[0, 0, 0]
[0, 0, 0]
```
**Scalar value:** 6


## Combinators and Control

### compose - `fixtures/dsl/spec_examples/compose.json`

Run rotate then recolour via a compose block.

**Program**
```
(pipeline
  (apply compose
    (apply rotate 1)
    (apply replace_colour 1 3)))
```
**Input grid**
```
[1, 0]
[0, 1]
```
**Output grid**
```
[0, 3]
[3, 0]
```


### repeat - `fixtures/dsl/spec_examples/repeat.json`

Rotate twice by repeating the rotate primitive.

**Program**
```
(pipeline
  (apply repeat 2 (apply rotate 1)))
```
**Input grid**
```
[0, 1]
[2, 3]
```
**Output grid**
```
[3, 2]
[1, 0]
```


### if_equal - `fixtures/dsl/spec_examples/if_equal.json`

Recolour cells when the counted region size matches the target.

**Program**
```
(pipeline
  (apply region_where_colour 1)
  (apply count_cells @last_region)
  (apply if_equal @last_value 4 (apply replace_colour 1 3) (apply identity)))
```
**Input grid**
```
[1, 1, 0]
[0, 1, 0]
[0, 1, 0]
```
**Output grid**
```
[3, 3, 0]
[0, 3, 0]
[0, 3, 0]
```

