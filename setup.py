from __future__ import annotations

from pathlib import Path

from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

ROOT = Path(__file__).resolve().parent
CPP = ROOT / "cpp"

ext_modules = [
    Pybind11Extension(
        "sip_market_native",
        [
            str(CPP / "src" / "order_book.cpp"),
            str(CPP / "src" / "matching_engine.cpp"),
            str(CPP / "src" / "bindings.cpp"),
        ],
        include_dirs=[str(CPP / "include")],
        cxx_std=17,
    ),
]

setup(
    name="sip-market-native",
    version="0.1.0",
    description="Native market simulation helpers",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
    packages=[],
    py_modules=[],
    zip_safe=False,
    python_requires=">=3.9",
)
