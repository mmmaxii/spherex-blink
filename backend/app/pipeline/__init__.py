"""Pipelines: the ordered steps behind each long request. Each one runs as a background job.

  common.py    reading many images in parallel with retries, progress and a list of skipped images
  blink.py     position → images → aligned frames, stacks per pass, differences, GIF
  spectrum.py  position → images → flux per image → spectrum per pass → classification

A pipeline is `run(params, progress) -> manifest` plus `start(params) -> Job`. Steps are plain
functions from data/, imaging/ and spectra/, so each can be replaced or validated on its own.
"""
