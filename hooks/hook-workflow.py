# Intentionally empty. pyinstaller-hooks-contrib ships a stdhook for the PyPI
# package "workflow", which collides with this repo's top-level `workflow`
# package and crashes Analysis with ImportErrorWhenRunningHook. This local
# empty hook takes precedence and neutralises it (same trick as ChromIQ).
