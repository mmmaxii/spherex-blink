"""Getting data: SPHEREx images and the catalogues around them.

resolve.py   name (Sesame) or typed coordinates → position at the SPHEREx epoch, with proper motion
sia.py       SIA2 search over the configured releases, survey passes, which images to read
l2.py        partial reads of L2 files from S3 (image, flags, variance, wavelength at a position)
flags.py     flag bit names from the FLAGS header (MSKNnnnn) and the official masking recipe
catalogs.py  Gaia DR3 and AllWISE sources for overlays
"""
