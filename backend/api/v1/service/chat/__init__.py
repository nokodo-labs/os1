"""chat service package.

keep this facade lightweight: submodules such as summarization are imported by
TaskIQ task registration, while agent/filter wiring imports those task modules.
eager re-exports here would recreate that cycle during worker startup.
"""
