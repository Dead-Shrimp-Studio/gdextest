@tool
extends EditorPlugin
# Editor plugin manager requires the plugin script to extend EditorPlugin
# directly (extending the native GdextestPlugin is rejected). This thin wrapper
# instantiates the native plugin (registered in ClassDB by the extension) as a
# child; its C++ _ready() calls the adapter, which runs the suites and quits.
#
# The run is deferred until the initial editor filesystem scan finishes:
# quitting while the scan thread is still starting up races it and can crash
# the editor on shutdown (docs/testing/notes.md §3.3). _ready() fires mid
# initialization, so we poll EditorFileSystem.is_scanning() on process_frame.

const SCAN_TIMEOUT_MS := 20000

var test_plugin: Node
var _start_ms := 0

func _ready() -> void:
    _start_ms = Time.get_ticks_msec()
    get_tree().process_frame.connect(_on_frame)

func _on_frame() -> void:
    var fs := EditorInterface.get_resource_filesystem()
    if fs.is_scanning() and Time.get_ticks_msec() - _start_ms < SCAN_TIMEOUT_MS:
        return  # initial scan still running — keep waiting
    get_tree().process_frame.disconnect(_on_frame)
    test_plugin = GdextestPlugin.new()
    add_child(test_plugin)

func _exit_tree() -> void:
    if get_tree() and get_tree().process_frame.is_connected(_on_frame):
        get_tree().process_frame.disconnect(_on_frame)
    # The native plugin owns the test run and requests process shutdown. Do not
    # remove it during editor teardown; Godot owns plugin lifetime here (removing
    # it races the scan thread and can crash the editor on shutdown).
