"""Learned movement model: data prep (numpy), model + training + detector (torch).

``segments`` turns recorded trainer sessions into fixed-timestep training
examples and needs only numpy. ``model``, ``train`` and ``detector`` need torch
(``pip install -e .[ml]`` plus a CUDA build of torch for GPU training).
"""
