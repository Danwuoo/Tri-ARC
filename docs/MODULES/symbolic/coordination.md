# Module Coordination Infrastructure

This module provides coordination infrastructure for communication between the symbolic solver and other modules (TTT and LLM).

## Overview

The coordination module enables bidirectional information exchange:
- **From TTT/LLM to Symbolic**: Receive invariants, relations, sketches, and macros
- **From Symbolic to TTT/LLM**: Send failure feedback for learning and prompt adjustment

## Components

### Data Structures (`types.py`)

#### Invariant
Represents a constraint from TTT or other modules that should hold for valid programs.

```python
invariant = Invariant(
    type="color_conservation",
    constraint={"colors": [0, 1, 2]},
    confidence=0.9,
    source="ttt"
)
```

**Fields:**
- `type`: Type of invariant (e.g., "color_conservation", "object_count", "topology")
- `constraint`: The actual constraint specification
- `confidence`: Confidence score (0.0 to 1.0)
- `source`: Source module ("ttt", "symbolic", "llm")

#### Relation
Describes spatial or semantic relationships between objects.

```python
relation = Relation(
    relation_type="spatial",
    objects=[1, 2],
    parameters={"distance": 3, "direction": "horizontal"},
    confidence=0.95
)
```

**Fields:**
- `relation_type`: Type of relation ("spatial", "color", "size")
- `objects`: List of object IDs involved
- `parameters`: Additional parameters
- `confidence`: Confidence score (0.0 to 1.0)

#### DSLMacro
High-level DSL macro from LLM that can be expanded into concrete stages.

```python
macro = DSLMacro(
    name="rotate_and_reflect",
    parameters=["angle", "axis"],
    body=[
        Stage(operator="rotate", arguments=("angle",)),
        Stage(operator="reflect", arguments=("axis",))
    ],
    documentation="Rotates and reflects a grid",
    confidence=0.85
)
```

**Fields:**
- `name`: Name of the macro
- `parameters`: List of parameter names
- `body`: List of DSL stages
- `documentation`: Human-readable description
- `confidence`: Confidence score (0.0 to 1.0)

### Message Queue (`message_queue.py`)

Thread-safe message queue for asynchronous communication.

```python
queue = MessageQueue(max_size=1000)
queue.start()

# Send message
message = Message(
    type="ttt_invariants",
    task_id="task_001",
    payload={"invariants": [...]},
)
queue.put(message)

# Receive message
msg = queue.get(timeout=1.0)

# Register handler
def handle_invariants(msg: Message):
    print(f"Received invariants: {msg.payload}")

queue.register_handler("ttt_invariants", handle_invariants)
```

**Features:**
- Thread-safe operations
- Message filtering by type and task_id
- Handler registration for automatic routing
- Statistics tracking
- Optional logging to file

### TTT Coordinator (`ttt_coordinator.py`)

Manages communication with the Test-Time Training module.

```python
coordinator = TTTCoordinator(config)

# Receive invariants
invariants = [
    Invariant(type="color_conservation", constraint={}, confidence=0.9, source="ttt")
]
coordinator.receive_invariants("task_001", invariants)

# Receive relations
relations = [
    Relation(relation_type="spatial", objects=[1, 2], confidence=0.85)
]
coordinator.receive_candidate_relations("task_001", relations)

# Send failure feedback
coordinator.send_failure_feedback(
    "task_001",
    "search_exhausted",
    {"elapsed_s": 10.0, "expansions": 1000}
)

# Retrieve cached data
task_invariants = coordinator.get_invariants("task_001")
task_relations = coordinator.get_relations("task_001")
```

**Configuration:**
```yaml
coordination:
  ttt:
    enabled: true
    receive_invariants: true
    send_feedback: true
    log_messages: false
    message_log_file: "logs/coordination/ttt_messages.jsonl"
```

### LLM Coordinator (`llm_coordinator.py`)

Manages communication with the LLM module.

```python
coordinator = LLMCoordinator(config)

# Receive DSL macro
macro = DSLMacro(
    name="test_macro",
    parameters=["p1"],
    body=[Stage(operator="op1", arguments=())]
)
coordinator.receive_dsl_macro("task_001", macro)

# Receive program sketch
sketch = ProgramSketch(
    stages=[
        Stage(operator="op1", arguments=()),
        Hole(id="hole1", type="operator", domain={"op2", "op3"})
    ]
)
coordinator.receive_sketch("task_001", sketch)

# Verify LLM candidate (mandatory SMT check)
result = coordinator.verify_llm_candidate(program, examples)

# Send failure feedback
coordinator.send_failure_feedback(
    "task_001",
    "verification_failed",
    "Focus on generating programs that satisfy all examples"
)

# Retrieve cached data
task_macros = coordinator.get_macros("task_001")
task_sketches = coordinator.get_sketches("task_001")
```

**Configuration:**
```yaml
coordination:
  llm:
    enabled: true
    receive_macros: true
    verify_candidates: true
    send_feedback: true
    log_messages: false
    message_log_file: "logs/coordination/llm_messages.jsonl"
```

### Coordination Integration (`integration.py`)

Unified interface for both TTT and LLM coordination.

```python
integration = CoordinationIntegration(config)

# Get invariants from TTT
invariants = integration.get_invariants("task_001")

# Get relations from TTT
relations = integration.get_relations("task_001")

# Get macros from LLM
macros = integration.get_macros("task_001")

# Get sketches from LLM
sketches = integration.get_sketches("task_001")

# Send failure feedback to both modules
integration.send_failure_feedback(
    "task_001",
    "search_exhausted",
    {"elapsed_s": 10.0}
)

# Verify LLM candidate
result = integration.verify_llm_candidate(program, examples)

# Get statistics
stats = integration.get_stats()

# Cleanup
integration.shutdown()
```

**Configuration:**
```yaml
coordination:
  enabled: true
  log_messages: false
  message_log_file: "logs/coordination/messages.jsonl"
  
  ttt:
    enabled: true
    receive_invariants: true
    send_feedback: true
  
  llm:
    enabled: true
    receive_macros: true
    verify_candidates: true
    send_feedback: true
```

## Integration with Symbolic Solver

The coordination module is integrated into the symbolic solver through the `CoordinationIntegration` class.

### Initialization

In `SymbolicSolver.__init__`:

```python
# Initialize coordination integration (TTT and LLM)
coord_cfg = self.symbolic_cfg.get("coordination", {})
self.coordination_enabled = bool(coord_cfg.get("enabled", False))
if self.coordination_enabled:
    from arc.symbolic.coordination import CoordinationIntegration
    self.coordination = CoordinationIntegration(raw_config)
    LOGGER.info("Coordination integration initialized")
else:
    self.coordination = None
```

### Usage in Solve Method

In `SymbolicSolver.solve`:

```python
# Receive invariants and sketches from TTT/LLM modules
invariants = []
relations = []
sketches = []
macros = []
if self.coordination_enabled and self.coordination:
    invariants = self.coordination.get_invariants(task_id)
    relations = self.coordination.get_relations(task_id)
    sketches = self.coordination.get_sketches(task_id)
    macros = self.coordination.get_macros(task_id)
    
    if invariants:
        LOGGER.info(f"Received {len(invariants)} invariants from TTT")
    if sketches:
        LOGGER.info(f"Received {len(sketches)} sketches from LLM")

# ... synthesis process ...

# Send failure feedback if no solutions found
if self.coordination_enabled and self.coordination:
    if summary_status == "no_solution":
        self.coordination.send_failure_feedback(
            task_id,
            "search_exhausted",
            {"elapsed_s": elapsed_s, "expansions": budget.expansions}
        )
```

## Message Types

### From TTT to Symbolic
- `ttt_invariants`: Invariants to use as constraints
- `ttt_relations`: Candidate relations between objects

### From LLM to Symbolic
- `llm_macro`: DSL macro definition
- `llm_sketch`: Program sketch with holes

### From Symbolic to TTT/LLM
- `symbolic_failure`: Failure feedback with type and metadata
- `symbolic_failure_llm`: Failure feedback with prompt adjustment

## Usage Examples

### Example 1: Receiving Invariants from TTT

```python
# TTT module sends invariants
invariants = [
    Invariant(
        type="color_conservation",
        constraint={"input_colors": [0, 1, 2], "output_colors": [0, 1, 2]},
        confidence=0.95,
        source="ttt"
    ),
    Invariant(
        type="object_count",
        constraint={"min": 2, "max": 5},
        confidence=0.85,
        source="ttt"
    )
]

# Symbolic solver receives them
for inv in invariants:
    coordinator.receive_invariants(task_id, [inv])

# Use in synthesis
task_invariants = coordinator.get_invariants(task_id)
for inv in task_invariants:
    if inv.type == "color_conservation":
        # Apply color conservation constraint
        pass
```

### Example 2: Receiving Sketch from LLM

```python
# LLM module generates a sketch
sketch = ProgramSketch(
    stages=[
        Stage(operator="detect_objects", arguments=()),
        Hole(id="transform", type="operator", domain={"rotate", "reflect", "scale"}),
        Stage(operator="paint_region", arguments=("color",))
    ],
    constraints=[
        {"type": "hole_constraint", "hole_id": "transform", "constraint": "preserves_topology"}
    ]
)

# Symbolic solver receives it
coordinator.receive_sketch(task_id, sketch)

# Use in synthesis
task_sketches = coordinator.get_sketches(task_id)
for sketch in task_sketches:
    # Use sketch to guide synthesis
    pass
```

### Example 3: Sending Failure Feedback

```python
# Synthesis fails
if not candidates:
    # Send feedback to TTT
    ttt_coordinator.send_failure_feedback(
        task_id,
        "search_exhausted",
        {
            "elapsed_s": 10.0,
            "expansions": 1000,
            "max_depth_reached": True,
            "invariants_used": len(invariants)
        }
    )
    
    # Send feedback to LLM
    llm_coordinator.send_failure_feedback(
        task_id,
        "search_exhausted",
        "Try simpler program structures or different operator combinations"
    )
```

## Testing

Run the test suite:

```bash
pytest tests/symbolic/test_coordination.py -v
```

Test coverage includes:
- Data structure validation and serialization
- Message queue operations
- TTT coordinator functionality
- LLM coordinator functionality
- Coordination integration
- Handler registration and message routing

## Performance Considerations

### Message Queue
- Default max size: 1000 messages
- Non-blocking put/get operations available
- Background processing thread for handlers
- Configurable polling interval

### Caching
- Invariants and relations cached by task_id
- Macros and sketches cached by task_id
- Clear cache after task completion to free memory

### Thread Safety
- All operations are thread-safe
- Message queue uses Python's `queue.Queue`
- Coordinators use locks for cache access

## Future Enhancements

1. **Persistent Message Queue**: Save messages to disk for recovery
2. **Priority Queue**: Prioritize certain message types
3. **Message Expiration**: Automatically expire old messages
4. **Batch Operations**: Send/receive multiple messages at once
5. **Compression**: Compress large payloads
6. **Encryption**: Encrypt sensitive messages
7. **Remote Communication**: Support for distributed modules

## References

- Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
- Design Document: Module Coordination section
- Related Modules: TTT, LLM, Symbolic Solver
