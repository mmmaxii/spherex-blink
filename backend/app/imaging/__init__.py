"""Turning L2 cutouts into comparable frames.

grid.py        common north-up grid of a request; sky position → place on the displayed image
align.py       reprojection of a cutout (and its flag mask) onto the grid
background.py  per-image background level and noise
stack.py       sigma-clipped stacks and differences of aligned images
render.py      PNG frames with one common brightness scale, flag overlays, GIF
"""
