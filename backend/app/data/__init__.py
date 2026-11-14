"""Getting SPHEREx data.

Planned modules:
  sia.py      SIA2 search (DR1 + QR3), parse polygons, detector, survey pass, approximate channel/wavelength
  s3fits.py   partial reads of L2 files from S3 with HTTP Range (only the rows needed)
  flags.py    flag bit names from the FLAGS header (MSKNnnnn) and the official masking recipe
  resolve.py  Sesame name resolution, sexagesimal parsing, proper motion to a given date
"""
