from .plugins import match_plugin_for_window


def get_prompt_for_window(title):
    plugin = match_plugin_for_window(title)
    return plugin.cleanup_prompt, plugin.label
