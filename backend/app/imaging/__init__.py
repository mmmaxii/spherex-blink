"""Turning L2 images into comparable frames.

Planned modules:
  background.py  local background (sigma-clipped, SOURCE pixels excluded), per-frame noise and weight
  reproject.py   flux-conserving reprojection to a common north-up grid (reproject_exact, as IRSA does)
  stack.py       inverse-variance weighted, sigma-clipped stacks per (detector, pass); differences
"""
