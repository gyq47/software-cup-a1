# LoongArch64 cp39 wheels

Place verified `cp39-cp39-linux_loongarch64` wheels here before building the
LoongArch backend image.

The Python 3.9 Dockerfile installs `chromadb==0.4.24` and risky native
dependencies from this directory with `--find-links=/app/wheels`. Do not place
Python 3.10/3.11 wheels here for the LoongArch deployment route.
