---
title: Engine integration
description: Live-engine tests: singletons, scene tree, and the SignalMonitor API.
order: 40
sidebar: Basics
draft: false
---

# Engine integration

Pure-logic tests run fine without the engine. When a test needs singletons, `ClassDB`, real scene-tree structure, or signals, opt in with a tag and one header.

## Opting in

1. Include `gdextest/engine.h`.
2. Tag the test `TAG_INTEGRATION` with `GDEX_TEST_T`.
3. Reach the engine through the context.

```cpp
#include <godot_cpp/classes/os.hpp>
#include "gdextest/assert.h"
#include "gdextest/engine.h"
#include "gdextest/registry.h"

GDEX_TEST_T(engine, singleton_is_live, TAG_INTEGRATION) {
    godot::OS *os = godot::OS::get_singleton();
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(os));
    GDEX_EXPECT_GT(os->get_processor_count(), 0);
}
```

## Engine accessors

`gdextest/engine.h` declares two functions:

| Function | Returns |
| --- | --- |
| `gdextest::engine_node(ctx)` | The host `godot::Node*` the adapter ran from, or null. |
| `gdextest::engine_tree(ctx)` | The live `godot::SceneTree*` (`engine_node(ctx)->get_tree()`), or null. |

Both return null when no engine is attached, for example in a self-test sub-run. Guard the result before use:

```cpp
godot::SceneTree *tree = gdextest::engine_tree(ctx);
if (!tree) {
    GDEX_FAIL("no live scene tree");
    return;
}
```

## Building scene structure

Create, parent, and free real nodes. Track what you create so the leak check catches leftovers:

```cpp
GDEX_TEST_T(engine, can_create_and_destroy_node, TAG_INTEGRATION) {
    godot::SceneTree *tree = gdextest::engine_tree(ctx);
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(tree));

    godot::Node *child = memnew(godot::Node);
    ctx.track_object(child);
    child->set_name("gdextest-temp");
    tree->get_root()->add_child(child);
    GDEX_EXPECT(child->get_parent() == static_cast<godot::Node *>(tree->get_root()));

    tree->get_root()->remove_child(child);
    memdelete(child);
}
```

Memory rules:

- Allocate engine objects with `memnew` and free them with `memdelete`.
- `RefCounted` objects can live in a `godot::Ref`. Track them with `ctx.track_ref`.
- Clean up in the body, or let a teardown do it (see [Writing tests](/projects/gdextest/docs/writing-tests)).

## Signal monitoring with `SignalMonitor`

`SignalMonitor` watches signals on any object. It counts emissions and records the arguments of every emission, so you can assert both firing and payload.

### Getting a monitor

```cpp
gdextest::SignalMonitor &monitor = ctx.signals();
```

The first call creates the monitor for this test. The framework registers a teardown that disconnects everything and frees the monitor when the test ends. You never free it yourself.

### Watching signals

| Method | Effect |
| --- | --- |
| `add(target, signal_name, expected = 0)` | Watch one signal. `expected` is the count `evaluate()` demands. |
| `add_all(target, {"a", "b"}, expected)` | Watch several signals at once. |
| `remove(target, signal_name)` | Stop watching and disconnect. |
| `remove_all()` | Stop watching everything and disconnect. |
| `reset(target, signal_name)` | Clear the count and history for one signal. |
| `reset_all()` | Clear counts and history everywhere. |

### Querying emissions

| Method | Returns |
| --- | --- |
| `was_emitted(target, signal_name)` | True when the signal fired at least once. |
| `get_emission_count(target, signal_name)` | Number of emissions seen. |
| `get_last_arguments(target, signal_name)` | Argument list of the newest emission. |
| `get_argument(target, signal_name, emission, arg)` | One argument of one emission, as a `Variant`. |
| `get_emission_history(target, signal_name)` | Every emission's argument list, oldest first. |

### Asserting the outcome

`evaluate()` returns true when every watched signal's emission count equals its expected count. Signals watched with the default expectation of `0` must not have fired.

```cpp
GDEX_TEST_T(monitor, node_added_is_observed, TAG_INTEGRATION) {
    gdextest::SignalMonitor &monitor = ctx.signals();
    godot::SceneTree *tree = gdextest::engine_tree(ctx);

    monitor.add(tree, "node_added", 1);      // expect exactly one emission
    godot::Node *child = memnew(godot::Node);
    tree->get_root()->add_child(child);      // fires node_added

    GDEX_EXPECT_TRUE(monitor.was_emitted(tree, "node_added"));
    GDEX_EXPECT_EQ(monitor.get_emission_count(tree, "node_added"), 1);
    GDEX_EXPECT_TRUE(monitor.evaluate());

    tree->get_root()->remove_child(child);
    memdelete(child);
}
```

A typical pattern: watch with `add(target, signal, 1)`, run the action, then check `evaluate()` last. `evaluate()` with nothing watched returns true.

### Notes and limits

- `SignalMonitor` is a registered Godot class. The framework registers it at the editor initialization level, so use the default editor host mode for suites that call `ctx.signals()`.
- Emission recording is synchronous. The monitor connects a bound callable per signal, so emissions that happen on other threads are not covered.
- Arguments are stored as `Variant`s. Use `Variant` conversion methods (`operator int()`, `String`, ...) to unpack them.

## What integration tests can reach

Inside the engine process, a test body can use everything godot-cpp offers:

- Singletons: `OS`, `Engine`, `Time`, `ProjectSettings`, your own autoloads.
- `ClassDB`: check that your classes are registered.
- The live scene tree: build graphs under `engine_tree(ctx)->get_root()`.
- Your extension's real code, compiled into the test build or loaded through `[gdextest.consumer_extension]` (see [Consumer guide](/projects/gdextest/docs/consumer-guide)).

Pair integration tests with async bodies when the behavior needs frames: `GDEX_TEST_ASYNC_T(my_suite, settles_over_frames, TAG_INTEGRATION | TAG_ASYNC)`. See [Async tests](/projects/gdextest/docs/async-tests).
