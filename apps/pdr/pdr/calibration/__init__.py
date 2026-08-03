"""Tools for deriving and verifying the decoder geometry in pdr.config.

You need these whenever the HUD layout or capture resolution changes: the crop
offsets, digit cells and segment sample points in config.py are all specific to
this camera's 1920x1080 output.
"""
